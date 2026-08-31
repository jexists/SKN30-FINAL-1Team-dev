"""미팅 한 번의 공통 분석과 딜별 보고서/ML을 기존 실행·보고서 저장에 연결한다."""

import asyncio
import copy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import meeting_analysis, meeting_content_analysis, report_writing_deep
from app.db.session import get_sessionmaker
from app.models.agent import AgentRun
from app.models.content import Report
from app.models.workspace import Member
from app.schemas.meeting_content import (
    MeetingContentAnalysisOutput,
    MeetingContentInput,
    MeetingEvidenceLedger,
    SegmentAssignment,
    build_evidence_ledger,
)
from app.services import meeting_context
from app.services.agent_logging import log_agent_error
from app.services.agent_stream import publish_progress
from app.services.llm import LLMError

PROMPT_VERSION = "meeting_processing.v5"
RUN_TIMEOUT_SECONDS = 1_200


class MeetingProcessingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reports: report_writing_deep.FreeformMeetingReports | None
    analyses: list[meeting_analysis.DealFeatureResult]
    evidence: MeetingEvidenceLedger
    errors: dict[str, str]
    context_lookups: list[dict[str, Any]] = Field(default_factory=list)


def _same_meeting(reports: list[Report]) -> None:
    first = reports[0]
    if (
        any(report.report_kind != "meeting" or not report.sales_deal_id for report in reports)
        or not first.source_activity_id
        or any(report.source_activity_id != first.source_activity_id for report in reports)
        or any(report.transcript != first.transcript for report in reports)
        or len({report.sales_deal_id for report in reports}) != len(reports)
    ):
        raise HTTPException(422, "meeting_reports_mismatch")


async def input_snapshot(
    db: AsyncSession,
    member: Member,
    reports: list[Report],
    parent: AgentRun | None = None,
    overrides: list[SegmentAssignment] | None = None,
) -> dict[str, Any]:
    """이미 접근 권한을 확인한 딜 보고서 N개에서 원문 한 벌과 CRM을 고정한다."""
    _same_meeting(reports)
    first = reports[0]
    context = await meeting_context.build_context(
        db, member, first.source_activity_id, [report.sales_deal_id for report in reports]
    )
    try:
        snapshot = meeting_content_analysis.input_snapshot(first.transcript, context["deals"])
    except ValueError:
        raise HTTPException(422, "meeting_transcript_invalid") from None
    snapshot["crm_context"] = context["crm_context"]
    snapshot["activity_id"] = str(first.source_activity_id)
    snapshot["team_id"] = str(member.team_id)
    snapshot["report_versions"] = [
        {
            "id": str(report.id),
            "sales_deal_id": str(report.sales_deal_id),
            "updated_at": report.updated_at.isoformat(),
        }
        for report in reports
    ]
    snapshot["assignment_overrides"] = [item.model_dump(mode="json") for item in overrides or []]
    if parent is not None:
        if any(
            (report.source_snapshot or {}).get("meeting_run_id") != str(parent.id)
            for report in reports
        ):
            raise HTTPException(409, "meeting_assignment_stale")
        evidence = MeetingEvidenceLedger.model_validate(parent.output_snapshot["evidence"])
        source = MeetingContentInput.model_validate(snapshot["source"])
        parent_source = parent.input_snapshot["source"]
        if (
            parent.input_snapshot["activity_id"] != str(first.source_activity_id)
            or source.transcript != parent_source["transcript"]
            or set(source.selected_deal_ids) != set(evidence.selected_deal_ids)
        ):
            raise HTTPException(409, "meeting_assignment_source_changed")
        unresolved = {
            item.segment.segment_id
            for item in evidence.items
            if item.applicability.scope in {"unresolved", "out_of_scope"}
        }
        for item in overrides or []:
            if item.segment_id not in unresolved or item.applicability.scope != "deal":
                raise HTTPException(422, "meeting_assignment_not_unresolved")
            if not set(item.applicability.deal_ids) <= set(evidence.selected_deal_ids):
                raise HTTPException(422, "meeting_assignment_deal_not_selected")
        snapshot["parent_evidence"] = evidence.model_dump(mode="json")
        snapshot["parent_context_lookups"] = parent.output_snapshot.get("context_lookups", [])
    return snapshot


async def run(snapshot: dict[str, Any], member_id: UUID) -> MeetingProcessingOutput:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + RUN_TIMEOUT_SECONDS
    additional: list[dict[str, Any]] = copy.deepcopy(snapshot.get("parent_context_lookups", []))
    selected = [UUID(value) for value in snapshot["source"]["selected_deal_ids"]]

    async def lookup(kind: str, sales_deal_id: UUID) -> dict[str, Any]:
        if kind == "previous_reports" and sales_deal_id in selected:
            for history in snapshot["crm_context"].get("previous_reports", []):
                if history["sales_deal_id"] == str(sales_deal_id):
                    # 빈 이력도 이미 조회한 결과다. 실행 중 최신 DB 값으로 바꾸지 않는다.
                    if not any(
                        item["kind"] == kind and item["sales_deal_id"] == str(sales_deal_id)
                        for item in additional
                    ):
                        additional.append(
                            {
                                "kind": kind,
                                "sales_deal_id": str(sales_deal_id),
                                "data": copy.deepcopy(history),
                            }
                        )
                    return copy.deepcopy(history)
        # 도구마다 짧은 별도 세션. LLM을 기다리는 동안 DB 연결을 잡고 있지 않는다.
        async with get_sessionmaker()() as db:
            member = await db.get(Member, member_id)
            if member is None or not member.active or str(member.team_id) != snapshot["team_id"]:
                raise LLMError("meeting_context_access_denied")
            value = await meeting_context.load_extra_context(
                db, member, UUID(snapshot["activity_id"]), selected, kind, sales_deal_id
            )
        additional.append({"kind": kind, "sales_deal_id": str(sales_deal_id), "data": value})
        return value

    async with asyncio.timeout_at(deadline):
        publish_progress("content_analysis")
        if snapshot.get("parent_evidence") is not None:
            # 같은 원문 버전의 기존 분류에 재배정만 적용한다. 다른 구간은 재추측하지 않는다.
            prior = MeetingEvidenceLedger.model_validate(snapshot["parent_evidence"])
            replacements = {
                item["segment_id"]: item["applicability"]
                for item in snapshot["assignment_overrides"]
            }
            evidence = build_evidence_ledger(
                MeetingContentInput.model_validate(snapshot["source"]),
                MeetingContentAnalysisOutput(
                    assignments=[
                        {
                            "segment_id": item.segment.segment_id,
                            "applicability": replacements.get(
                                item.segment.segment_id, item.applicability.model_dump(mode="json")
                            ),
                        }
                        for item in prior.items
                    ]
                ),
            )
        else:
            evidence = await meeting_content_analysis.run(
                {key: snapshot[key] for key in ("source", "deals", "crm_context")}, lookup=lookup
            )
    crm = {**snapshot["crm_context"], "additional_context": additional}

    async def write_reports():
        try:
            publish_progress("report_writing")
            async with asyncio.timeout_at(deadline):
                output = await report_writing_deep.run(
                    report_writing_deep.ReportWritingInput(
                        transcript=snapshot["source"]["transcript"],
                        evidence=evidence,
                        crm_context=crm,
                    )
                )
                publish_progress("report_complete")
                return output, {}
        except TimeoutError as error:
            log_agent_error(
                error, stage="meeting_processing.report", error_code="report_agent_timeout"
            )
            return None, {"report_writing": "report_agent_timeout"}
        except LLMError as error:
            log_agent_error(error, stage="meeting_processing.report")
            return None, {"report_writing": str(error)}

    async def analyze_deals():
        publish_progress("features")
        result = await meeting_analysis.run_for_deals(
            evidence, crm, timeout=max(0.0, deadline - loop.time())
        )
        publish_progress("analysis_complete")
        return result

    tasks = [asyncio.create_task(write_reports()), asyncio.create_task(analyze_deals())]
    try:
        written, analyses = await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return MeetingProcessingOutput(
        reports=written[0],
        analyses=analyses,
        evidence=evidence,
        errors=written[1],
        context_lookups=additional,
    )


async def _locked_run(db: AsyncSession, member: Member, run_id: UUID) -> AgentRun:
    conditions = [AgentRun.id == run_id, AgentRun.team_id == member.team_id]
    if member.role_code == "member":
        conditions.append(AgentRun.requested_by_member_id == member.id)
    run = (
        await db.execute(select(AgentRun).where(*conditions).with_for_update())
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "agent_run_not_found")
    if run.agent_code != "meeting_processing" or run.status_code != "completed":
        raise HTTPException(409, "meeting_run_not_completed")
    return run


async def _locked_reports(db: AsyncSession, member: Member, run: AgentRun) -> list[Report]:
    from app.api.reports import _locked_report

    reports = [
        await _locked_report(db, member, UUID(item["id"]))
        for item in sorted(run.input_snapshot["report_versions"], key=lambda item: item["id"])
    ]
    _same_meeting(reports)
    versions = {item["id"]: item for item in run.input_snapshot["report_versions"]}
    for report in reports:
        if report.status_code not in {"draft", "changes_requested"}:
            raise HTTPException(409, "report_not_editable")
        if (
            str(report.source_activity_id) != run.input_snapshot["activity_id"]
            or str(report.sales_deal_id) != versions[str(report.id)]["sales_deal_id"]
            or report.transcript != run.input_snapshot["source"]["transcript"]
        ):
            raise HTTPException(409, "meeting_source_changed")
    return reports


async def _commit_reports(db: AsyncSession, member: Member, reports: list[Report]):
    from app.api.reports import _detail

    await db.flush()
    output = [await _detail(db, member, report.id) for report in reports]
    await db.commit()
    return output


async def apply(db: AsyncSession, member: Member, run_id: UUID):
    """완료된 제안을 한 번만 원자적으로 저장. 실행 중 수정된 문서는 덮어쓰지 않는다."""
    try:
        run = await _locked_run(db, member, run_id)
        reports = await _locked_reports(db, member, run)
        applied = [
            (report.source_snapshot or {}).get("meeting_run_id") == str(run_id)
            for report in reports
        ]
        if all(applied):
            return await _commit_reports(db, member, reports)
        if any(applied):
            raise HTTPException(409, "meeting_run_partially_applied")
        versions = {
            item["id"]: item["updated_at"] for item in run.input_snapshot["report_versions"]
        }
        if any(report.updated_at.isoformat() != versions[str(report.id)] for report in reports):
            raise HTTPException(409, "meeting_report_changed")
        result = MeetingProcessingOutput.model_validate(run.output_snapshot)
        selected = {report.sales_deal_id for report in reports}
        if set(result.evidence.selected_deal_ids) != selected:
            raise HTTPException(409, "meeting_result_deals_mismatch")
        if result.reports:
            report_writing_deep.validate_reports(
                report_writing_deep.ReportWritingInput(
                    transcript=run.input_snapshot["source"]["transcript"],
                    evidence=result.evidence,
                ),
                result.reports,
            )
        drafts = (
            {item.sales_deal_id: item for item in result.reports.deal_reports}
            if result.reports
            else {}
        )
        analyses = {item.sales_deal_id: item for item in result.analyses}
        if set(analyses) != selected or len(analyses) != len(result.analyses):
            raise HTTPException(409, "meeting_analysis_deals_mismatch")
        now = datetime.now(UTC)
        shared = {
            "run_id": str(run_id),
            "revision": str(uuid4()),
            "common_report": result.reports.common_report.model_dump(mode="json")
            if result.reports and result.reports.common_report
            else None,
            "unassigned_report": result.reports.unassigned_report.model_dump(mode="json")
            if result.reports and result.reports.unassigned_report
            else None,
        }
        if result.reports is None:
            drafts = {}
            # 작성 실패여도 미분류 원문은 화면/저장/일일보고에서 사라지지 않는다.
            for name, scopes in (
                ("common_report", report_writing_deep.COMMON_SCOPES),
                ("unassigned_report", report_writing_deep.UNASSIGNED_SCOPES),
            ):
                items = [
                    item for item in result.evidence.items if item.applicability.scope in scopes
                ]
                if items:
                    shared[name] = {
                        "body": "\n\n".join(item.segment.text for item in items),
                        "evidence_ids": [item.segment.segment_id for item in items],
                    }
        for name in ("common_report", "unassigned_report"):
            edited = [
                prior
                for report in reports
                if isinstance(prior := (report.content.get("meeting_shared") or {}).get(name), dict)
                and prior.get("edited")
            ]
            if edited:
                if len({item["body"] for item in edited}) != 1:
                    raise HTTPException(409, "meeting_notes_conflict")
                proposed = shared[name]
                # 사람이 쓴 공통 메모도 딜 본문과 동일하게 보호한다. 새 AI안은 별도 제안이다.
                shared[name] = {
                    "body": edited[0]["body"],
                    "evidence_ids": proposed["evidence_ids"] if proposed else [],
                    "edited": True,
                    "ai_body": proposed["body"] if proposed else None,
                }
        for report in reports:
            content = copy.deepcopy(report.content)
            draft = drafts.get(report.sales_deal_id)
            if draft:
                fields = report.template_snapshot.get("fields", [])
                field_id = (
                    "body"
                    if any(f.get("id") == "body" for f in fields)
                    else next(
                        (
                            f["id"]
                            for f in fields
                            if f.get("type") == "textarea" and f.get("aiFilled") is not False
                        ),
                        None,
                    )
                    or next((f["id"] for f in fields if f.get("aiFilled") is True), None)
                )
                generated = {field_id or "body": draft.body}
                current = content.get("values", {})
                if field_id is not None and not any(
                    isinstance(value, str) and value.strip() for value in current.values()
                ):
                    content["values"] = generated
                content.update(
                    ai_values=generated,
                    ai_evidence=" · ".join(draft.evidence_ids),
                    ai_generated_at=now.isoformat(),
                )
            content["meeting_shared"] = copy.deepcopy(shared)
            report.content = content
            report.source_snapshot = {
                "meeting_run_id": str(run_id),
                "evidence": result.evidence.model_dump(mode="json"),
            }
            analysis = analyses[report.sales_deal_id]
            report.ai_evidence = {
                "meeting_run_id": str(run_id),
                "deal_assessment": analysis.assessment.model_dump(mode="json")
                if analysis.assessment
                else None,
                "features": analysis.features.model_dump(mode="json")
                if analysis.features
                else None,
                "analysis_error": analysis.error,
                "report_error": result.errors.get("report_writing"),
            }
            report.updated_at = now
        return await _commit_reports(db, member, reports)
    except Exception:
        await db.rollback()
        raise


async def update_notes(
    db: AsyncSession,
    member: Member,
    run_id: UUID,
    common_body: str | None,
    unassigned_body: str | None,
    expected_revision: UUID,
):
    """미팅 공통 편집본을 그룹 전체에 저장. AI 원문 근거와 분석 결과는 변경하지 않는다."""
    try:
        run = await _locked_run(db, member, run_id)
        reports = await _locked_reports(db, member, run)
        for report in reports:
            if (report.source_snapshot or {}).get("meeting_run_id") != str(run_id):
                raise HTTPException(409, "meeting_notes_stale")
            if (report.content.get("meeting_shared") or {}).get("revision") != str(
                expected_revision
            ):
                raise HTTPException(409, "meeting_notes_changed")
        revision = str(uuid4())
        for report in reports:
            content = copy.deepcopy(report.content)
            shared = content["meeting_shared"]
            shared["revision"] = revision
            for name, body in (
                ("common_report", common_body),
                ("unassigned_report", unassigned_body),
            ):
                if shared.get(name) is not None:
                    if body is None or not body.strip():
                        raise HTTPException(422, "meeting_notes_empty")
                    if shared[name]["body"] != body:
                        shared[name]["edited"] = True
                    shared[name]["body"] = body
                elif body:
                    raise HTTPException(422, "meeting_notes_without_evidence")
            report.content = content
            report.updated_at = datetime.now(UTC)
        return await _commit_reports(db, member, reports)
    except Exception:
        await db.rollback()
        raise
