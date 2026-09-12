"""기간 보고서의 동결 입력 검증과 하위 제출본 묶음."""

import copy
from collections.abc import Callable
from datetime import date
from typing import Any

from app.models.content import Report
from app.services.llm import LLMError

PERIOD_KINDS = {"daily": "일일", "weekly": "주간", "monthly": "월간"}


def input_snapshot(report: Report, guidance: str | None) -> dict[str, Any]:
    """백그라운드 실행이 사용할 보고서 입력을 실행 시점 값으로 고정한다."""
    return {
        "report_kind": report.report_kind,
        "report_date": report.report_date.isoformat(),
        "period_start": report.period_start.isoformat() if report.period_start else None,
        "period_end": report.period_end.isoformat() if report.period_end else None,
        "template_snapshot": report.template_snapshot,
        "content": report.content,
        "transcript": report.transcript,
        "guidance": guidance,
    }


def build_source(snapshot: dict[str, Any]) -> dict[str, Any]:
    """검증된 보고서 스냅샷을 복사하고 실제 AI 작성 대상 필드를 확정한다."""
    kind = snapshot.get("report_kind")
    if kind not in PERIOD_KINDS:
        raise LLMError("period_report_kind_invalid")
    if kind != "daily":
        try:
            start = date.fromisoformat(snapshot["period_start"])
            end = date.fromisoformat(snapshot["period_end"])
            if end < start:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise LLMError("period_report_period_invalid") from None

    content = snapshot.get("content") or {}
    if not isinstance(content, dict):
        raise LLMError("period_report_content_invalid")
    report_sources = snapshot.get("report_sources", {"reports": [], "meetings": []})
    if not isinstance(report_sources, dict):
        raise LLMError("period_report_sources_invalid")
    activities = report_sources.get("activities", [])
    if not isinstance(activities, list) or (kind != "daily" and activities):
        raise LLMError("period_report_source_activities_invalid")
    attachments = snapshot.get("attachments", [])
    if not isinstance(attachments, list):
        raise LLMError("period_report_attachments_invalid")
    values = content.get("values")
    if values is not None and (
        not isinstance(values, dict)
        or set(values) - {"body"}
        or ("body" in values and not isinstance(values["body"], str))
    ):
        raise LLMError("period_report_values_invalid")

    source = copy.deepcopy(
        {
            "report_kind": kind,
            "report_date": snapshot["report_date"],
            "period_start": snapshot.get("period_start"),
            "period_end": snapshot.get("period_end"),
            "current_body": (values or {}).get("body"),
            "transcript": snapshot.get("transcript"),
            "guidance": snapshot.get("guidance"),
            "activities": activities,
            "attachments": [
                {"id": item.get("id"), "name": item.get("name"), "extract": item["extract"]}
                for item in attachments
                if isinstance(item, dict) and isinstance(item.get("extract"), str)
            ],
            "report_sources": report_sources,
        }
    )
    template = snapshot.get("template_snapshot")
    fields = template.get("fields") if isinstance(template, dict) else None
    if (
        not isinstance(fields, list)
        or len(fields) != 1
        or not isinstance(fields[0], dict)
        or fields[0].get("id") != "body"
    ):
        raise LLMError("period_report_template_invalid")
    return source


def source_units(source: dict[str, Any]) -> list[dict[str, Any]]:
    """일일은 미팅 묶음, 주간·월간은 바로 아래 제출 본문만 전달한다."""
    units: list[dict[str, Any]] = []

    def add(source_type: str, content: dict[str, Any]) -> None:
        unit = {
            "source_id": f"{source_type}:{len(units) + 1}",
            "source_type": source_type,
            "content": content,
        }
        units.append(unit)

    report_sources = source["report_sources"]
    reports = report_sources.get("reports", [])
    meetings = report_sources.get("meetings", [])
    if not isinstance(reports, list) or not isinstance(meetings, list):
        raise LLMError("period_report_sources_invalid")

    if source["report_kind"] == "daily":
        bundles: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for meeting in meetings:
            if not isinstance(meeting, dict):
                raise LLMError("period_report_sources_invalid")
            identity = meeting.get("submission_id")
            if not isinstance(identity, str) or not identity:
                raise LLMError("period_report_sources_invalid")
            bundle = bundles.setdefault(identity, {"deal_reports": [], "meeting_context": []})
            if bundle["meeting_context"]:
                raise LLMError("period_report_sources_invalid")
            bundle["meeting_context"].append(meeting)
        for report in reports:
            if not isinstance(report, dict) or report.get("report_kind") != "meeting":
                raise LLMError("period_report_sources_invalid")
            identity = report.get("submission_id")
            if not isinstance(identity, str) or not identity:
                raise LLMError("period_report_sources_invalid")
            if identity not in bundles:
                raise LLMError("period_report_sources_invalid")
            bundles[identity]["deal_reports"].append(report)
        for bundle in bundles.values():
            add("meeting_bundle", bundle)
    else:
        if meetings:
            raise LLMError("period_report_sources_invalid")
        expected_kind = "daily" if source["report_kind"] == "weekly" else "weekly"
        seen = set()
        for report in reports:
            if not isinstance(report, dict) or report.get("report_kind") != expected_kind:
                raise LLMError("period_report_sources_invalid")
            identity = report.get("submission_id")
            if not isinstance(identity, str) or not identity or identity in seen:
                raise LLMError("period_report_sources_invalid")
            seen.add(identity)
            add("child_submission", {"reports": [report]})
    for activity in source["activities"]:
        if not isinstance(activity, dict):
            raise LLMError("period_report_source_activities_invalid")
        add("direct_activity", {"activity": activity})
    for attachment in source["attachments"]:
        add("attachment", {"attachment": attachment})
    return units


def run_context(source: dict[str, Any]) -> dict[str, Any]:
    return {
        key: source[key]
        for key in (
            "report_kind",
            "report_date",
            "period_start",
            "period_end",
            "current_body",
            "transcript",
            "guidance",
        )
    }


def create_period_tools(
    payload: dict[str, Any],
    *,
    scope_access: Callable[[str, object], bool] | None = None,
) -> list:
    """서버가 권한/계층/기간을 검증한 제출본과 작성 맥락만 읽는다."""
    source = copy.deepcopy(payload.get("source", payload))

    def read_report_context() -> dict[str, Any]:
        """집계 기간, 기존 본문, 추가 메모와 사용자 작성 지시를 읽는다."""
        return copy.deepcopy(source["run_context"])

    def read_report_sources(source_id: str | None = None) -> list[dict[str, Any]]:
        """동결된 제출/활동/첨부 자료를 읽는다. 생략하면 전체, ID는 정확히 일치해야 한다."""
        units = source["source_units"]
        allowed = (
            scope_access("read_report_sources", source_id)
            if scope_access is not None
            else source_id is None or any(unit["source_id"] == source_id for unit in units)
        )
        if not allowed:
            raise PermissionError("report_source_not_allowed")
        if source_id is None:
            return copy.deepcopy(units)
        selected = [unit for unit in units if unit["source_id"] == source_id]
        if not selected:
            raise PermissionError("report_source_not_allowed")
        return copy.deepcopy(selected)

    return [read_report_context, read_report_sources]
