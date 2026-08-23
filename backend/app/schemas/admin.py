"""어드민 계정 발급 스키마.

비밀번호는 어디에도 없다. Supabase 초대 메일이 그 자리를 대신하므로
발급하는 쪽이 비밀번호를 알 방법도, 전달할 이유도 없다.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

from app.schemas.auth import Email

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=100)
]
RoleCode = Literal["member", "manager"]

# 국세청 사업자등록번호 검증 가중치. 마지막 자리는 검증 숫자다.
_BUSINESS_NO_WEIGHTS = (1, 3, 7, 1, 3, 7, 1, 3, 5)


def _is_valid_business_no(digits: str) -> bool:
    """10자리 사업자등록번호의 검증 숫자를 확인한다.

    형식만 보면 오타 한 글자가 그대로 저장된다. 세금계산서가 걸리는 값이라
    자릿수만으로 통과시키지 않는다.
    """
    total = sum(int(d) * w for d, w in zip(digits[:9], _BUSINESS_NO_WEIGHTS, strict=True))
    total += int(digits[8]) * 5 // 10
    return (10 - total % 10) % 10 == int(digits[9])


class TeamCreate(BaseModel):
    """새로 만들 팀. 회사명·부서명은 없어도 되지만 팀명은 있어야 한다."""

    model_config = ConfigDict(extra="forbid")

    name: Name
    company_name: Name | None = None
    department: Name | None = None
    # 하이픈과 공백은 받아서 벗긴다. 저장은 숫자 10자리로만 한다.
    business_no: str | None = None

    @field_validator("business_no")
    @classmethod
    def normalize_business_no(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = "".join(ch for ch in value if not ch.isspace() and ch != "-")
        if not digits:
            return None
        if len(digits) != 10 or not digits.isdigit():
            raise ValueError("사업자등록번호는 숫자 10자리여야 합니다.")
        if not _is_valid_business_no(digits):
            raise ValueError("사업자등록번호의 검증 숫자가 맞지 않습니다.")
        return digits


class AccountCreate(BaseModel):
    """계정 하나를 발급한다. 팀은 고르거나 새로 만들거나 둘 중 하나다."""

    model_config = ConfigDict(extra="forbid")

    email: Email
    display_name: Name
    role_code: RoleCode
    team_id: UUID | None = None
    team: TeamCreate | None = None

    @model_validator(mode="after")
    def exactly_one_team(self) -> "AccountCreate":
        if (self.team_id is None) == (self.team is None):
            raise ValueError("team_id 와 team 중 정확히 하나만 보냅니다.")
        return self


class TeamMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    email: str | None
    role_code: str
    active: bool


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    company_name: str | None
    department: str | None
    business_no: str | None
    member_count: int
    members: list[TeamMemberRead]


class AccountCreated(BaseModel):
    """발급 결과. 초대 메일이 나갔다는 사실까지가 이 응답의 의미다."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    display_name: str
    email: str | None
    role_code: str
