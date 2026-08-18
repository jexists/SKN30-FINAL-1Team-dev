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
Password = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    password: Password


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    display_name: str
    role_code: Literal["member", "manager"]
    job_title: str | None
