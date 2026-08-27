from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, ForeignKeyConstraint, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Product(Base):
    __tablename__ = "product"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    name: Mapped[str]
    active: Mapped[bool] = mapped_column(server_default=text("true"))
    category_code: Mapped[str]
    unit_price: Mapped[int] = mapped_column(BigInteger)
    shelf_life_months: Mapped[int | None]
    memo: Mapped[str | None]
    image_storage_key: Mapped[str | None]

    @property
    def has_image(self) -> bool:
        """사진이 있는지만 알린다. storage_key 자체는 내부 주소라 응답에 넣지 않는다."""
        return self.image_storage_key is not None


class SalesPipeline(Base):
    __tablename__ = "sales_pipeline"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    name: Mapped[str]
    description: Mapped[str | None]
    status_code: Mapped[str]
    is_default: Mapped[bool] = mapped_column(server_default=text("false"))
    published_at: Mapped[datetime | None]
    archived_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class SalesPipelineStage(Base):
    __tablename__ = "sales_pipeline_stage"
    __table_args__ = (
        UniqueConstraint(
            "sales_pipeline_id",
            "stage_code",
            name="sales_pipeline_stage_sales_pipeline_id_stage_code_key",
        ),
        UniqueConstraint(
            "sales_pipeline_id",
            "position",
            name="sales_pipeline_stage_sales_pipeline_id_position_key",
        ),
        UniqueConstraint(
            "sales_pipeline_id",
            "id",
            name="sales_pipeline_stage_sales_pipeline_id_id_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    sales_pipeline_id: Mapped[UUID] = mapped_column(ForeignKey("public.sales_pipeline.id"))
    stage_code: Mapped[str]
    name: Mapped[str]
    tone: Mapped[str]
    phase_code: Mapped[str]
    outcome_code: Mapped[str]
    position: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class SalesDeal(Base):
    __tablename__ = "sales_deal"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sales_pipeline_id", "sales_pipeline_stage_id"],
            [
                "public.sales_pipeline_stage.sales_pipeline_id",
                "public.sales_pipeline_stage.id",
            ],
            name="sales_deal_sales_pipeline_stage_membership_fkey",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    deal_no: Mapped[str]
    customer_company_id: Mapped[UUID] = mapped_column(ForeignKey("public.customer_company.id"))
    customer_contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.customer_contact.id")
    )
    owner_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.product.id"))
    sales_pipeline_id: Mapped[UUID]
    sales_pipeline_stage_id: Mapped[UUID]
    title: Mapped[str]
    description: Mapped[str | None]
    sales_deal_type_id: Mapped[UUID] = mapped_column(ForeignKey("public.sales_deal_type.id"))
    deal_amount: Mapped[int] = mapped_column(BigInteger)
    opened_on: Mapped[date]
    closed_on: Mapped[date | None]
    quote_no: Mapped[str | None]
    quote_issued_on: Mapped[date | None]
    quote_valid_until: Mapped[date | None]
    contract_no: Mapped[str | None]
    contract_signed_on: Mapped[date | None]
    quote_status_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.quote_status.id"))
    contract_status_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.contract_status.id")
    )
    quote_amount: Mapped[int | None] = mapped_column(BigInteger)
    contract_amount: Mapped[int | None] = mapped_column(BigInteger)
    quote_delivery_terms: Mapped[str | None]
    contract_ends_on: Mapped[date | None]
    warranty_terms: Mapped[str | None]
    expected_delivery_at: Mapped[datetime | None]
    memo: Mapped[str | None]
    stage_position: Mapped[int]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class SalesDealItem(Base):
    __tablename__ = "sales_deal_item"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    sales_deal_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.sales_deal.id", ondelete="CASCADE")
    )
    product_id: Mapped[UUID] = mapped_column(ForeignKey("public.product.id"))
    quantity: Mapped[int]
    unit_price: Mapped[int] = mapped_column(BigInteger)
    position: Mapped[int]


class SalesDealParticipant(Base):
    __tablename__ = "sales_deal_participant"

    sales_deal_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.sales_deal.id", ondelete="CASCADE"), primary_key=True
    )
    customer_contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.customer_contact.id"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class PurchaseOrder(Base):
    __tablename__ = "purchase_order"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    order_no: Mapped[str]
    sales_deal_id: Mapped[UUID] = mapped_column(ForeignKey("public.sales_deal.id"))
    supplier_name: Mapped[str]
    purchase_order_status_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.purchase_order_status.id")
    )
    ordered_on: Mapped[date]
    due_on: Mapped[date]
    expected_receipt_on: Mapped[date]
    memo: Mapped[str | None]
    request_department: Mapped[str] = mapped_column(server_default=text("'영업팀'::text"))
    cooperation_department: Mapped[str] = mapped_column(server_default=text("'생산팀'::text"))
    created_by_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    expected_customer_company_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.customer_company.id")
    )
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_item"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[UUID] = mapped_column(
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
