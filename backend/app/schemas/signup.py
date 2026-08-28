from pydantic import BaseModel, ConfigDict

from app.schemas.auth import Email


class AccountRequest(BaseModel):
    """계정을 받고 싶은 사람이 남기는 것. 연락할 이메일 하나면 된다."""

    model_config = ConfigDict(extra="forbid")

    email: Email
