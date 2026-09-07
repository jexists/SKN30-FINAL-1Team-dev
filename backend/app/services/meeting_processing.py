"""미팅 한 번의 공통 분석과 딜별 보고서/ML 초안을 만든다."""

import asyncio
import copy
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import meeting_analysis, meeting_content_analysis, report_writing_deep
from app.models.workspace import Member
from app.schemas.meeting_content import MeetingEvidenceLedger
from app.services import meeting_context
from app.services.agent_logging import log_agent_error
from app.services.agent_stream import publish_progress
from app.services.llm import LLMError, is_transient_llm_error

PROMPT_VERSION = "meeting_processing.v14"
RUN_TIMEOUT_SECONDS = 1_200


class MeetingProcessingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reports: report_writing_deep.FreeformMeetingReports | None
    analyses: list[meeting_analysis.DealFeatureResult]
    evidence: MeetingEvidenceLedger
    errors: dict[str, str]
    context_lookups: list[dict[str, Any]] = Field(default_factory=list)


class MeetingEvidenceOutput(BaseModel):
    """공통 근거 실행의 결과. 후속 보고서/ML 실행이 그대로 재사용한다."""

    model_config = ConfigDict(extra="forbid")

    evidence: MeetingEvidenceLedger
    crm_context: dict[str, Any]
    context_lookups: list[dict[str, Any]] = Field(default_factory=list)


async def input_snapshot(
    db: AsyncSession,
    member: Member,
    source_activity_id: UUID,
    sales_deal_ids: list[UUID],
    transcript: str,
) -> dict[str, Any]:
    """사용자가 생성 버튼을 누른 시점의 원문과 권한 검증된 CRM을 고정한다."""
    context = await meeting_context.build_context(db, member, source_activity_id, sales_deal_ids)
    try:
        snapshot = meeting_content_analysis.input_snapshot(transcript, context["deals"])
    except ValueError:
        raise HTTPException(422, "meeting_transcript_invalid") from None
    snapshot["crm_context"] = context["crm_context"]
    snapshot["activity_id"] = str(source_activity_id)
    return snapshot


async def run(snapshot: dict[str, Any]) -> MeetingProcessingOutput:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + RUN_TIMEOUT_SECONDS
    prepared = await run_evidence(snapshot)
    evidence = prepared.evidence
    crm = prepared.crm_context
    additional = prepared.context_lookups

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
            if is_transient_llm_error(str(error)):
                raise
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


async def run_evidence(snapshot: dict[str, Any]) -> MeetingEvidenceOutput:
    """원문을 한 번만 읽고, 후속 독립 AgentRun에 넘길 고정 근거를 만든다."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + RUN_TIMEOUT_SECONDS
    additional: list[dict[str, Any]] = []

    def record_lookup(value: dict[str, Any]) -> None:
        item = copy.deepcopy(value)
        key = (item.get("kind"), item.get("sales_deal_id"))
        duplicate = (
            any(existing.get("kind") == item.get("kind") for existing in additional)
            if item.get("kind") == "trade_history"
            else any(
                (existing.get("kind"), existing.get("sales_deal_id")) == key
                for existing in additional
            )
        )
        if duplicate:
            return
        additional.append(item)

    async with asyncio.timeout_at(deadline):
        publish_progress("content_analysis")
        evidence = await meeting_content_analysis.run(
            {key: snapshot[key] for key in ("source", "deals", "crm_context")},
            on_lookup=record_lookup,
        )
    crm = copy.deepcopy(snapshot["crm_context"])
    crm.pop("refinement_context", None)
    company_history = next(
        (item.get("data") for item in additional if item.get("kind") == "trade_history"), None
    )
    if isinstance(company_history, dict) and isinstance(company_history.get("items"), list):
        crm["trade_history"] = copy.deepcopy(company_history["items"])
        crm["trade_history_metadata"] = {
            key: copy.deepcopy(value)
            for key, value in company_history.items()
            if key not in {"kind", "items", "sales_deal_id"}
        }
    crm["additional_context"] = [
        copy.deepcopy(item) for item in additional if item.get("kind") != "trade_history"
    ]
    return MeetingEvidenceOutput(evidence=evidence, crm_context=crm, context_lookups=additional)


async def run_report(snapshot: dict[str, Any]) -> report_writing_deep.FreeformMeetingReports:
    evidence = MeetingEvidenceLedger.model_validate(snapshot["evidence"])
    return await report_writing_deep.run(
        report_writing_deep.ReportWritingInput(
            transcript=snapshot["source"]["transcript"],
            evidence=evidence,
            crm_context=copy.deepcopy(snapshot.get("crm_context") or {}),
        )
    )


async def run_analysis(snapshot: dict[str, Any]) -> list[meeting_analysis.DealFeatureResult]:
    evidence = MeetingEvidenceLedger.model_validate(snapshot["evidence"])
    return await meeting_analysis.run_for_deals(
        evidence,
        copy.deepcopy(snapshot.get("crm_context") or {}),
        timeout=RUN_TIMEOUT_SECONDS,
    )
