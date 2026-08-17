from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustomerCompany(Base):
    __tablename__ = "customer_company"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    name: Mapped[str]
    region_code: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class CustomerContact(Base):
    __tablename__ = "customer_contact"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("public.customer_company.id"))
    owner_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
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
    registered_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


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

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    customer_contact_id: Mapped[UUID] = mapped_column(ForeignKey("public.customer_contact.id"))
    assignee_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    title: Mapped[str]
    body: Mapped[str]
    is_urgent: Mapped[bool] = mapped_column(server_default=text("false"))
    status_code: Mapped[str]
    registered_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class SupportResponse(Base):
    __tablename__ = "support_response"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    support_request_id: Mapped[UUID] = mapped_column(ForeignKey("public.support_request.id"))
    responder_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    body: Mapped[str]
    responded_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
