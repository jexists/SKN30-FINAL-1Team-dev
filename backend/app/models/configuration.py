from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustomerContactStatus(Base):
    __tablename__ = "customer_contact_status"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    code: Mapped[str]
    name: Mapped[str]
    tone: Mapped[str]
    position: Mapped[int]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class ActivityCategory(Base):
    __tablename__ = "activity_category"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    code: Mapped[str]
    name: Mapped[str]
    tone: Mapped[str]
    position: Mapped[int]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    activity_type: Mapped[str]


class ActivityActionTag(Base):
    __tablename__ = "activity_action_tag"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    code: Mapped[str]
    name: Mapped[str]
    tone: Mapped[str]
    position: Mapped[int]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    activity_type: Mapped[str]


class SalesDealType(Base):
    __tablename__ = "sales_deal_type"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    code: Mapped[str]
    name: Mapped[str]
    position: Mapped[int]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class PurchaseOrderStatus(Base):
    __tablename__ = "purchase_order_status"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    code: Mapped[str]
    name: Mapped[str]
    tone: Mapped[str]
    position: Mapped[int]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    outcome_code: Mapped[str]


class QuoteStatus(Base):
    """견적서 한 장의 진행 상태. 파이프라인 단계와는 다른 축이다."""

    __tablename__ = "quote_status"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    code: Mapped[str]
    name: Mapped[str]
    tone: Mapped[str]
    position: Mapped[int]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    outcome_code: Mapped[str]


class ContractStatus(Base):
    """계약서 한 장의 진행 상태."""

    __tablename__ = "contract_status"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    code: Mapped[str]
    name: Mapped[str]
    tone: Mapped[str]
    position: Mapped[int]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    outcome_code: Mapped[str]
