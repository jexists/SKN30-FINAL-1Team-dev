"""기간 보고서의 생성 본문 출력 계약."""

from pydantic import BaseModel, ConfigDict, Field


class ReportDraftField(BaseModel):
    """기간 보고서의 줄글 본문 초안."""

    model_config = ConfigDict(extra="forbid")

    field_id: str = Field(min_length=1, max_length=128)
    value: str = Field(max_length=5_000)


class ReportDraftOutput(BaseModel):
    """프론트가 본문 값으로 변환할 수 있는 LLM 출력."""

    model_config = ConfigDict(extra="forbid")

    fields: list[ReportDraftField] = Field(min_length=1, max_length=50)
