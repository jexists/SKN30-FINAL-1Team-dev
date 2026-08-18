from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SearchQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=100),
]

# team 은 수신자가 없는 팀 공지, personal 은 로그인한 사람에게 온 지시다.
NoticeScope = Literal["team", "personal"]


class NoticeRead(BaseModel):
    id: UUID
    scope: NoticeScope
    author_member_id: UUID
    author_display_name: str
    recipient_member_id: UUID | None
    tag: str | None
    title: str
    body: str
    # image_storage_key 는 내부 저장소 주소라 응답하지 않는다. 대체 텍스트만 내보낸다.
    image_alt: str | None
    published_at: datetime
    due_at: datetime | None
    due_text: str | None


class NoticePage(BaseModel):
    items: list[NoticeRead]
    skip: int
    limit: int
    total: int
    has_more: bool
    next_skip: int | None


class NoticePageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: NoticeScope | None = None
    q: SearchQuery | None = None
    published_from: datetime | None = None
    published_to: datetime | None = None
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=100)

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if self.published_from is not None and self.published_to is not None:
            if self.published_to < self.published_from:
                raise ValueError("invalid_notice_range")
        return self
