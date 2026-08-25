from datetime import date as Date
from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SearchQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=100),
]
Title = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=254),
]
Tag = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=64),
]
ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=254),
]
# 편집기가 만든 HTML. 여기서는 길이만 본다. 허용 태그는 services.html_sanitize 가 정한다.
BodyHtml = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=200_000),
]

# team 은 수신자가 없는 팀 공지, personal 은 로그인한 사람에게 온 지시다.
# 종류 컬럼(type)이 생긴 뒤로는 NOTICE/DIRECTIVE 와 1:1 이며, 기존 호출자를 위해 남겨 둔다.
NoticeScope = Literal["team", "personal"]
NoticeType = Literal["NOTICE", "DIRECTIVE"]

# 노출 순서는 팀장이 손으로 넣는다. 화면이 다루기 어려운 값이 들어오지 않게 폭을 좁힌다.
_SORT_ORDER = Field(ge=-9_999, le=9_999)


class NoticeRead(BaseModel):
    """팀원이 보는 공지 한 건."""

    id: UUID
    scope: NoticeScope
    type: NoticeType
    author_member_id: UUID
    author_display_name: str
    # 수신자가 정확히 한 명일 때만 그 사람이다. 여러 명이거나 공지면 None 이다.
    # ponytail: 수신자가 여러 명이 될 수 있게 되면서 뜻이 좁아졌다. 화면이 targets 로
    # 옮겨 간 뒤 뗀다.
    recipient_member_id: UUID | None
    tag: str | None
    title: str
    # 허용 태그만 남은 HTML. 사진 주소는 이 응답을 만들 때 서명 URL 로 바꿔 넣는다.
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


class NoticeTargetRead(BaseModel):
    id: UUID
    display_name: str


class NoticeManageListItem(BaseModel):
    """팀장 관리 목록의 한 줄.

    본문(body)을 싣지 않는다. 본문 안의 사진마다 서명 URL 을 발급해야 하는데, 목록은 한 번에
    30건이라 발급 호출이 곱절로 늘어난다. 폼을 열 때 단건 조회가 본문을 준다.
    """

    id: UUID
    type: NoticeType
    author_member_id: UUID
    author_display_name: str
    tag: str | None
    title: str
    image_alt: str | None
    published_at: datetime
    due_at: datetime | None
    due_text: str | None
    display_start_date: Date
    display_end_date: Date | None
    is_hidden: bool
    sort_order: int
    targets: list[NoticeTargetRead]
    target_member_ids: list[UUID]
    updated_at: datetime


class NoticeManageRead(NoticeManageListItem):
    """수정 폼이 채워 넣을 한 건. 목록 항목에 본문을 더한 것이다."""

    body: str


class NoticeManagePage(BaseModel):
    items: list[NoticeManageListItem]
    skip: int
    limit: int
    total: int
    has_more: bool
    next_skip: int | None


class NoticeImageRead(BaseModel):
    """올린 사진. url 은 본문에 그대로 박는 내부 참조다."""

    id: UUID
    url: str


class _WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoticeCreate(_WriteModel):
    type: NoticeType
    title: Title
    body: BodyHtml
    tag: Tag | None = None
    image_alt: ShortText | None = None
    due_at: datetime | None = None
    due_text: ShortText | None = None
    # 주지 않으면 라우터가 오늘(Asia/Seoul)로 채운다.
    display_start_date: Date | None = None
    display_end_date: Date | None = None
    is_hidden: bool = False
    sort_order: Annotated[int, _SORT_ORDER] = 0
    # DIRECTIVE 에만 쓴다. NOTICE 에 주면 거절한다.
    target_member_ids: list[UUID] | None = None

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if self.display_start_date is not None and self.display_end_date is not None:
            if self.display_end_date < self.display_start_date:
                raise ValueError("invalid_notice_display_range")
        if self.type == "NOTICE" and self.target_member_ids:
            raise ValueError("notice_cannot_have_targets")
        if self.type == "DIRECTIVE" and not self.target_member_ids:
            raise ValueError("directive_target_required")
        return self


class NoticePatch(_WriteModel):
    """보낸 항목만 바꾼다.

    종류와 수신자의 정합성은 여기서 보지 않는다. 부분 값만 오므로 바뀐 뒤의 모습을 알 수 없고,
    라우터가 기존 행과 합친 뒤에 판단한다.
    """

    type: NoticeType | None = None
    title: Title | None = None
    body: BodyHtml | None = None
    tag: Tag | None = None
    image_alt: ShortText | None = None
    due_at: datetime | None = None
    due_text: ShortText | None = None
    display_start_date: Date | None = None
    # None 을 명시하면 무기한으로 되돌린다.
    display_end_date: Date | None = None
    is_hidden: bool | None = None
    sort_order: Annotated[int, _SORT_ORDER] | None = None
    # 보내면 수신자 전체를 이 목록으로 바꾼다.
    target_member_ids: list[UUID] | None = None

    @model_validator(mode="after")
    def required_fields_cannot_be_null(self) -> Self:
        for field_name in (
            "type",
            "title",
            "body",
            "display_start_date",
            "is_hidden",
            "sort_order",
            "target_member_ids",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if self.display_start_date is not None and self.display_end_date is not None:
            if self.display_end_date < self.display_start_date:
                raise ValueError("invalid_notice_display_range")
        return self


class NoticePageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: NoticeScope | None = None
    type: NoticeType | None = None
    q: SearchQuery | None = None
    published_from: datetime | None = None
    published_to: datetime | None = None
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=30)

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if self.published_from is not None and self.published_to is not None:
            if self.published_to < self.published_from:
                raise ValueError("invalid_notice_range")
        if self.scope is not None and self.type is not None:
            wanted = "NOTICE" if self.scope == "team" else "DIRECTIVE"
            if self.type != wanted:
                raise ValueError("conflicting_notice_filter")
        return self


class NoticeManagePageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: NoticeType | None = None
    q: SearchQuery | None = None
    # 팀장 화면이라 숨긴 것도 기본으로 함께 본다. 숨겨야 고칠 수 있다.
    include_hidden: bool = True
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=30)
