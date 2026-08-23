from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

# Supabase Auth 가 이메일 형식을 최종 판정하므로 여기서는 길이와 정규화만 본다.
# 형식 검사를 흉내내면 두 곳의 판정이 어긋난다.
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        strict=True,
        min_length=3,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+$",
    ),
]
# 로그인에서는 길이를 막지 않는다. 막으면 비밀번호 정책이 응답으로 새어 나간다.
Password = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)]
# 새로 정하는 비밀번호에만 하한을 둔다. 나머지 정책은 Supabase 가 판정한다.
NewPassword = Annotated[str, StringConstraints(strict=True, min_length=8, max_length=256)]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    password: Password


class SetPasswordRequest(BaseModel):
    """초대·복구 링크로 받은 토큰이 곧 자격증명이다. 로그인 상태를 요구하지 않는다."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    password: NewPassword


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    display_name: str
    role_code: Literal["member", "manager"]
    job_title: str | None
    # 계정 발급 권한. member 행이 아니라 ADMIN_USER_IDS 에서 나온다.
    is_admin: bool = False
