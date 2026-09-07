from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TeamMemberOptionRead(BaseModel):
    """담당자 선택 같은 화면 목록이 쓰는 팀원 한 명.

    email 은 담지 않는다. 어드민 목록 화면 전용 정보라 일반 화면까지 퍼뜨리지 않는다.
    부서는 member 가 아니라 team 의 값이라 팀원마다 같으므로 직함만 둔다.

    badge_color 는 담는다. 담당자 이름표를 그리는 데 쓰는 표시용 값이고, 이름표는 목록
    화면 어디에나 서므로 색을 여기 말고 다른 데서 받을 자리가 없다. 고치는 길은 팀장
    전용 PATCH /team/members/{id} 하나뿐이다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    job_title: str | None
    role_code: str
    badge_color: str | None
