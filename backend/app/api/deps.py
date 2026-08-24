"""라우터에서 공용으로 쓰는 의존성.

Annotated 별칭으로 두면 라우터 시그니처가 짧아지고,
Depends() 를 인자 기본값에 직접 쓰지 않게 되어 린터(B008)와도 맞습니다.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.workspace import Member, Team
from app.services import supabase_auth

type DbSession = Annotated[AsyncSession, Depends(get_db)]


async def active_member(db: AsyncSession, member_id: UUID) -> Member | None:
    """Supabase 사용자 id 는 곧 member.id 다.

    팀·역할·활성 상태의 기준은 언제나 public.member 다.
    사용자가 고칠 수 있는 Supabase user_metadata 는 권한 판단에 쓰지 않는다.
    """
    result = await db.execute(
        select(Member)
        .join(Team, Member.team_id == Team.id)
        .where(
            Member.id == member_id,
            Member.active.is_(True),
            Member.role_code.in_(("member", "manager")),
        )
    )
    return result.scalar_one_or_none()


async def get_current_member(request: Request, db: DbSession) -> Member:
    # auth.py 를 import 하면 순환이 되므로 쿠키 이름만 여기서 다시 적는다.
    token = request.cookies.get("salesluv_access", "")
    try:
        member_id = await supabase_auth.verify_access_token(token)
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

    member = await active_member(db, member_id)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="member_not_linked",
        )
    return member


type CurrentMember = Annotated[Member, Depends(get_current_member)]


async def owner_scope(
    db: AsyncSession,
    member: Member,
    requested: list[UUID] | None,
) -> tuple[UUID, ...] | None:
    """전역 보기 범위가 고른 담당자를 조회 조건으로 바꾼다.

    남의 현황을 보는 건 팀장만 할 수 있다. 그리고 요청된 id 는 매번 같은 팀의 활성
    구성원인지 다시 확인한다. 화면이 보낸 값을 그대로 믿으면 팀 경계가 쿼리 파라미터
    하나로 뚫린다.

    None 은 "담당자를 좁히지 않는다"는 뜻이고, 팀 범위는 라우터의 `_scope` 가 따로 건다.
    """
    if requested is None:
        return None
    if member.role_code != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="scope_not_allowed",
        )
    owner_ids = tuple(dict.fromkeys(requested))
    result = await db.execute(
        select(Member.id).where(
            Member.id.in_(owner_ids),
            Member.team_id == member.team_id,
            Member.active.is_(True),
            Member.role_code.in_(("member", "manager")),
        )
    )
    if set(result.scalars().all()) != set(owner_ids):
        # 없는 사람이나 남의 팀이 섞였으면 빈 목록이 아니라 거절이다. 조용히 비우면
        # 화면은 "그 사람 실적이 0" 이라고 읽는다.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="scope_not_allowed",
        )
    return owner_ids


async def get_admin_member(member: CurrentMember) -> Member:
    """계정을 발급할 수 있는 사람인지 본다.

    판단 근거는 member.role_code 가 아니라 환경변수 허용목록이다. DB 행만
    고쳐서 어드민이 될 수 있으면, 계정을 만들 수 있는 권한이 계정 안에 갇힌다.
    """
    if not settings.admin_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin_not_configured",
        )
    if member.id not in settings.admin_user_id_set:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_only")
    return member


type CurrentAdmin = Annotated[Member, Depends(get_admin_member)]
