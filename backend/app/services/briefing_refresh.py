"""자료·미팅이 바뀌면 AI 브리핑을 미리 다시 만들어 두는 백그라운드 예약.

화면은 브리핑을 만들지 않는다. 미팅 상세를 열면 이미 저장된 최신 성공 브리핑을 그대로
읽기만 한다(``app.api.activities._activity_briefing``). 그 브리핑을 누가 언제 만드는가가
이 모듈이다.

흐름은 셋으로 나뉜다.

1. **예약** — 자료 처리가 커밋된 뒤, 또는 미팅·딜의 연결이 바뀐 뒤에 영향받는 *미래*
   미팅을 찾아 ``agent_run`` 한 행씩 큐에 넣는다. LLM 호출은 여기서 하지 않는다.
2. **실행** — 기존 범용 worker(``app.services.agent_worker``)가 그대로 집어간다. 새 큐도
   새 테이블도 만들지 않았다. worker 가 입력 스냅샷을 만들 때 그 시점의 source revision 을
   ``source_refs`` 에 함께 적는다(``agent_runs._build_run_input``).
3. **게시** — 완료 시점에 revision 을 다시 계산해 비교한다. 같으면 그대로 최신 브리핑이
   되고, 다르면(실행 중에 새 자료가 들어왔다) 후속 실행을 예약한다.

source revision 은 "검색용 버전" 같은 임의의 증가 숫자가 아니라 실제 검색 대상 상태의
지문이다 — :func:`source_revision` 주석 참고.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.agent import AgentRun
from app.models.content import Document
from app.models.content import File as FileRow
from app.models.crm import Activity
from app.models.sales import SalesDeal, SalesDealItem
from app.models.workspace import Member
from app.services import activity_documents, document_processing

BRIEFING_AGENT_CODE = "contract_management_briefing"
# 기존 일정 등록 경로(app.api.activities)가 쓰던 것과 같은 네임스페이스다. 멱등키의 입력만
# activity_id 에서 "activity_id:revision" 으로 넓힌다.
IDEMPOTENCY_NAMESPACE = uuid5(NAMESPACE_URL, "urn:salesluv:contract_management_briefing")
# 한 번의 자료 처리로 되살아나는 미팅 수의 상한. 고객사 전체 자료를 하나 올렸다고 수백 건의
# LLM 실행이 한꺼번에 큐에 쌓이는 것을 막는다. 가까운 미팅부터 채운다.
MAX_ACTIVITIES_PER_TRIGGER = 50


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _isoformat(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat()


async def _owner(db: AsyncSession, activity: Activity) -> Member | None:
    """브리핑을 실행할 주체. 그 미팅 담당자의 권한으로 자료를 본다.

    worker 의 ``prepare_claimed`` 가 요구하는 조건(같은 팀, 활성, member/manager)을 여기서
    미리 확인한다. 퇴사 처리된 담당자의 미팅은 큐에 넣어도 반드시 실패하므로 넣지 않는다.
    """
    return (
        await db.execute(
            select(Member).where(
                Member.id == activity.owner_member_id,
                Member.team_id == activity.team_id,
                Member.active.is_(True),
                Member.role_code.in_(("member", "manager")),
            )
        )
    ).scalar_one_or_none()


async def source_revision(db: AsyncSession, *, activity: Activity, member: Member | None) -> str:
    """이 미팅의 브리핑이 실제로 검색하게 될 상태의 지문.

    임의로 올리는 숫자를 두지 않는다. 같은 자료 상태에서 두 번 계산하면 같은 값이 나오고,
    검색 결과가 달라질 만한 변화가 있으면 반드시 달라지는 값이어야 한다. 그래서 입력을
    "브리핑이 무엇을 보게 되는가" 그대로로 잡았다.

    * 미팅이 정하는 검색 범위 — 고객사, 딜, 제품, 담당자, 시작 시각
    * 딜의 대표 제품과 견적 품목 — 제품 자료의 범위를 정한다
    * 그 범위에서 실제로 읽히게 될 문서와 파일 — ``document_id``, ``file_id``,
      ``version_no``, ``processed_at``

    파일 목록은 ``search_chunks`` 와 같은 조건으로 뽑는다. 그래서

    * 자료를 지우면(``deleted_at``) 목록에서 빠져 지문이 바뀐다.
    * 딜·고객사·제품 연결을 바꾸면 범위에 들고 나므로 지문이 바뀐다.
    * 같은 문서를 다시 올리면 새 ``file_id``/``version_no`` 가 들어와 지문이 바뀐다.
    * 재처리로 ``processed_at`` 만 바뀌어도 지문이 바뀐다.

    ``member`` 는 실행 주체다. 자료실 공개 범위(``document_access``)를 지문 계산에도 똑같이
    적용해, 그 사람이 볼 수 없는 자료 때문에 브리핑이 다시 만들어지지 않게 한다.
    """
    # develop 의 이름은 `_product_ids` 다. 관련자료 조회 경로를 그대로 두기 위해
    # 이름 정리는 이번 범위에서 하지 않는다(구현계획 5장).
    product_ids = await activity_documents._product_ids(
        db, team_id=activity.team_id, activity=activity
    )
    scopes = document_processing.document_scopes(
        activity.sales_deal_id, activity.customer_company_id, product_ids
    )
    files: list[list[Any]] = []
    if scopes:
        rows = (
            await db.execute(
                select(Document.id, FileRow.id, FileRow.version_no, FileRow.processed_at)
                .join(FileRow, FileRow.document_id == Document.id)
                .where(
                    Document.team_id == activity.team_id,
                    Document.deleted_at.is_(None),
                    FileRow.processing_status == "completed",
                    document_processing.latest_completed_file(),
                    *document_processing.document_access(member),
                    or_(*scopes),
                )
            )
        ).all()
        files = sorted(
            [str(document_id), str(file_id), version_no, _isoformat(processed_at)]
            for document_id, file_id, version_no, processed_at in rows
        )
    payload = {
        "activity": [
            str(activity.customer_company_id) if activity.customer_company_id else None,
            str(activity.sales_deal_id) if activity.sales_deal_id else None,
            str(activity.customer_contact_id) if activity.customer_contact_id else None,
            str(activity.product_id) if activity.product_id else None,
            _isoformat(activity.starts_at),
        ],
        "products": sorted(str(value) for value in product_ids),
        "files": files,
    }
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


def idempotency_key(activity_id: UUID, revision: str) -> UUID:
    """같은 미팅·같은 revision 이면 항상 같은 키.

    ``agent_run`` 의 ``UNIQUE (requested_by_member_id, idempotency_key)`` 가 중복을
    결정한다. 메모리 debounce 가 아니라서 프로세스를 다시 띄워도, worker 가 여럿이어도
    같은 revision 의 브리핑은 한 번만 만들어진다. 반대로 revision 이 바뀌면 이미 돌고 있는
    실행이 있어도 새 요청이 들어간다 — 실행 시작 뒤에 올라온 자료를 놓치지 않기 위해서다.
    """
    return uuid5(IDEMPOTENCY_NAMESPACE, f"{activity_id}:{revision}")


async def _future_meetings(
    db: AsyncSession,
    *,
    team_id: UUID,
    scopes: list[Any],
    now: datetime,
) -> list[Activity]:
    """지금 이후에 시작하는 미팅만. 이미 지난 미팅의 브리핑은 다시 만들지 않는다."""
    if not scopes:
        return []
    return list(
        (
            await db.execute(
                select(Activity)
                .where(
                    Activity.team_id == team_id,
                    Activity.deleted_at.is_(None),
                    Activity.completed_at.is_(None),
                    Activity.starts_at >= now,
                    or_(*scopes),
                )
                .order_by(Activity.starts_at.asc(), Activity.id.asc())
                .limit(MAX_ACTIVITIES_PER_TRIGGER)
            )
        )
        .scalars()
        .all()
    )


def _deal_scope(sales_deal_id: UUID) -> Any:
    return Activity.sales_deal_id == sales_deal_id


def _company_scope(customer_company_id: UUID) -> Any:
    """그 고객사 미팅. 딜을 거쳐 회사가 정해지는 미팅도 함께 본다."""
    return or_(
        Activity.customer_company_id == customer_company_id,
        Activity.sales_deal_id.in_(
            select(SalesDeal.id).where(SalesDeal.customer_company_id == customer_company_id)
        ),
    )


def _product_scope(product_id: UUID) -> Any:
    """그 제품을 다루는 미팅. 딜 대표 제품과 견적 품목까지 본다."""
    return or_(
        Activity.product_id == product_id,
        Activity.sales_deal_id.in_(select(SalesDeal.id).where(SalesDeal.product_id == product_id)),
        Activity.sales_deal_id.in_(
            select(SalesDealItem.sales_deal_id).where(SalesDealItem.product_id == product_id)
        ),
    )


def document_activity_scopes(
    *,
    sales_deal_id: UUID | None,
    customer_company_id: UUID | None,
    product_id: UUID | None,
) -> list[Any]:
    """이 자료가 영향을 주는 미팅의 조건.

    자료가 걸려 있는 범위만 본다. 딜에만 붙은 자료는 그 딜의 미팅만 건드리고, 같은 고객사의
    다른 딜은 건드리지 않는다.
    """
    scopes: list[Any] = []
    if sales_deal_id is not None:
        scopes.append(_deal_scope(sales_deal_id))
    if customer_company_id is not None:
        scopes.append(_company_scope(customer_company_id))
    if product_id is not None:
        scopes.append(_product_scope(product_id))
    return scopes


async def schedule_activities(db: AsyncSession, activities: list[Activity]) -> list[UUID]:
    """미팅별로 지금 revision 에 해당하는 브리핑 실행을 큐에 넣는다.

    이미 같은 revision 으로 만들어 둔 실행이 있으면 조용히 건너뛴다. 한 미팅에 자료 여러
    개가 연달아 처리돼도 revision 이 그대로면 실행은 하나다.

    호출하는 쪽의 트랜잭션을 쓰지 않는다 — 이 함수는 스스로 커밋한다. 자료 저장이 이미
    커밋된 뒤에 부르는 것이 전제이고(미완성 청크가 검색되면 안 된다), 예약이 실패해도
    앞선 저장은 되돌리지 않는다.
    """
    if not settings.llm_configured or not activities:
        return []
    from app.services.agent_runs import _prompt_version, _request_hash

    queued: list[UUID] = []
    for activity in activities:
        member = await _owner(db, activity)
        if member is None:
            continue
        revision = await source_revision(db, activity=activity, member=member)
        key = idempotency_key(activity.id, revision)
        existing = (
            await db.execute(
                select(AgentRun.id).where(
                    AgentRun.requested_by_member_id == member.id,
                    AgentRun.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        request_snapshot = {
            "agent_code": BRIEFING_AGENT_CODE,
            "activity_id": str(activity.id),
            "idempotency_key": str(key),
        }
        now = datetime.now(UTC)
        run = AgentRun(
            id=uuid4(),
            team_id=activity.team_id,
            parent_run_id=None,
            requested_by_member_id=member.id,
            agent_code=BRIEFING_AGENT_CODE,
            # 사람이 버튼을 눌러 만든 실행과 구분한다. 화면에는 더 이상 그 버튼이 없다.
            trigger_code="system",
            idempotency_key=key,
            report_id=None,
            status_code="queued",
            llm_model_name=settings.llm_model,
            # agent_run.prompt_version 은 빈 문자열을 허용하지 않는다
            # (baseline 의 agent_run_prompt_version_check). 큐에 넣는 시점에는 기존
            # agent_runs.create 와 같은 값을 쓰고, 실제 값은 prepare_claimed 가 입력을
            # 만들면서 다시 쓴다.
            prompt_version=_prompt_version(BRIEFING_AGENT_CODE),
            request_snapshot=request_snapshot,
            # worker 가 선점하는 조건이다(request_hash IS NOT NULL). 이 값이 있어야 범용
            # worker 가 입력을 만들고 실행한다 — 별도 worker 를 두지 않는 이유다.
            request_hash=_request_hash(request_snapshot),
            scope_key=None,
            source_refs={"activity_id": str(activity.id), "source_revision": revision},
            input_snapshot={},
            output_snapshot=None,
            evidence=None,
            error_message=None,
            error_code=None,
            current_stage_code="queued",
            attempt_count=0,
            payload_expires_at=None,
            payload_redacted_at=None,
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=None,
            next_attempt_at=now,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            created_at=now,
            started_at=None,
            finished_at=None,
        )
        db.add(run)
        try:
            # 미팅마다 따로 커밋한다. 한 미팅에서 UNIQUE 에 걸렸다고 rollback 하면, 같은
            # 호출에서 이미 넣어 둔 다른 미팅의 예약까지 함께 사라진다.
            await db.commit()
        except IntegrityError:
            # 다른 worker·요청이 같은 revision 을 먼저 넣었다. UNIQUE 가 승자를 정한다.
            await db.rollback()
            continue
        queued.append(run.id)
    return queued


async def schedule_for_activity(activity_id: UUID) -> list[UUID]:
    """미팅 하나의 브리핑을 예약한다. 미팅 등록·수정 트리거가 쓴다."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        activity = (
            await session.execute(
                select(Activity).where(
                    Activity.id == activity_id,
                    Activity.deleted_at.is_(None),
                    Activity.completed_at.is_(None),
                    Activity.starts_at >= datetime.now(UTC),
                )
            )
        ).scalar_one_or_none()
        if activity is None:
            return []
        return await schedule_activities(session, [activity])


async def schedule_for_document_scope(
    *,
    team_id: UUID,
    sales_deal_id: UUID | None,
    customer_company_id: UUID | None,
    product_id: UUID | None,
) -> list[UUID]:
    """자료 하나가 걸린 범위의 미래 미팅을 모두 예약한다."""
    scopes = document_activity_scopes(
        sales_deal_id=sales_deal_id,
        customer_company_id=customer_company_id,
        product_id=product_id,
    )
    if not scopes:
        return []
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        activities = await _future_meetings(
            session, team_id=team_id, scopes=scopes, now=datetime.now(UTC)
        )
        return await schedule_activities(session, activities)


async def schedule_for_file(file_id: UUID) -> list[UUID]:
    """자료 처리가 끝난 파일 하나를 기준으로 영향받는 미팅을 예약한다.

    반드시 자료 저장이 커밋된 뒤에 부른다. 처리 중이던 청크가 검색에 섞이면 브리핑이
    미완성 근거를 인용한다. 처리에 실패한 파일은 ``processing_status`` 가 completed 가
    아니라 여기서 아무것도 예약하지 않는다.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(Document)
                .join(FileRow, FileRow.document_id == Document.id)
                .where(
                    FileRow.id == file_id,
                    FileRow.processing_status == "completed",
                    Document.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return []
        team_id = row.team_id
        sales_deal_id = row.sales_deal_id
        customer_company_id = row.customer_company_id
        product_id = row.product_id
    return await schedule_for_document_scope(
        team_id=team_id,
        sales_deal_id=sales_deal_id,
        customer_company_id=customer_company_id,
        product_id=product_id,
    )


async def schedule_quietly(coroutine) -> None:
    """백그라운드 트리거용 감싸개.

    예약이 실패해도 앞선 저장(자료 원문·요약, 일정 등록)은 이미 커밋됐고 되돌리지 않는다.
    다음 트리거가 같은 미팅을 다시 예약하므로 여기서 재시도하지 않는다.
    """
    try:
        await coroutine
    except Exception as error:
        # 넓게 잡는다. 이 함수는 이미 커밋된 저장 뒤에 붙는 곁가지라, 어떤 이유로 예약이
        # 깨지더라도 그 저장을 실패로 되돌리게 두면 안 된다.
        from app.services.agent_logging import log_agent_error

        log_agent_error(
            error,
            stage="briefing_refresh.schedule",
            error_code="briefing_refresh_schedule_failed",
        )


async def follow_up_if_stale(run_id: UUID) -> list[UUID]:
    """실행이 끝난 뒤 revision 을 다시 보고, 그 사이에 자료가 바뀌었으면 후속을 예약한다.

    오래된 결과가 최신 브리핑을 덮는 일은 여기서 막지 않는다 — 조회하는 쪽이 실행 시각이
    아니라 ``source_observed_at`` 순으로 고르기 때문에, 늦게 끝난 옛 실행은 애초에 최신으로
    뽑히지 않는다(``app.api.activities._activity_briefing``). 여기서 할 일은 "그래서 아직
    아무도 최신 상태를 만들지 않았다"는 사실을 큐에 되돌려 놓는 것뿐이다.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        run = (
            await session.execute(select(AgentRun).where(AgentRun.id == run_id))
        ).scalar_one_or_none()
        if run is None or run.agent_code != BRIEFING_AGENT_CODE:
            return []
        refs = run.source_refs or {}
        activity_id = refs.get("activity_id")
        if activity_id is None:
            return []
        activity = (
            await session.execute(
                select(Activity).where(
                    Activity.id == UUID(str(activity_id)),
                    Activity.deleted_at.is_(None),
                    Activity.completed_at.is_(None),
                    Activity.starts_at >= datetime.now(UTC),
                )
            )
        ).scalar_one_or_none()
        if activity is None:
            return []
        member = await _owner(session, activity)
        if member is None:
            return []
        current = await source_revision(session, activity=activity, member=member)
        if current == refs.get("source_revision"):
            return []
        return await schedule_activities(session, [activity])
