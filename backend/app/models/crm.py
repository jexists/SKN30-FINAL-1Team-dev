from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, ForeignKeyConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustomerCompany(Base):
    __tablename__ = "customer_company"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    name: Mapped[str]
    region_code: Mapped[str | None]
    # 하이픈 없는 10자리. 화면에 보일 하이픈은 프론트가 붙인다.
    business_no: Mapped[str | None]
    # 우편번호 5자리와 주소. 다음 우편번호 서비스가 돌려주는 값을 그대로 담는다.
    postcode: Mapped[str | None]
    address: Mapped[str | None]
    # 층·호수처럼 사람이 직접 적는 부분.
    address_detail: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class CustomerContact(Base):
    __tablename__ = "customer_contact"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("public.customer_company.id"))
    # 대표 담당자. CustomerContactAssignee 의 첫 번째와 같고, 조회 스코프가 이 컬럼을 본다.
    owner_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    # 고객을 등록한 사람. 등록 후 바뀌지 않는다.
    created_by_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    name: Mapped[str]
    department: Mapped[str | None]
    job_title: Mapped[str | None]
    email: Mapped[str | None]
    phone: Mapped[str]
    customer_contact_status_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.customer_contact_status.id")
    )
    source_code: Mapped[str | None]
    memo: Mapped[str | None]
    # 담당자가 직접 켜고 끄는 표시. 활동 기록에서 파생하지 않는다.
    visited: Mapped[bool] = mapped_column(server_default=text("false"))
    registered_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class CustomerContactAssignee(Base):
    """고객 한 건의 담당자. 대표 담당자도 여기에 함께 들어간다."""

    __tablename__ = "customer_contact_assignee"

    customer_contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.customer_contact.id", ondelete="CASCADE"), primary_key=True
    )
    member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Activity(Base):
    __tablename__ = "activity"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    owner_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    customer_contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.customer_contact.id")
    )
    end_user_contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.customer_contact.id")
    )
    activity_type: Mapped[str]
    activity_category_id: Mapped[UUID] = mapped_column(ForeignKey("public.activity_category.id"))
    title: Mapped[str]
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime | None]
    all_day: Mapped[bool] = mapped_column(server_default=text("false"))
    due_at: Mapped[datetime | None]
    location: Mapped[str | None]
    activity_action_tag_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.activity_action_tag.id")
    )
    completed_at: Mapped[datetime | None]
    note: Mapped[str | None]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.product.id"))
    sales_deal_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.sales_deal.id"))
    purchase_order_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.purchase_order.id"))


class ActivityCompanion(Base):
    __tablename__ = "activity_companion"

    activity_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.activity.id", ondelete="CASCADE"), primary_key=True
    )
    member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"), primary_key=True)


class SupportRequest(Base):
    __tablename__ = "support_request"
    __table_args__ = (
        # 불만의 고객사가 그 딜의 고객사와 다를 수 없게 하는 복합 외래키다. 두 컬럼을
        # 따로 검증하지 않고 DB 가 한 제약으로 보장한다. sales_deal 이
        # sales_pipeline_stage 를 참조하는 방식과 같다.
        ForeignKeyConstraint(
            ["sales_deal_id", "customer_company_id"],
            ["public.sales_deal.id", "public.sales_deal.customer_company_id"],
            name="support_request_sales_deal_company_membership_fkey",
            onupdate="CASCADE",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    # 두 컬럼은 __table_args__ 의 복합 외래키 하나로 sales_deal 을 가리킨다.
    # customer_company.id 나 sales_deal.id 로 가는 단일 외래키는 그 제약에 이미 포함되므로
    # 중복해서 두지 않는다. sales_deal 이 sales_pipeline_id 를 다루는 방식과 같다.
    customer_company_id: Mapped[UUID]
    # 불만이 걸린 계약건. 관련 제품과 워런티는 이 딜의 product_id·warranty_terms 다.
    sales_deal_id: Mapped[UUID]
    # 불만을 등록한 사람. 등록 시점의 로그인 구성원이며 그대로 처리 담당자를 겸한다.
    assignee_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    title: Mapped[str]
    body: Mapped[str]
    is_urgent: Mapped[bool] = mapped_column(server_default=text("false"))
    # received 접수 / diagnosing 원인파악 / in_progress 처리중 / completed 처리완료
    status_code: Mapped[str]
    # 불만이 일어난 시각. 접수자가 직접 넣는다. registered_at(등록 시각)과 다르다.
    occurred_at: Mapped[datetime]
    registered_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class SupportResponse(Base):
    __tablename__ = "support_response"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    support_request_id: Mapped[UUID] = mapped_column(ForeignKey("public.support_request.id"))
    responder_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    body: Mapped[str]
    responded_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
