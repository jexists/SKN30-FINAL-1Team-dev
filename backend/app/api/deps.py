"""라우터에서 공용으로 쓰는 의존성.

Annotated 별칭으로 두면 라우터 시그니처가 짧아지고,
Depends() 를 인자 기본값에 직접 쓰지 않게 되어 린터(B008)와도 맞습니다.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import read_session_token
from app.db.session import get_db
from app.models.workspace import Member, Team

type DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_member(request: Request, db: DbSession) -> Member:
    token = request.cookies.get("salesluv_session", "")
    member_id = read_session_token(
        token,
        settings.session_secret.get_secret_value(),
    )
    if member_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not_authenticated",
        )

    result = await db.execute(
        select(Member)
        .join(Team, Member.team_id == Team.id)
        .where(
            Member.id == member_id,
            Member.active.is_(True),
            Member.role_code.in_(("member", "manager")),
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not_authenticated",
        )
    return member


type CurrentMember = Annotated[Member, Depends(get_current_member)]
