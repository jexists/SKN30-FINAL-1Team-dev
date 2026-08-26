"""어드민 계정 발급 API.

계정 하나를 만드는 일이 Supabase Auth 와 public 스키마 양쪽에 걸쳐 있다.
어느 한쪽만 남는 상태를 만들지 않는 것이 이 모듈의 일이다.

발급 권한의 근거는 member.role_code 가 아니라 ADMIN_USER_IDS 다. deps.get_admin_member 를 본다.
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.auth import auth_http_error
from app.api.deps import CurrentAdmin, DbSession
from app.core.config import settings
from app.models.workspace import Member, Team
from app.schemas.admin import AccountCreate, AccountCreated, TeamRead
from app.services import supabase_auth

router = APIRouter(prefix="/admin", tags=["admin"])

# 로컬 개발용 고정 비밀번호. 받을 수 있는 메일 주소 없이 테스트 계정을 만들려고 둔다.
# APP_ENV=local 에서만 쓰이므로 test/production 에는 닿지 않는다.
LOCAL_DEV_PASSWORD = "12341234"


@router.get("/teams", response_model=list[TeamRead])
async def list_teams(_admin: CurrentAdmin, db: DbSession) -> list[dict]:
    """팀과 구성원 전체. 발급 화면이 기존 팀에 붙일지 새로 만들지 고르는 데 쓴다.

    어드민은 팀 경계를 넘어 본다. 다른 라우터의 team_id 스코프가 여기에는 없다.
    """
    teams = (await db.execute(select(Team).order_by(Team.created_at))).scalars().all()
    members = (await db.execute(select(Member).order_by(Member.display_name))).scalars().all()

    by_team: dict[UUID, list[Member]] = {}
    for member in members:
        by_team.setdefault(member.team_id, []).append(member)

    return [
        {
            "id": team.id,
            "name": team.name,
            "company_name": team.company_name,
            "department": team.department,
            "business_no": team.business_no,
            "member_count": len(by_team.get(team.id, [])),
            "members": by_team.get(team.id, []),
        }
        for team in teams
    ]


@router.post(
    "/accounts",
    response_model=AccountCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_account(
    payload: AccountCreate,
    _admin: CurrentAdmin,
    db: DbSession,
) -> Member:
    """Supabase 사용자 생성·초대 메일·team/member 등록을 한 번에 끝낸다.

    순서를 되돌릴 수 있게 잡는다. member.id 는 auth 사용자 id 와 같아야 하므로
    초대가 먼저고, 그 뒤 DB 쓰기가 실패하면 만든 사용자를 지워 되돌린다.

    payload.instant 이면 초대 대신 LOCAL_DEV_PASSWORD 로 확인된 사용자를 바로 만든다.
    로컬에서만 받는다.
    """
    if payload.instant and settings.app_env != "local":
        # 조용히 초대로 넘기지 않는다. 메일이 안 나갈 줄 알고 실주소를 넣었을 수도 있다.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="instant_local_only",
        )

    team = await _resolve_team(payload, db)

    try:
        if payload.instant:
            # 메일을 받을 곳이 없을 때 쓴다. 확인된 사용자를 바로 만들고 비밀번호를 고정한다.
            member_id = await supabase_auth.create_confirmed_user(
                email=payload.email,
                password=LOCAL_DEV_PASSWORD,
            )
        else:
            member_id = await supabase_auth.invite_user(
                email=payload.email,
                redirect_to=f"{settings.frontend_base_url.rstrip('/')}/set-password",
            )
    except supabase_auth.EmailAlreadyExists as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email_already_exists",
        ) from error
    except supabase_auth.AuthError as error:
        raise auth_http_error(error) from error

    member = Member(
        id=member_id,
        team_id=team.id,
        display_name=payload.display_name,
        role_code=payload.role_code,
        email=payload.email,
        active=True,
    )
    db.add(member)
    try:
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        # 초대만 남으면 그 이메일로 다시 발급할 수 없게 된다. 반드시 되돌린다.
        try:
            await supabase_auth.delete_user(user_id=member_id)
        except supabase_auth.AuthError:
            # 되돌리기까지 실패했다. 원래 실패를 가리지 않고 그대로 올린다.
            pass
        raise

    return member


async def _resolve_team(payload: AccountCreate, db: DbSession) -> Team:
    """기존 팀을 찾거나 새 팀을 만든다. 초대를 보내기 전에 끝낸다.

    없는 팀을 가리켰다면 Supabase 사용자를 만들기 전에 멈추는 편이 낫다.
    되돌릴 것이 없는 실패가 되돌려야 하는 실패보다 낫다.
    """
    if payload.team_id is not None:
        team = await db.get(Team, payload.team_id)
        if team is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team_not_found")
        return team

    assert payload.team is not None  # AccountCreate 가 둘 중 하나임을 보장한다.
    duplicate = await db.execute(
        select(func.count()).select_from(Team).where(Team.name == payload.team.name)
    )
    if duplicate.scalar_one():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="team_name_already_exists",
        )

    team = Team(id=uuid4(), **payload.team.model_dump())
    db.add(team)
    await db.flush()
    return team
