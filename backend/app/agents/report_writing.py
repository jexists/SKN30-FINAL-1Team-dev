"""프론트 보고서 양식에 맞춰 필드별 초안을 생성하는 에이전트."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.content import Report
from app.services.llm import generate_structured

# 프롬프트는 라우터가 아니라 이 에이전트 파일에서만 관리한다.
# 내용을 바꾸면 실행 이력에서 구분할 수 있도록 버전도 함께 올린다.
PROMPT_VERSION = "report_writing.v3"

SYSTEM_PROMPT = (
    "너는 한국어 영업 보고서 초안을 작성하는 AI다. "
    "제공된 보고서 양식, 현재 작성값, 미팅 기록, 작성자 요청만 근거로 사용하고 "
    "없는 사실을 지어내지 마라. "
    "양식의 각 항목을 fields 에 한 번씩 넣고 field_id 는 양식의 id 를 그대로 사용하라. "
    "근거가 없으면 value 를 빈 문자열로 두고, 전체 결과를 summary 로 짧게 요약하라. "
    "JSON 만 출력한다."
)


class ReportDraftField(BaseModel):
    """프론트 양식의 입력칸 하나에 넣을 초안."""

    model_config = ConfigDict(extra="forbid")

    field_id: str = Field(min_length=1, max_length=128)
    value: str = Field(max_length=5_000)


class ReportDraftOutput(BaseModel):
    """프론트가 입력칸별 값으로 변환할 수 있는 LLM 출력."""

    model_config = ConfigDict(extra="forbid")

    fields: list[ReportDraftField] = Field(max_length=50)
    summary: str = Field(default="", max_length=2_000)


def input_snapshot(report: Report, guidance: str | None) -> dict[str, Any]:
    """백그라운드 실행이 사용할 보고서 입력을 실행 시점 값으로 고정한다."""
    return {
        "report_kind": report.report_kind,
        "report_date": report.report_date.isoformat(),
        "sales_deal_id": str(report.sales_deal_id) if report.sales_deal_id else None,
        "template_snapshot": report.template_snapshot,
        "content": report.content,
        "transcript": report.transcript,
        "guidance": guidance,
    }


def _prompt_input(snapshot: dict[str, Any]) -> str:
    """저장된 입력을 모델이 읽을 수 있는 짧고 명시적인 문자열로 만든다."""
    template = json.dumps(snapshot["template_snapshot"], ensure_ascii=False, separators=(",", ":"))
    # 딜별 보고서에 다른 선택 딜 목록을 싣지 않는다. target은 정규 FK 하나뿐이다.
    content_value = dict(snapshot["content"])
    content_value.pop("sales_deal_ids", None)
    content_value.pop("sales_deals", None)
    content = json.dumps(content_value, ensure_ascii=False, separators=(",", ":"))
    lines = [
        f"보고서 종류: {snapshot['report_kind']}",
        f"보고 일자: {snapshot['report_date']}",
        f"보고서 양식(JSON): {template}",
        f"현재 작성값(JSON): {content}",
    ]
    if snapshot.get("sales_deal_id"):
        lines.insert(2, f"대상 딜 ID: {snapshot['sales_deal_id']}")
    if snapshot.get("transcript"):
        lines.append(f"미팅 기록: {snapshot['transcript']}")
    if snapshot.get("guidance"):
        lines.append(f"작성자 요청: {snapshot['guidance']}")
    return "\n".join(lines)


async def run(snapshot: dict[str, Any]) -> ReportDraftOutput:
    """저장된 입력으로 LLM 을 호출하는 보고서 작성 에이전트의 단일 진입점."""
    return await generate_structured(
        instructions=SYSTEM_PROMPT,
        input_text=_prompt_input(snapshot),
        schema=ReportDraftOutput,
        schema_name="report_draft",
    )
