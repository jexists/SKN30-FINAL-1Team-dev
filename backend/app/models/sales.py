from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Product(Base):
    __tablename__ = "product"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    name: Mapped[str]
    active: Mapped[bool] = mapped_column(server_default=text("true"))


class PipelineStage(Base):
    __tablename__ = "pipeline_stage"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    name: Mapped[str]
    tone: Mapped[str]
    outcome_code: Mapped[str]
    position: Mapped[int]


class Contract(Base):
    __tablename__ = "contract"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    contract_no: Mapped[str]
    customer_company_id: Mapped[UUID] = mapped_column(ForeignKey("public.customer_company.id"))
    contact_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.customer_contact.id"))
    owner_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.product.id"))
    stage_id: Mapped[UUID] = mapped_column(ForeignKey("public.pipeline_stage.id"))
    title: Mapped[str]
    description: Mapped[str | None]
    contract_type: Mapped[str]
    amount: Mapped[int] = mapped_column(BigInteger)
    contract_date: Mapped[date]
    ends_on: Mapped[date | None]
    warranty_terms: Mapped[str | None]
    expected_delivery_at: Mapped[datetime | None]
    memo: Mapped[str | None]
    position: Mapped[int]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class PurchaseOrder(Base):
    __tablename__ = "purchase_order"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    order_no: Mapped[str]
    contract_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.contract.id"))
    customer_company_id: Mapped[UUID] = mapped_column(ForeignKey("public.customer_company.id"))
    owner_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    supplier_name: Mapped[str]
    stage_code: Mapped[str]
    ordered_on: Mapped[date]
    due_on: Mapped[date]
    expected_receipt_on: Mapped[date]
    memo: Mapped[str | None]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_item"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.purchase_order.id", ondelete="CASCADE")
    )
    product_id: Mapped[UUID] = mapped_column(ForeignKey("public.product.id"))
    quantity: Mapped[int]
    unit_price: Mapped[int] = mapped_column(BigInteger)
    position: Mapped[int]


class SalesTarget(Base):
    __tablename__ = "sales_target"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    customer_company_id: Mapped[UUID] = mapped_column(ForeignKey("public.customer_company.id"))
    target_month: Mapped[date]
    target_amount: Mapped[int] = mapped_column(BigInteger)
