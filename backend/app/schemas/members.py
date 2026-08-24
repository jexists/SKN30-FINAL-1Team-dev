from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TeamMemberOptionRead(BaseModel):
    """담당자 선택 같은 화면 목록이 쓰는 팀원 한 명.

    email 은 담지 않는다. 어드민 목록 화면 전용 정보라 일반 화면까지 퍼뜨리지 않는다.
    부서는 member 가 아니라 team 의 값이라 팀원마다 같으므로 직함만 둔다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    job_title: str | None
    role_code: str
