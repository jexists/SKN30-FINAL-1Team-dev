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

    # auth.users.id 와 같은 값. auth 스키마는 ORM 에 매핑하지 않으므로
    # 여기에는 대응하는 ForeignKey 를 두지 않는다. 물리 FK 는 DB 에 있다.
    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
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
