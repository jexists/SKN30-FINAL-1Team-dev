from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Team(Base):
    __tablename__ = "team"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Member(Base):
    __tablename__ = "member"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    # Supabase auth.users.id 와의 유일한 연결 고리.
    # 로그인하지 않는 목업 구성원이 있으므로 nullable 이다.
    auth_user_id: Mapped[UUID | None]
    # 0007 로 컬럼을 지우기 전까지 남는 자체 로그인 흔적. 인증에는 쓰지 않는다.
    login_id: Mapped[str]
    password_hash: Mapped[str]
    display_name: Mapped[str]
    role_code: Mapped[str]
    job_title: Mapped[str | None]
    active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Notice(Base):
    __tablename__ = "notice"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    author_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    recipient_member_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.member.id"))
    tag: Mapped[str | None]
    title: Mapped[str]
    body: Mapped[str]
    image_storage_key: Mapped[str | None]
    image_alt: Mapped[str | None]
    published_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    due_at: Mapped[datetime | None]
    due_text: Mapped[str | None]
