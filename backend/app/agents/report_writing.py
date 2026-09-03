"""기간 보고서 입력을 동결하고 전용 작성 에이전트로 전달한다."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.content import Report
from app.services.llm import LLMError

# 프롬프트는 라우터가 아니라 이 에이전트 파일에서만 관리한다.
# 내용을 바꾸면 실행 이력에서 구분할 수 있도록 버전도 함께 올린다.
PROMPT_VERSION = "report_writing.v14"


class ReportDraftField(BaseModel):
    """기간 보고서의 줄글 본문 초안."""

    model_config = ConfigDict(extra="forbid")

    field_id: str = Field(min_length=1, max_length=128)
    value: str = Field(max_length=5_000)


class ReportDraftOutput(BaseModel):
    """프론트가 본문 값으로 변환할 수 있는 LLM 출력."""

    model_config = ConfigDict(extra="forbid")

    fields: list[ReportDraftField] = Field(min_length=1, max_length=50)


def input_snapshot(report: Report, guidance: str | None) -> dict[str, Any]:
    """백그라운드 실행이 사용할 보고서 입력을 실행 시점 값으로 고정한다."""
    return {
        "report_kind": report.report_kind,
        "report_date": report.report_date.isoformat(),
        "period_start": report.period_start.isoformat() if report.period_start else None,
        "period_end": report.period_end.isoformat() if report.period_end else None,
        "sales_deal_id": str(report.sales_deal_id) if report.sales_deal_id else None,
        "template_snapshot": report.template_snapshot,
        "content": report.content,
        "transcript": report.transcript,
        "guidance": guidance,
    }


async def run(snapshot: dict[str, Any]) -> ReportDraftOutput:
    """일일·주간·월간만 작성한다. 미팅은 통합 ``meeting_processing`` 경로를 사용한다."""
    if snapshot.get("report_kind") not in {"daily", "weekly", "monthly"}:
        raise LLMError("report_writing_kind_unsupported")
    from app.agents.period_report_writing_deep import run as run_period

    return await run_period(snapshot)
