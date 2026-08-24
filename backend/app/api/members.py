from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentMember, DbSession
from app.models.workspace import Member
from app.schemas.members import TeamMemberOptionRead

router = APIRouter(tags=["members"])


@router.get("/team-members", response_model=list[TeamMemberOptionRead])
async def list_team_members(member: CurrentMember, db: DbSession) -> list[Member]:
    """같은 팀의 활성 구성원. 담당자 선택 같은 화면 목록의 데이터원이다.

    role_code 와 active 조건은 deps.active_member 및 customers._contact_scope 와 같은 기준을 쓴다.
    누구를 담당자로 세울 수 있는지는 쓰기 시점에 따로 판단한다. 여기는 팀 안의 이름 목록일 뿐이다.
    """
    result = await db.execute(
        select(Member)
        .where(
            Member.team_id == member.team_id,
            Member.active.is_(True),
            Member.role_code.in_(("member", "manager")),
        )
        .order_by(Member.display_name, Member.id)
    )
    return list(result.scalars().all())
