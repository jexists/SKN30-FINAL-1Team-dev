"""AI 브리핑이 지금 자료 상태를 반영하고 있는지 판단하는 지문 계산.

브리핑은 일정 등록 때 한 번 만들고, 그 뒤에는 사람이 새로고침을 눌렀을 때만 다시 만든다.
자료·보고서·딜이 바뀌었다고 서버가 브리핑을 마음대로 바꾸지 않는다.

대신 실행을 만들 때 그 시점의 지문(:func:`source_revision`)을 ``source_refs`` 에 남기고
(``agent_runs._build_run_input``), 미팅 상세를 열 때 지금 지문과 비교해 다르면 화면에
"재생성 필요"를 띄운다(``app.api.activities._activity_briefing``).

지문은 임의의 증가 숫자가 아니라 브리핑 입력 상태 그 자체의 해시다 — :func:`source_revision`
주석 참고.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import Document, Report, ReportDeal, ReportSubmission
from app.models.content import File as FileRow
from app.models.crm import (
    Activity,
    CustomerCompany,
    CustomerContact,
    SupportRequest,
    SupportResponse,
)
from app.models.sales import SalesDeal, SalesPipelineStage
from app.models.workspace import Member
from app.services import activity_documents, document_processing


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _isoformat(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value.isoformat()


async def owner(db: AsyncSession, activity: Activity) -> Member | None:
    """지문을 계산할 기준 구성원. 그 미팅 담당자의 자료 공개 범위로 본다.

    실행을 만든 사람(팀장 대리 새로고침 등)과 화면을 연 사람이 달라도 같은 기준으로
    계산해야, 자료는 그대로인데 공개 범위 차이만으로 "재생성 필요"가 뜨지 않는다.
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
    """이 미팅의 브리핑 입력 상태의 지문.

    임의로 올리는 숫자를 두지 않는다. 같은 상태에서 두 번 계산하면 같은 값이 나오고,
    브리핑 내용이 달라질 만한 변화가 있으면 반드시 달라지는 값이어야 한다. 그래서 입력을
    "브리핑이 무엇을 보게 되는가"(``contract_schedule_snapshots.build_briefing_snapshot``)
    그대로로 잡았다. RAG 검색 결과 자체는 넣지 않는다 — 조회마다 임베딩을 호출하게 된다.
    대신 검색 대상이 되는 파일 목록을 넣는다.

    * 미팅 — 고객사, 고객 담당자, 시작·종료 시각, 제목, 장소, 메모, 첫 미팅 여부
    * 고객사 이름, 고객 담당자 이름·부서·직함
    * 고객사의 딜 — 제목, 단계, 금액, 계약 종료일, 지급조건, 견적 유효기간, 납기 예정일
    * 딜의 대표 제품과 견적 품목 — 제품 자료의 범위를 정한다
    * 그 범위에서 실제로 읽히게 될 문서와 파일 — ``document_id``, ``category_code``,
      ``file_id``, ``version_no``, ``processed_at``
    * 회사의 확정 보고서 전체 — ``report_id``, 현재 제출본과 제출 시각
    * 회사의 C/S — 제목·긴급·상태, 본문 수정 시각, 대응 기록 수와 마지막 대응 시각

    파일 목록은 ``search_chunks`` 와 같은 조건으로 뽑는다. 그래서

    * 자료를 지우면(``deleted_at``) 목록에서 빠져 지문이 바뀐다.
    * 딜·고객사·제품 연결을 바꾸면 범위에 들고 나므로 지문이 바뀐다.
    * 같은 문서를 다시 올리면 새 ``file_id``/``version_no`` 가 들어와 지문이 바뀐다.
    * 재처리로 ``processed_at`` 만 바뀌어도 지문이 바뀐다.

    ``member`` 는 :func:`owner` 로 구한 미팅 담당자다. 자료실 공개 범위(``document_access``)를
    지문 계산에도 똑같이 적용한다.
    """
    deals: list[list[Any]] = []
    if activity.customer_company_id is not None:
        deal_rows = (
            await db.execute(
                select(
                    SalesDeal.id,
                    SalesDeal.title,
                    SalesPipelineStage.phase_code,
                    SalesPipelineStage.outcome_code,
                    SalesDeal.deal_amount,
                    SalesDeal.contract_amount,
                    SalesDeal.contract_ends_on,
                    SalesDeal.contract_payment_terms,
                    SalesDeal.quote_valid_until,
                    SalesDeal.expected_delivery_at,
                )
                .join(
                    SalesPipelineStage,
                    and_(
                        SalesPipelineStage.sales_pipeline_id == SalesDeal.sales_pipeline_id,
                        SalesPipelineStage.id == SalesDeal.sales_pipeline_stage_id,
                    ),
                )
                .where(
                    SalesDeal.team_id == activity.team_id,
                    SalesDeal.customer_company_id == activity.customer_company_id,
                    SalesDeal.deleted_at.is_(None),
                )
            )
        ).all()
        deals = sorted(
            [
                str(deal_id),
                title,
                phase_code,
                outcome_code,
                None if deal_amount is None else str(deal_amount),
                None if contract_amount is None else str(contract_amount),
                _isoformat(contract_ends_on),
                payment_terms,
                _isoformat(quote_valid_until),
                _isoformat(expected_delivery_at),
            ]
            for (
                deal_id,
                title,
                phase_code,
                outcome_code,
                deal_amount,
                contract_amount,
                contract_ends_on,
                payment_terms,
                quote_valid_until,
                expected_delivery_at,
            ) in deal_rows
        )
    deal_ids = [UUID(deal[0]) for deal in deals]
    product_ids = await activity_documents.product_ids_for_deals(
        db, team_id=activity.team_id, sales_deal_ids=deal_ids
    )
    reports: list[list[Any]] = []
    report_text: list[dict[str, Any]] = []
    if activity.customer_company_id is not None:
        deal_report_ids = select(ReportDeal.report_id).where(ReportDeal.sales_deal_id.in_(deal_ids))
        recent_report_ids = (
            select(Report.id)
            .join(
                ReportSubmission,
                and_(
                    ReportSubmission.report_id == Report.id,
                    ReportSubmission.id == Report.current_submission_id,
                ),
            )
            .where(
                Report.team_id == activity.team_id,
                Report.status_code.in_(("approved", "submitted")),
                or_(
                    Report.customer_company_id == activity.customer_company_id,
                    Report.id.in_(deal_report_ids),
                ),
            )
            .order_by(Report.report_date.desc(), Report.id)
            .subquery()
        )
        report_rows = (
            await db.execute(
                select(
                    Report.id,
                    Report.version,
                    Report.current_submission_id,
                    ReportSubmission.submitted_at,
                    ReportSubmission.snapshot,
                )
                .join(recent_report_ids, recent_report_ids.c.id == Report.id)
                .join(
                    ReportSubmission,
                    and_(
                        ReportSubmission.report_id == Report.id,
                        ReportSubmission.id == Report.current_submission_id,
                    ),
                )
                .order_by(Report.report_date.desc(), Report.id)
            )
        ).all()
        reports = [
            [
                str(report_id),
                version,
                str(submission_id) if submission_id is not None else None,
                _isoformat(submitted_at),
            ]
            for report_id, version, submission_id, submitted_at, *_ in report_rows
        ]
        report_text = [row[4] for row in report_rows[:3]]
        if report_text:
            product_ids.update(
                await activity_documents.mentioned_product_ids(
                    db, team_id=activity.team_id, values=report_text
                )
            )
    scopes = document_processing.document_scopes(None, activity.customer_company_id, product_ids)
    files: list[list[Any]] = []
    if scopes:
        rows = (
            await db.execute(
                select(
                    Document.id,
                    Document.category_code,
                    FileRow.id,
                    FileRow.version_no,
                    FileRow.processed_at,
                )
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
            [str(document_id), category_code, str(file_id), version_no, _isoformat(processed_at)]
            for document_id, category_code, file_id, version_no, processed_at in rows
        )
    company_name = None
    if activity.customer_company_id is not None:
        company_name = (
            await db.execute(
                select(CustomerCompany.name).where(
                    CustomerCompany.id == activity.customer_company_id,
                    CustomerCompany.team_id == activity.team_id,
                )
            )
        ).scalar_one_or_none()
    contact: list[Any] = []
    if activity.customer_contact_id is not None:
        contact_row = (
            await db.execute(
                select(
                    CustomerContact.name, CustomerContact.department, CustomerContact.job_title
                ).where(CustomerContact.id == activity.customer_contact_id)
            )
        ).one_or_none()
        contact = [] if contact_row is None else list(contact_row)
    # 첫 미팅 여부(briefing_mode)는 이 미팅보다 앞선 일정이 있는지로 정해진다.
    has_prior_meeting = False
    if activity.customer_company_id is not None:
        has_prior_meeting = (
            await db.execute(
                select(Activity.id)
                .where(
                    Activity.team_id == activity.team_id,
                    Activity.customer_company_id == activity.customer_company_id,
                    Activity.deleted_at.is_(None),
                    Activity.starts_at < activity.starts_at,
                )
                .limit(1)
            )
        ).scalar_one_or_none() is not None
    support_requests: list[list[Any]] = []
    if activity.customer_company_id is not None:
        support_conditions = [
            SupportRequest.team_id == activity.team_id,
            SupportRequest.customer_company_id == activity.customer_company_id,
            SupportRequest.deleted_at.is_(None),
        ]
        # 브리핑 입력과 같은 규칙이다(contract_schedule_snapshots._briefing_support_requests).
        if member is not None and member.role_code == "member":
            support_conditions.append(SupportRequest.assignee_member_id == member.id)
        support_rows = (
            await db.execute(
                select(
                    SupportRequest.id,
                    SupportRequest.title,
                    SupportRequest.is_urgent,
                    SupportRequest.status_code,
                    SupportRequest.occurred_at,
                    SupportRequest.updated_at,
                    func.count(SupportResponse.id),
                    func.max(SupportResponse.responded_at),
                )
                .outerjoin(SupportResponse, SupportResponse.support_request_id == SupportRequest.id)
                .where(*support_conditions)
                .group_by(SupportRequest.id)
            )
        ).all()
        support_requests = sorted(
            [
                str(request_id),
                title,
                is_urgent,
                status_code,
                _isoformat(occurred_at),
                _isoformat(updated_at),
                response_count,
                _isoformat(last_responded_at),
            ]
            for (
                request_id,
                title,
                is_urgent,
                status_code,
                occurred_at,
                updated_at,
                response_count,
                last_responded_at,
            ) in support_rows
        )
    payload = {
        "activity": [
            str(activity.customer_company_id) if activity.customer_company_id else None,
            str(activity.customer_contact_id) if activity.customer_contact_id else None,
            _isoformat(activity.starts_at),
            _isoformat(activity.ends_at),
            activity.title,
            activity.location,
            activity.note,
            has_prior_meeting,
        ],
        "company": company_name,
        "contact": contact,
        "deals": deals,
        "products": sorted(str(value) for value in product_ids),
        "files": files,
        "reports": reports,
        "support_requests": support_requests,
    }
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()
