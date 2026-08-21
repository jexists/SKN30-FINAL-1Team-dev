from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.content import Report
from app.services.llm import generate_structured

PROMPT_VERSION = "report_writing.v1"

SYSTEM_PROMPT = (
    "너는 한국어 영업 보고서 초안을 쓰는 도우미다. "
    "주어진 양식 항목과 근거 자료만 사용하고 없는 사실을 지어내지 마라. "
    "각 항목마다 field_id 와 value 를 채우고, 근거가 없으면 value 를 빈 문자열로 둬라. "
    "JSON 만 출력한다."
)


class ReportDraftField(BaseModel):
    """양식 항목 하나에 대한 제안. field_id 는 template_snapshot 의 항목 id 다."""

    model_config = ConfigDict(extra="forbid")

    field_id: str = Field(min_length=1, max_length=128)
    value: str = Field(max_length=5_000)


class ReportDraftOutput(BaseModel):
    """LLM 이 돌려줘야 하는 구조. 검증에 실패하면 실행을 failed 로 남긴다."""

    model_config = ConfigDict(extra="forbid")

    fields: list[ReportDraftField] = Field(max_length=50)
    summary: str = Field(default="", max_length=2_000)


def input_snapshot(report: Report, guidance: str | None) -> dict[str, Any]:
    """실행에 실제로 쓴 값만 남긴다. 원문 전체를 복제하지 않는다."""
    return {
        "report_kind": report.report_kind,
        "report_date": report.report_date.isoformat(),
        "template_snapshot": report.template_snapshot,
        "content": report.content,
        "transcript": report.transcript,
        "guidance": guidance,
    }


def _prompt_input(snapshot: dict[str, Any]) -> str:
    lines = [
        f"보고서 종류: {snapshot['report_kind']}",
        f"보고 일자: {snapshot['report_date']}",
        f"양식: {snapshot['template_snapshot']}",
        f"현재 작성값: {snapshot['content']}",
    ]
    if snapshot.get("transcript"):
        lines.append(f"미팅 기록: {snapshot['transcript']}")
    if snapshot.get("guidance"):
        lines.append(f"작성자 요청: {snapshot['guidance']}")
    return "\n".join(lines)


async def run(snapshot: dict[str, Any]) -> ReportDraftOutput:
    """보고서 작성 에이전트 진입점."""
    return await generate_structured(
        instructions=SYSTEM_PROMPT,
        input_text=_prompt_input(snapshot),
        schema=ReportDraftOutput,
        schema_name="report_draft",
    )
