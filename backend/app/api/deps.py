"""라우터에서 공용으로 쓰는 의존성.

Annotated 별칭으로 두면 라우터 시그니처가 짧아지고,
Depends() 를 인자 기본값에 직접 쓰지 않게 되어 린터(B008)와도 맞습니다.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.workspace import Member, Team
from app.services import supabase_auth

type DbSession = Annotated[AsyncSession, Depends(get_db)]


async def member_by_auth_user_id(db: AsyncSession, auth_user_id: UUID) -> Member | None:
    """Supabase 사용자에 연결된 활성 구성원.

    팀·역할·활성 상태의 기준은 언제나 public.member 다.
    사용자가 고칠 수 있는 Supabase user_metadata 는 권한 판단에 쓰지 않는다.
    """
    result = await db.execute(
        select(Member)
        .join(Team, Member.team_id == Team.id)
        .where(
            Member.auth_user_id == auth_user_id,
            Member.active.is_(True),
            Member.role_code.in_(("member", "manager")),
        )
    )
    return result.scalar_one_or_none()


async def get_current_member(request: Request, db: DbSession) -> Member:
    # auth.py 를 import 하면 순환이 되므로 쿠키 이름만 여기서 다시 적는다.
    token = request.cookies.get("salesluv_access", "")
    try:
        auth_user_id = await supabase_auth.verify_access_token(token)
    except supabase_auth.InvalidCredentials as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not_authenticated",
        ) from error
    except supabase_auth.AuthNotConfigured as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth_not_configured",
        ) from error
    except supabase_auth.AuthError as error:
        # 서명 키를 못 받아온 경우다. 인증 실패로 단정하지 않는다.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth_unavailable",
        ) from error

    member = await member_by_auth_user_id(db, auth_user_id)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="member_not_linked",
        )
    return member


type CurrentMember = Annotated[Member, Depends(get_current_member)]
