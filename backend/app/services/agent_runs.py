from datetime import UTC, date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import contract_management, meeting_analysis, report_writing, schedule_management
from app.api import activities as activities_api
from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.agent import AgentApproval, AgentRun
from app.models.content import Report, ReportActivity
from app.models.crm import (
    Activity,
    ActivityCompanion,
    CustomerCompany,
    CustomerContact,
    SupportRequest,
)
from app.models.sales import SalesDeal, SalesPipelineStage
from app.models.workspace import Member
from app.schemas.agent_runs import (
    AgentApprovalCreate,
    AgentApprovalRead,
    AgentRunCreate,
    AgentRunRead,
)
from app.services.llm import LLMError

_SEOUL = ZoneInfo("Asia/Seoul")


def _seoul(value: datetime | None) -> datetime | None:
    """DB 에는 UTC 로 두고 응답에서만 서울 시간으로 바꾼다."""
    return None if value is None else value.astimezone(_SEOUL)


def _run_read(run: AgentRun) -> AgentRunRead:
    return AgentRunRead(
        id=run.id,
        agent_code=run.agent_code,
        trigger_code=run.trigger_code,
        status_code=run.status_code,
        llm_model_name=run.llm_model_name,
        prompt_version=run.prompt_version,
        requested_by_member_id=run.requested_by_member_id,
        source_refs=run.source_refs,
        output_snapshot=run.output_snapshot,
        evidence=run.evidence,
        error_message=run.error_message,
        started_at=_seoul(run.started_at),
        finished_at=_seoul(run.finished_at),
    )


def _scope(member: Member):
    """같은 팀에서 관리자는 전체를, 일반 구성원은 본인 실행만 본다."""
    conditions = [AgentRun.team_id == member.team_id]
    if member.role_code == "member":
        conditions.append(AgentRun.requested_by_member_id == member.id)
    return conditions


async def _draft_source(db: AsyncSession, member: Member, report_id: UUID) -> Report:
    """초안을 붙일 draft 보고서. 일반 구성원은 본인 것만, 관리자는 팀 전체를 다룬다."""
    conditions = [
        Report.id == report_id,
        Report.team_id == member.team_id,
    ]
    if member.role_code == "member":
        conditions.append(Report.author_member_id == member.id)
    report = (await db.execute(select(Report).where(*conditions))).scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="report_not_found",
        )
    if report.status_code != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="report_not_editable",
        )
    return report


def _value(value):
    if isinstance(value, (datetime, UUID)):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _snapshot(row, fields: tuple[str, ...]) -> dict:
    return {field: _value(getattr(row, field)) for field in fields}


def _severity_from_days(days_left: int) -> str | None:
    """dashboard.py 팔로우업 카드의 지남(high)/7일 이내(medium) 관례를 그대로 따른다."""
    if days_left < 0:
        return "high"
    if days_left <= 7:
        return "medium"
    return None


def _deal_risk_signals(
    deal: SalesDeal,
    stage: SalesPipelineStage | None,
    task_due: tuple[UUID, datetime] | None,
    now: datetime,
    today: date,
) -> list[dict]:
    signals: list[dict] = []

    def _add(code: str, severity: str | None, ref_type: str, ref_id) -> None:
        if severity is None:
            return
        signals.append(
            {
                "sales_deal_id": str(deal.id),
                "code": code,
                "severity": severity,
                "source_refs": [{"type": ref_type, "id": str(ref_id)}],
            }
        )

    if deal.quote_valid_until is not None:
        _add(
            "quote_expiring",
            _severity_from_days((deal.quote_valid_until - today).days),
            "sales_deal",
            deal.id,
        )
    if deal.contract_ends_on is not None:
        _add(
            "contract_expiring",
            _severity_from_days((deal.contract_ends_on - today).days),
            "sales_deal",
            deal.id,
        )
    if deal.expected_delivery_at is not None:
        _add(
            "delivery_delay_risk",
            _severity_from_days((deal.expected_delivery_at - now).days),
            "sales_deal",
            deal.id,
        )
    if task_due is not None:
        activity_id, due_at = task_due
        _add(
            "follow_up_overdue",
            _severity_from_days((due_at - now).days),
            "activity",
            activity_id,
        )
    if stage is not None and stage.phase_code in ("contract", "order", "closed"):
        missing = any(
            value is None
            for value in (deal.contract_no, deal.contract_signed_on, deal.contract_ends_on)
        )
        if missing:
            _add("missing_contract_information", "low", "sales_deal", deal.id)

    return signals


def _support_risk_signals(support_requests: list[SupportRequest]) -> list[dict]:
    return [
        {
            "sales_deal_id": None,
            "code": "unresolved_support",
            "severity": "high" if request.is_urgent else "medium",
            "source_refs": [{"type": "support_request", "id": str(request.id)}],
        }
        for request in support_requests
        if request.status_code == "in_progress"
    ]


async def _contract_source(
    db: AsyncSession, member: Member, payload: AgentRunCreate
) -> tuple[dict, dict]:
    company = (
        await db.execute(
            select(CustomerCompany).where(
                CustomerCompany.id == payload.customer_company_id,
                CustomerCompany.team_id == member.team_id,
            )
        )
    ).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail="customer_company_not_found")

    deal_conditions = [
        SalesDeal.team_id == member.team_id,
        SalesDeal.customer_company_id == company.id,
        SalesDeal.deleted_at.is_(None),
    ]
    if payload.sales_deal_ids:
        deal_conditions.append(SalesDeal.id.in_(payload.sales_deal_ids))
    deals = list((await db.execute(select(SalesDeal).where(*deal_conditions))).scalars().all())
    if payload.sales_deal_ids and {deal.id for deal in deals} != set(payload.sales_deal_ids):
        raise HTTPException(status_code=404, detail="sales_deal_not_found")

    deal_ids = [deal.id for deal in deals]
    activities = []
    reports = []
    if deal_ids:
        activities = list(
            (
                await db.execute(
                    select(Activity).where(
                        Activity.team_id == member.team_id,
                        Activity.sales_deal_id.in_(deal_ids),
                        Activity.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        reports = list(
            (
                await db.execute(
                    select(Report)
                    .join(ReportActivity, ReportActivity.report_id == Report.id)
                    .join(Activity, Activity.id == ReportActivity.activity_id)
                    .where(
                        Report.team_id == member.team_id,
                        Report.status_code == "approved",
                        Activity.team_id == member.team_id,
                        Activity.sales_deal_id.in_(deal_ids),
                        Activity.deleted_at.is_(None),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )

    support_requests = list(
        (
            await db.execute(
                select(SupportRequest)
                .join(CustomerContact, CustomerContact.id == SupportRequest.customer_contact_id)
                .where(
                    SupportRequest.team_id == member.team_id,
                    CustomerContact.company_id == company.id,
                )
            )
        )
        .scalars()
        .all()
    )
    stage_ids = [deal.sales_pipeline_stage_id for deal in deals]
    stages = (
        list(
            (
                await db.execute(
                    select(SalesPipelineStage).where(SalesPipelineStage.id.in_(stage_ids))
                )
            )
            .scalars()
            .all()
        )
        if stage_ids
        else []
    )

    now = datetime.now(UTC)
    today = now.astimezone(_SEOUL).date()
    stage_by_id = {stage.id: stage for stage in stages}
    task_due_by_deal: dict[UUID, tuple[UUID, datetime]] = {}
    for activity in activities:
        if (
            activity.activity_type == "task"
            and activity.due_at is not None
            and activity.sales_deal_id is not None
        ):
            current = task_due_by_deal.get(activity.sales_deal_id)
            if current is None or activity.due_at < current[1]:
                task_due_by_deal[activity.sales_deal_id] = (activity.id, activity.due_at)

    risk_signals: list[dict] = []
    for deal in deals:
        risk_signals.extend(
            _deal_risk_signals(
                deal,
                stage_by_id.get(deal.sales_pipeline_stage_id),
                task_due_by_deal.get(deal.id),
                now,
                today,
            )
        )
    risk_signals.extend(_support_risk_signals(support_requests))

    snapshot = {
        "customer_company": _snapshot(company, ("id", "name", "region_code")),
        "sales_deals": [
            _snapshot(
                deal,
                (
                    "id",
                    "title",
                    "description",
                    "deal_amount",
                    "opened_on",
                    "closed_on",
                    "quote_valid_until",
                    "contract_no",
                    "contract_signed_on",
                    "contract_ends_on",
                    "expected_delivery_at",
                    "memo",
                    "owner_member_id",
                    "updated_at",
                ),
            )
            for deal in deals
        ],
        "pipeline_stages": [
            _snapshot(stage, ("id", "stage_code", "name", "phase_code", "outcome_code", "position"))
            for stage in stages
        ],
        "approved_reports": [
            _snapshot(
                report, ("id", "report_kind", "content", "ai_evidence", "reviewed_at", "updated_at")
            )
            for report in reports
        ],
        "support_requests": [
            _snapshot(request, ("id", "title", "is_urgent", "status_code", "registered_at"))
            for request in support_requests
        ],
        "activities": [
            _snapshot(
                activity,
                (
                    "id",
                    "sales_deal_id",
                    "activity_type",
                    "title",
                    "starts_at",
                    "ends_at",
                    "due_at",
                    "completed_at",
                    "updated_at",
                ),
            )
            for activity in activities
        ],
        "risk_signals": risk_signals,
    }
    return snapshot, {
        "customer_company_id": str(company.id),
        "sales_deal_ids": [str(deal.id) for deal in deals],
    }


async def _schedule_source(
    db: AsyncSession, member: Member, payload: AgentRunCreate
) -> tuple[dict, dict]:
    deal = (
        await db.execute(
            select(SalesDeal).where(
                SalesDeal.id == payload.sales_deal_id,
                SalesDeal.team_id == member.team_id,
                SalesDeal.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=404, detail="sales_deal_not_found")

    member_ids = [payload.owner_member_id, *payload.companion_member_ids]
    found_members = set(
        (
            await db.execute(
                select(Member.id).where(
                    Member.id.in_(member_ids),
                    Member.team_id == member.team_id,
                    Member.active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    if found_members != set(member_ids):
        raise HTTPException(status_code=404, detail="member_not_found")

    parent_output = None
    if payload.parent_run_id:
        parent = (
            await db.execute(
                select(AgentRun).where(
                    AgentRun.id == payload.parent_run_id,
                    AgentRun.team_id == member.team_id,
                    AgentRun.agent_code == "contract_management",
                    AgentRun.status_code == "completed",
                )
            )
        ).scalar_one_or_none()
        if parent is None:
            raise HTTPException(status_code=404, detail="agent_run_not_found")
        parent_deals = set(parent.source_refs.get("sales_deal_ids", []))
        if parent_deals and str(deal.id) not in parent_deals:
            raise HTTPException(status_code=409, detail="parent_run_sales_deal_mismatch")
        parent_output = parent.output_snapshot

    companion_activity_ids = select(ActivityCompanion.activity_id).where(
        ActivityCompanion.member_id.in_(member_ids)
    )
    activities = list(
        (
            await db.execute(
                select(Activity).where(
                    Activity.team_id == member.team_id,
                    Activity.deleted_at.is_(None),
                    Activity.starts_at < payload.preferred_ends_at,
                    or_(Activity.ends_at.is_(None), Activity.ends_at > payload.preferred_starts_at),
                    or_(
                        Activity.owner_member_id.in_(member_ids),
                        Activity.id.in_(companion_activity_ids),
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    snapshot = {
        "contract_management_output": parent_output,
        "sales_deal": _snapshot(
            deal,
            (
                "id",
                "title",
                "customer_company_id",
                "owner_member_id",
                "contract_ends_on",
                "expected_delivery_at",
                "updated_at",
            ),
        ),
        "request": {
            "owner_member_id": str(payload.owner_member_id),
            "companion_member_ids": [str(value) for value in payload.companion_member_ids],
            "preferred_starts_at": payload.preferred_starts_at.isoformat(),
            "preferred_ends_at": payload.preferred_ends_at.isoformat(),
            "duration_minutes": payload.duration_minutes,
            "activity_type": payload.activity_type,
        },
        "activities": [
            _snapshot(
                activity,
                ("id", "owner_member_id", "title", "starts_at", "ends_at", "all_day", "updated_at"),
            )
            for activity in activities
        ],
    }
    return snapshot, {
        "sales_deal_id": str(deal.id),
        "activity_ids": [str(activity.id) for activity in activities],
    }


async def create(
    payload: AgentRunCreate,
    member: Member,
    db: AsyncSession,
) -> tuple[AgentRunRead, UUID | None]:
    """실행 이력을 만들고 새 실행이면 백그라운드 작업용 id 도 돌려준다."""
    # LLM 설정이 없으면 큐에 쌓아둬도 반드시 실패한다. 만들기 전에 막는다.
    if not settings.llm_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="llm_not_configured",
        )

    # 같은 사용자가 동일 키로 재전송하면 새 실행 대신 기존 실행을 돌려준다.
    existing = (
        await db.execute(
            select(AgentRun).where(
                AgentRun.requested_by_member_id == member.id,
                AgentRun.idempotency_key == payload.idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _run_read(existing), None

    try:
        parent_run_id = None
        if payload.agent_code in {"report_writing", "meeting_analysis"}:
            assert payload.report_id is not None
            report = await _draft_source(db, member, payload.report_id)
        if payload.agent_code == "report_writing":
            prompt_version = report_writing.PROMPT_VERSION
            input_snapshot = report_writing.input_snapshot(report, payload.guidance)
            source_refs = {"report_id": str(report.id)}
        elif payload.agent_code == "meeting_analysis":
            try:
                input_snapshot = meeting_analysis.input_snapshot(report.transcript)
            except ValueError as error:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=str(error),
                ) from error
            prompt_version = meeting_analysis.PROMPT_VERSION
            source_refs = {"report_id": str(report.id)}
        elif payload.agent_code == "contract_management":
            prompt_version = contract_management.PROMPT_VERSION
            input_snapshot, source_refs = await _contract_source(db, member, payload)
        else:
            prompt_version = schedule_management.PROMPT_VERSION
            input_snapshot, source_refs = await _schedule_source(db, member, payload)
            parent_run_id = payload.parent_run_id

        run = AgentRun(
            id=uuid4(),
            team_id=member.team_id,
            parent_run_id=parent_run_id,
            requested_by_member_id=member.id,
            agent_code=payload.agent_code,
            trigger_code="user",
            idempotency_key=payload.idempotency_key,
            # 실제 호출은 백그라운드에서 한다. 여기서는 대기 상태로만 남긴다.
            status_code="queued",
            llm_model_name=settings.llm_model,
            prompt_version=prompt_version,
            source_refs=source_refs,
            # 실행 시점 입력을 저장한다. 보고서가 바뀌어도 이 실행에 사용한 입력은 남는다.
            input_snapshot=input_snapshot,
            output_snapshot=None,
            evidence=None,
            error_message=None,
            started_at=None,
            finished_at=None,
        )
        db.add(run)
        await db.flush()
        read = _run_read(run)
        await db.commit()
    except Exception:
        # 실행 이력이 일부만 저장되지 않도록 트랜잭션 전체를 되돌린다.
        await db.rollback()
        raise

    return read, run.id


async def execute(run_id: UUID) -> None:
    """백그라운드 실행. 요청 세션이 닫힌 뒤라 자체 세션을 쓴다."""
    sessionmaker = get_sessionmaker()
    # 1) 아직 queued 인 실행만 running 으로 바꾼다. 이미 처리된 재호출은 건너뛴다.
    # ponytail: 초기 단일 프로세스 전제. 다중 worker 에서는 조건부 UPDATE 로 선점한다.
    async with sessionmaker() as session:
        run = (
            await session.execute(select(AgentRun).where(AgentRun.id == run_id))
        ).scalar_one_or_none()
        if run is None or run.status_code != "queued":
            return
        run.status_code = "running"
        run.started_at = datetime.now(UTC)
        await session.commit()

        agent_code = run.agent_code
        input_snapshot = run.input_snapshot

    output = None
    error: str | None = None
    # 2) LLM 호출. 느린 구간이라 DB 커넥션을 쥐지 않은 채로 돈다.
    try:
        if agent_code == "report_writing":
            output = await report_writing.run(input_snapshot)
        elif agent_code == "meeting_analysis":
            output = await meeting_analysis.run(input_snapshot)
        elif agent_code == "contract_management":
            output = await contract_management.run(input_snapshot)
        elif agent_code == "schedule_management":
            output = await schedule_management.run(input_snapshot)
        else:
            error = "unsupported_agent"
    except LLMError as caught:
        error = str(caught)
    except Exception:
        # 공급자 예외 원문에 URL 이나 key 가 섞일 수 있어 코드만 남긴다.
        error = "llm_unexpected_error"

    # 3) 결과 기록.
    async with sessionmaker() as session:
        run = (
            await session.execute(select(AgentRun).where(AgentRun.id == run_id))
        ).scalar_one_or_none()
        if run is None:
            return
        run.finished_at = datetime.now(UTC)
        if output is None:
            run.status_code = "failed"
            run.error_message = error
        else:
            run.status_code = "completed"
            run.output_snapshot = output.model_dump()
            if run.agent_code == "report_writing":
                # 제안일 뿐이다. 사람이 확인해 보고서에 반영하기 전에는 report 를 고치지 않는다.
                run.evidence = {
                    "prompt_version": report_writing.PROMPT_VERSION,
                    "summary": output.summary,
                }
            elif run.agent_code == "meeting_analysis":
                run.evidence = {
                    "prompt_version": meeting_analysis.PROMPT_VERSION,
                    "model_version": output.deal_assessment.model_version,
                }
            else:
                run.evidence = {
                    "prompt_version": run.prompt_version,
                    "source_refs": run.source_refs,
                }
        await session.commit()


async def get(agent_run_id: UUID, member: Member, db: AsyncSession) -> AgentRunRead:
    """권한 밖의 실행은 존재 여부도 알리지 않고 404 로 답한다."""
    run = (
        await db.execute(select(AgentRun).where(AgentRun.id == agent_run_id, *_scope(member)))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="agent_run_not_found",
        )
    return _run_read(run)


def _approval_read(approval: AgentApproval) -> AgentApprovalRead:
    return AgentApprovalRead(
        id=approval.id,
        agent_run_id=approval.agent_run_id,
        activity_id=UUID(approval.result_refs["activity_id"]),
        report_id=UUID(approval.result_refs["report_id"]),
        created_at=approval.created_at,
    )


async def approve_schedule(
    agent_run_id: UUID,
    payload: AgentApprovalCreate,
    member: Member,
    db: AsyncSession,
) -> AgentApprovalRead:
    """일정관리 실행의 후보 하나를 승인해 activity 와 계약 현황 브리핑 report 를 만든다.

    Agent 가 반환한 candidate_id 는 신뢰하지 않고, 사용자가 확정한 제목·시간·담당자·분류를
    다시 검증한다. activity/report/agent_approval 은 한 트랜잭션으로만 반영한다.
    """
    existing = (
        await db.execute(
            select(AgentApproval).where(
                AgentApproval.requested_by_member_id == member.id,
                AgentApproval.idempotency_key == payload.idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _approval_read(existing)

    try:
        run = (
            await db.execute(
                select(AgentRun)
                .where(AgentRun.id == agent_run_id, *_scope(member))
                .with_for_update(of=AgentRun)
            )
        ).scalar_one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail="agent_run_not_found")
        if run.agent_code != "schedule_management":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="approval_not_supported_for_agent",
            )
        if run.status_code != "completed":
            raise HTTPException(status_code=409, detail="agent_run_not_completed")

        request_snapshot = run.input_snapshot["request"]
        activity_type = request_snapshot["activity_type"]
        owner_member_id = payload.owner_member_id or UUID(request_snapshot["owner_member_id"])
        companion_member_ids = (
            [UUID(value) for value in request_snapshot["companion_member_ids"]]
            if payload.companion_member_ids is None
            else payload.companion_member_ids
        )

        deal = (
            await db.execute(
                select(SalesDeal).where(
                    SalesDeal.id == UUID(run.source_refs["sales_deal_id"]),
                    SalesDeal.team_id == member.team_id,
                    SalesDeal.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if deal is None:
            raise HTTPException(status_code=409, detail="stale_agent_result")

        member_ids = [owner_member_id, *companion_member_ids]
        found_members = set(
            (
                await db.execute(
                    select(Member.id).where(
                        Member.id.in_(member_ids),
                        Member.team_id == member.team_id,
                        Member.active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        if found_members != set(member_ids):
            raise HTTPException(status_code=404, detail="member_not_found")

        category = await activities_api._active_activity_category(
            db, member, payload.category_code, activity_type
        )
        action_tag = (
            None
            if payload.action_tag is None
            else await activities_api._active_activity_action_tag(
                db, member, payload.action_tag, activity_type
            )
        )

        companion_activity_ids = select(ActivityCompanion.activity_id).where(
            ActivityCompanion.member_id.in_(member_ids)
        )
        candidate_activities = (
            (
                await db.execute(
                    select(Activity).where(
                        Activity.team_id == member.team_id,
                        Activity.deleted_at.is_(None),
                        Activity.starts_at < payload.ends_at,
                        or_(Activity.ends_at.is_(None), Activity.ends_at > payload.starts_at),
                        or_(
                            Activity.owner_member_id.in_(member_ids),
                            Activity.id.in_(companion_activity_ids),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        conflicts = schedule_management._conflicts_for(
            schedule_management.ScheduleCandidate(
                candidate_id="approval",
                title=payload.title,
                activity_type=activity_type,
                starts_at=payload.starts_at.isoformat(),
                ends_at=payload.ends_at.isoformat(),
                priority=1,
            ),
            [
                _snapshot(
                    activity,
                    (
                        "id",
                        "owner_member_id",
                        "title",
                        "starts_at",
                        "ends_at",
                        "all_day",
                        "updated_at",
                    ),
                )
                for activity in candidate_activities
            ],
        )
        if conflicts:
            raise HTTPException(status_code=409, detail="schedule_conflict")

        activity = Activity(
            id=uuid4(),
            team_id=member.team_id,
            owner_member_id=owner_member_id,
            activity_type=activity_type,
            activity_category_id=category.id,
            activity_action_tag_id=None if action_tag is None else action_tag.id,
            title=payload.title,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            all_day=False,
            sales_deal_id=deal.id,
            note=payload.note,
        )
        db.add(activity)
        for companion_id in companion_member_ids:
            db.add(ActivityCompanion(activity_id=activity.id, member_id=companion_id))

        parent_output = None
        if run.parent_run_id is not None:
            parent_run = (
                await db.execute(select(AgentRun).where(AgentRun.id == run.parent_run_id))
            ).scalar_one_or_none()
            parent_output = None if parent_run is None else parent_run.output_snapshot

        report = Report(
            id=uuid4(),
            team_id=member.team_id,
            author_member_id=member.id,
            recipient_member_id=None,
            template_snapshot={},
            source_activity_id=activity.id,
            report_kind="contract_status_briefing",
            report_date=datetime.now(UTC).astimezone(_SEOUL).date(),
            period_start=None,
            period_end=None,
            status_code="draft",
            content={
                "sales_deal_id": str(deal.id),
                "contract_summary": (parent_output or {}).get("contract_summary"),
                "risks": (parent_output or {}).get("risks", []),
                "recommended_actions": (parent_output or {}).get("recommended_actions", []),
            },
            transcript=None,
            source_snapshot=None,
            ai_evidence={
                "schedule_management_run_id": str(run.id),
                "contract_management_run_id": (
                    str(run.parent_run_id) if run.parent_run_id else None
                ),
                "prompt_version": run.prompt_version,
            },
            note=None,
            reviewed_by_member_id=None,
            reviewed_at=None,
        )
        db.add(report)

        approval = AgentApproval(
            id=uuid4(),
            agent_run_id=run.id,
            team_id=member.team_id,
            requested_by_member_id=member.id,
            idempotency_key=payload.idempotency_key,
            decision_snapshot=payload.model_dump(mode="json"),
            result_refs={"activity_id": str(activity.id), "report_id": str(report.id)},
            created_at=datetime.now(UTC),
        )
        db.add(approval)

        await db.flush()
        read = _approval_read(approval)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="agent_approval_conflict") from exc
    except Exception:
        await db.rollback()
        raise
    return read
