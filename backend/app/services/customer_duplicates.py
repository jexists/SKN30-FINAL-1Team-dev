"""고객 중복 판단을 한곳에서 정한다.

직접등록·명함등록·사업자등록증등록·엑셀등록이 모두 이 기준을 쓴다. 등록 방식마다 다른
기준을 두면 한쪽으로 들어온 사람이 다른 쪽에서 새 고객이 된다.

같은 사람으로 보는 조건은 세 가지 중 하나다.

- 전화번호가 숫자만 남겼을 때 같다
- 이메일이 대소문자·공백을 무시하고 같다
- 회사명과 고객명이 둘 다 같다

고객명 하나로는 판단하지 않는다. 같은 회사에 동명이인이 있을 수 있고, 회사가 다르면
같은 이름이라도 다른 사람이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CustomerCompany, CustomerContact
from app.models.workspace import Member


@dataclass(frozen=True)
class DuplicateProbe:
    """중복인지 물어볼 값. 등록 방식이 무엇이든 여기까지 좁혀서 들어온다."""

    company_name: str = ""
    name: str = ""
    phone: str = ""
    email: str = ""


@dataclass(frozen=True)
class DuplicateMatch:
    """겹친 기존 고객. 화면이 "이 정보로 고칠까요" 를 물으려면 전 필드가 필요하다."""

    contact_id: UUID
    company_id: UUID
    company_name: str
    name: str
    department: str | None
    job_title: str | None
    email: str | None
    phone: str
    memo: str | None
    visited: bool
    matched_by: list[str]


def phone_digits(value: str | None) -> str:
    """전화번호에서 숫자만 남긴다. 010-1234-5678 과 01012345678 은 같은 번호다."""
    return re.sub(r"[^0-9]", "", value or "")


def normalized_email(value: str | None) -> str:
    return (value or "").strip().casefold()


def normalized_text(value: str | None) -> str:
    return (value or "").strip().casefold()


def duplicate_keys(probe: DuplicateProbe) -> set[str]:
    """같은 요청 안에서 이미 나온 사람인지 볼 때 쓰는 열쇠.

    DB 조회와 같은 세 조건을 문자열로 만든 것이다. 하나라도 겹치면 같은 사람으로 본다.
    값이 빈 항목은 열쇠를 만들지 않는다. 빈 값끼리 겹쳤다고 볼 수는 없다.
    """
    keys: set[str] = set()
    digits = phone_digits(probe.phone)
    if digits:
        keys.add(f"phone:{digits}")
    email = normalized_email(probe.email)
    if email:
        keys.add(f"email:{email}")
    name = normalized_text(probe.name)
    company = normalized_text(probe.company_name)
    if name and company:
        keys.add(f"name_company:{name}|{company}")
    return keys


def match_labels(
    probe: DuplicateProbe,
    *,
    contact: CustomerContact,
    company_name: str,
) -> list[str]:
    """후보가 어떤 값으로 겹쳤는지 설명한다."""
    labels: list[str] = []
    digits = phone_digits(probe.phone)
    if digits and digits == phone_digits(contact.phone):
        labels.append("phone")
    email = normalized_email(probe.email)
    if email and email == normalized_email(contact.email):
        labels.append("email")
    name = normalized_text(probe.name)
    company = normalized_text(probe.company_name)
    if (
        name
        and company
        and name == normalized_text(contact.name)
        and company == normalized_text(company_name)
    ):
        labels.append("name_company")
    return labels


async def find_duplicates(
    db: AsyncSession,
    *,
    member: Member,
    probe: DuplicateProbe,
    exclude_contact_id: UUID | None = None,
    limit: int = 10,
) -> list[DuplicateMatch]:
    """같은 팀의 살아 있는 고객 중 같은 사람으로 볼 후보만 돌려준다. 저장·병합은 하지 않는다."""
    conditions = []
    digits = phone_digits(probe.phone)
    if digits:
        conditions.append(func.regexp_replace(CustomerContact.phone, r"[^0-9]", "", "g") == digits)
    email = normalized_email(probe.email)
    if email:
        conditions.append(func.lower(CustomerContact.email) == email)
    name = normalized_text(probe.name)
    company = normalized_text(probe.company_name)
    if name and company:
        conditions.append(
            (func.lower(CustomerContact.name) == name)
            & (func.lower(CustomerCompany.name) == company)
        )
    if not conditions:
        return []

    scope = [
        # 지운 고객은 중복 후보로 내놓지 않는다. 다시 등록하려는 참이다.
        CustomerContact.deleted_at.is_(None),
        CustomerCompany.team_id == member.team_id,
        or_(*conditions),
    ]
    if exclude_contact_id is not None:
        scope.append(CustomerContact.id != exclude_contact_id)

    result = await db.execute(
        select(CustomerContact, CustomerCompany)
        .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
        .where(*scope)
        .limit(limit)
    )
    matches: list[DuplicateMatch] = []
    for contact, company_row in result.all():
        matched_by = match_labels(probe, contact=contact, company_name=company_row.name)
        # SQL 의 대소문자 처리와 파이썬의 casefold 가 어긋나는 값이 있을 수 있다.
        # 어디가 겹쳤는지 말할 수 없는 후보는 내놓지 않는다.
        if not matched_by:
            continue
        matches.append(
            DuplicateMatch(
                contact_id=contact.id,
                company_id=contact.company_id,
                company_name=company_row.name,
                name=contact.name,
                department=contact.department,
                job_title=contact.job_title,
                email=contact.email,
                phone=contact.phone,
                memo=contact.memo,
                visited=contact.visited,
                matched_by=matched_by,
            )
        )
    return matches
