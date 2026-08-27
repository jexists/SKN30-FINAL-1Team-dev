from datetime import date, datetime
from uuid import UUID

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Team(Base):
    __tablename__ = "team"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str]
    company_name: Mapped[str | None]
    department: Mapped[str | None]
    # 하이픈 없는 10자리. 화면에 보일 하이픈은 프론트가 붙인다.
    business_no: Mapped[str | None]
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
    # auth.users.email 의 사본. 권한 판단에는 쓰지 않고 어드민 목록 표시에만 쓴다.
    email: Mapped[str | None]
    active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Notice(Base):
    __tablename__ = "notice"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    author_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    # 구버전 Supabase에 남아 있는 호환 컬럼. 최신 수신자 흐름은 notice_target을 사용한다.
    recipient_member_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.member.id"))
    # NOTICE 는 팀 전체가 보고, DIRECTIVE 는 NoticeTarget 이 가리키는 사람만 본다.
    type: Mapped[str]
    tag: Mapped[str | None]
    title: Mapped[str]
    # 허용 태그만 남긴 HTML. services.html_sanitize 를 지나야 여기에 들어온다.
    body: Mapped[str]
    image_storage_key: Mapped[str | None]
    image_alt: Mapped[str | None]
    published_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    due_at: Mapped[datetime | None]
    due_text: Mapped[str | None]
    # 노출 기간은 날짜다. 기준 시간대는 Asia/Seoul 이고 시작일과 종료일 모두 그 날을 포함한다.
    # DB 기본값을 두지 않았으므로 앱이 항상 값을 넣는다.
    display_start_date: Mapped[date]
    display_end_date: Mapped[date | None]
    is_hidden: Mapped[bool] = mapped_column(server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    deleted_at: Mapped[datetime | None]


class NoticeTarget(Base):
    """지시 한 건의 수신자. 공지에는 행이 없다. created_at 순서가 곧 표시 순서다."""

    __tablename__ = "notice_target"

    notice_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.notice.id", ondelete="CASCADE"), primary_key=True
    )
    member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class NoticeImage(Base):
    """공지 본문에 넣은 사진.

    본문 HTML 은 `/notice-images/{id}` 로만 가리킨다. 저장소 주소(storage_key)는 응답에
    나가지 않고, 실제로 볼 수 있는 주소는 읽을 때마다 서명 URL 로 새로 발급한다.
    """

    __tablename__ = "notice_image"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    uploaded_by_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    storage_key: Mapped[str]
    media_type: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
