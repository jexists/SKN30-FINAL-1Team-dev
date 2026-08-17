from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

LoginId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        strict=True,
        min_length=1,
        max_length=254,
    ),
]
Password = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login_id: LoginId
    password: Password


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    role_code: Literal["member", "manager"]
    job_title: str | None
