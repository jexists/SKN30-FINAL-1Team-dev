import asyncio
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

from app.api import sales_deals as api
from app.models.configuration import SalesDealType
from app.models.crm import CustomerCompany
from app.models.sales import Product, SalesDeal, SalesPipeline, SalesPipelineStage
from app.models.workspace import Member
from app.schemas.sales_deals import (
    SalesDealCreate,
    SalesDealMove,
    SalesDealPageParams,
    SalesDealPatch,
)

NOW = datetime(2026, 8, 17, 9, tzinfo=UTC)
_MISSING = object()


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(self, *, scalar=_MISSING, rows=None, scalar_values=None):
        self.scalar = scalar
        self.rows = [] if rows is None else rows
        self.scalar_values = [] if scalar_values is None else scalar_values

    def scalar_one(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def scalar_one_or_none(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def one_or_none(self):
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows

    def scalars(self):
        return _Scalars(self.scalar_values)


class _Db:
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.statements = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results
        return self.results.pop(0)

    async def flush(self):
        self.flush_count += 1

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


def _member(*, role: str = "member", team_id: UUID | None = None) -> Member:
    return Member(
        id=uuid4(),
        team_id=team_id or uuid4(),
        display_name="합성 담당자",
        role_code=role,
        job_title="영업 담당자",
        active=True,
    )


def _pipeline(member: Member, *, status_code: str = "published") -> SalesPipeline:
    return SalesPipeline(
        id=uuid4(),
        team_id=member.team_id,
        name="기본 영업",
        description=None,
        status_code=status_code,
        is_default=True,
        published_at=NOW,
        archived_at=NOW if status_code == "archived" else None,
        created_at=NOW,
        updated_at=NOW,
    )


def _stage(
    pipeline: SalesPipeline,
    *,
    code: str = "needs_validation",
    phase: str = "sales",
    outcome: str = "in_progress",
    position: int = 0,
) -> SalesPipelineStage:
    return SalesPipelineStage(
        id=uuid4(),
        sales_pipeline_id=pipeline.id,
        stage_code=code,
        name=code,
        tone="green" if outcome == "confirmed" else "gray",
        phase_code=phase,
        outcome_code=outcome,
        position=position,
        created_at=NOW,
        updated_at=NOW,
    )


def _deal_type(member: Member, *, deleted: bool = False) -> SalesDealType:
    return SalesDealType(
        id=uuid4(),
        team_id=member.team_id,
        code="new_installation",
        name="신규 도입",
        position=0,
        deleted_at=NOW if deleted else None,
        created_at=NOW,
        updated_at=NOW,
    )


def _company(member: Member) -> CustomerCompany:
    return CustomerCompany(
        id=uuid4(),
        team_id=member.team_id,
        name="합성 고객사",
        region_code="seoul",
        created_at=NOW,
    )


def _product(member: Member) -> Product:
    return Product(id=uuid4(), team_id=member.team_id, name="합성 상품", active=True)


def _deal(
    member: Member,
    pipeline: SalesPipeline,
    stage: SalesPipelineStage,
    deal_type: SalesDealType,
    company: CustomerCompany,
    product: Product,
) -> SalesDeal:
    return SalesDeal(
        id=uuid4(),
        team_id=member.team_id,
        deal_no="SL-DL-2026-0001",
        customer_company_id=company.id,
        customer_contact_id=None,
        owner_member_id=member.id,
        product_id=product.id,
        sales_pipeline_id=pipeline.id,
        sales_pipeline_stage_id=stage.id,
        title="합성 고객사 합성 상품",
        description=None,
        sales_deal_type_id=deal_type.id,
        deal_amount=10_000_000,
        opened_on=date(2026, 8, 17),
        closed_on=None,
        quote_no=None,
        quote_issued_on=None,
        quote_valid_until=None,
        contract_no=None,
        contract_signed_on=None,
        contract_ends_on=None,
        warranty_terms=None,
        expected_delivery_at=None,
        memo=None,
        stage_position=0,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _row(
    deal: SalesDeal,
    member: Member,
    pipeline: SalesPipeline,
    stage: SalesPipelineStage,
    deal_type: SalesDealType,
    company: CustomerCompany,
    product: Product,
):
    return (
        deal,
        member.display_name,
        company.name,
        company.region_code,
        None,
        product.name,
        pipeline.name,
        pipeline.status_code,
        pipeline.is_default,
        stage.stage_code,
        stage.name,
        stage.tone,
        stage.phase_code,
        stage.outcome_code,
        stage.position,
        deal_type.code,
        deal_type.name,
    )


def test_sales_deal_writes_use_explicit_pipeline_and_dynamic_type_code():
    payload = SalesDealCreate(
        customer_company_id=uuid4(),
        product_id=uuid4(),
        sales_pipeline_id=uuid4(),
        sales_pipeline_stage_id=uuid4(),
        deal_type_code="team_custom_type",
        deal_amount=1,
        opened_on="2026-08-17",
    )
    assert payload.deal_type_code == "team_custom_type"
    assert SalesDealPatch(contract_signed_on=None).model_dump(exclude_unset=True) == {
        "contract_signed_on": None
    }
    assert SalesDealPageParams(phase_code=["quote", "contract"])

    with pytest.raises(ValidationError):
        SalesDealCreate(**(payload.model_dump() | {"sales_pipeline_id": None}))
    with pytest.raises(ValidationError):
        SalesDealCreate(**(payload.model_dump() | {"deal_type_code": "한글 유형"}))
    with pytest.raises(ValidationError):
        SalesDealPatch(product_id=None)
    with pytest.raises(ValidationError):
        SalesDealMove(
            expected_sales_pipeline_stage_id=uuid4(),
            sales_pipeline_stage_id=uuid4(),
            stage_position=1.5,
        )


def test_pipeline_stage_and_type_options_are_team_scoped_and_hide_drafts_or_deleted():
    member = _member()
    published = _pipeline(member)
    archived = _pipeline(member, status_code="archived")
    stage = _stage(published)
    deal_type = _deal_type(member)
    db = _Db(
        _Result(scalar_values=[published, archived]),
        _Result(scalar=published),
        _Result(scalar_values=[stage]),
        _Result(scalar_values=[deal_type]),
    )

    pipelines = asyncio.run(api.list_sales_pipelines(member, db))
    stages = asyncio.run(api.list_sales_pipeline_stages(published.id, member, db))
    deal_types = asyncio.run(api.list_sales_deal_types(member, db))

    assert [item.status_code for item in pipelines] == ["published", "archived"]
    assert stages == [stage]
    assert deal_types == [deal_type]
    assert "sales_pipeline.status_code IN" in str(db.statements[0])
    assert "sales_deal_type.deleted_at IS NULL" in str(db.statements[-1])
    assert all(
        member.team_id in statement.compile().params.values() for statement in db.statements[:2]
    )


def test_archived_pipeline_stage_is_readable_but_not_a_write_target():
    member = _member()
    archived = _pipeline(member, status_code="archived")
    stage = _stage(archived)
    db = _Db(
        _Result(scalar=archived),
        _Result(scalar_values=[stage]),
        _Result(scalar=None),
    )

    assert asyncio.run(api.list_sales_pipeline_stages(archived.id, member, db)) == [stage]

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api._team_stage(db, member, uuid4()))

    assert exc.value.status_code == 404
    params = db.statements[2].compile().params.values()
    assert "published" in params
    assert "archived" not in params

    locked_db = _Db(_Result(scalar=None))
    with pytest.raises(HTTPException) as locked_exc:
        asyncio.run(api._locked_sales_deal(locked_db, member, uuid4()))

    assert locked_exc.value.status_code == 404
    locked_statement = locked_db.statements[0]
    assert "JOIN public.sales_pipeline" in str(locked_statement)
    locked_params = locked_statement.compile().params.values()
    assert "published" in locked_params
    assert "archived" not in locked_params


def test_sales_deal_list_exposes_pipeline_stage_type_and_phase_filter():
    member = _member()
    pipeline = _pipeline(member)
    stage = _stage(pipeline, code="quote_sent", phase="quote", position=2)
    deal_type = _deal_type(member, deleted=True)
    company = _company(member)
    product = _product(member)
    deal = _deal(member, pipeline, stage, deal_type, company, product)
    db = _Db(
        _Result(scalar=1),
        _Result(rows=[_row(deal, member, pipeline, stage, deal_type, company, product)]),
        _Result(rows=[(stage.id, 1)]),
    )

    page = asyncio.run(
        api.list_sales_deals(
            SalesDealPageParams(phase_code=["quote"], q=" 합성 "),
            member,
            db,
        )
    )

    item = page.items[0]
    assert item.sales_pipeline_id == pipeline.id
    assert item.sales_pipeline_stage_code == "quote_sent"
    assert item.sales_pipeline_stage_phase_code == "quote"
    assert item.deal_type_code == deal_type.code
    for statement in db.statements:
        sql = str(statement)
        assert "sales_deal.deleted_at IS NULL" in sql
        assert "sales_deal_type" in sql
        assert "%합성%" in statement.compile().params.values()


def test_new_deal_number_ignores_legacy_numbers():
    member = _member()
    db = _Db(
        _Result(scalar=member.team_id),
        _Result(
            scalar_values=[
                "FM-CT-2026-9999",
                "SL-DL-2026-0007",
                "SL-DL-2026-invalid",
            ]
        ),
    )

    assert asyncio.run(api._next_deal_no(db, member, 2026)) == "SL-DL-2026-0008"


def test_move_sets_contract_signed_date_only_for_confirmed_contract(monkeypatch):
    member = _member()
    pipeline = _pipeline(member)
    source_stage = _stage(pipeline)
    target_stage = _stage(
        pipeline,
        code="contract_completed",
        phase="contract",
        outcome="confirmed",
        position=5,
    )
    deal_type = _deal_type(member)
    company = _company(member)
    product = _product(member)
    deal = _deal(member, pipeline, source_stage, deal_type, company, product)
    db = _Db()

    async def team_stage(*_args):
        return target_stage

    async def locked_deal(*_args):
        return deal

    async def stage_deals(*_args):
        return [deal]

    async def deal_row(*_args):
        return _row(deal, member, pipeline, target_stage, deal_type, company, product)

    monkeypatch.setattr(api, "_team_stage", team_stage)
    monkeypatch.setattr(api, "_locked_sales_deal", locked_deal)
    monkeypatch.setattr(api, "_stage_sales_deals", stage_deals)
    monkeypatch.setattr(api, "_sales_deal_row", deal_row)

    result = asyncio.run(
        api.move_sales_deal(
            deal.id,
            SalesDealMove(
                expected_sales_pipeline_stage_id=source_stage.id,
                sales_pipeline_stage_id=target_stage.id,
                stage_position=0,
            ),
            BackgroundTasks(),
            member,
            db,
        )
    )

    assert result.contract_signed_on is not None
    assert result.closed_on is None
    assert deal.sales_pipeline_stage_id == target_stage.id
    assert db.commit_count == 1

    previous_stage_id = target_stage.id
    target_stage = _stage(
        pipeline,
        code="closed_cancelled",
        phase="closed",
        outcome="cancelled",
        position=8,
    )
    result = asyncio.run(
        api.move_sales_deal(
            deal.id,
            SalesDealMove(
                expected_sales_pipeline_stage_id=previous_stage_id,
                sales_pipeline_stage_id=target_stage.id,
                stage_position=0,
            ),
            BackgroundTasks(),
            member,
            db,
        )
    )
    assert result.closed_on is not None
    assert result.contract_signed_on is not None


def test_move_closes_only_closed_phase_and_rejects_another_pipeline(monkeypatch):
    member = _member()
    pipeline = _pipeline(member)
    other_pipeline = _pipeline(member)
    source_stage = _stage(pipeline, phase="contract", outcome="confirmed")
    target_stage = _stage(other_pipeline, code="closed_cancelled", phase="closed")
    deal_type = _deal_type(member)
    company = _company(member)
    product = _product(member)
    deal = _deal(member, pipeline, source_stage, deal_type, company, product)
    db = _Db()

    async def team_stage(*_args):
        return target_stage

    async def locked_deal(*_args):
        return deal

    monkeypatch.setattr(api, "_team_stage", team_stage)
    monkeypatch.setattr(api, "_locked_sales_deal", locked_deal)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api.move_sales_deal(
                deal.id,
                SalesDealMove(
                    expected_sales_pipeline_stage_id=source_stage.id,
                    sales_pipeline_stage_id=target_stage.id,
                    stage_position=0,
                ),
                BackgroundTasks(),
                member,
                db,
            )
        )

    assert exc.value.status_code == 422
    assert exc.value.detail == "sales_pipeline_stage_pipeline_mismatch"
    assert deal.closed_on is None
    assert db.rollback_count == 1


def test_renewal_filters_match_the_dashboard_card():
    """계약갱신 카드를 눌러 여는 목록. 카드가 세는 조건과 같아야 숫자와 총계가 맞는다."""
    member = _member()
    pipeline = _pipeline(member)
    stage = _stage(pipeline, code="contract_completed", phase="contract", outcome="confirmed")
    deal_type = _deal_type(member)
    company = _company(member)
    product = _product(member)
    deal = _deal(member, pipeline, stage, deal_type, company, product)
    db = _Db(
        _Result(scalar=1),
        _Result(rows=[_row(deal, member, pipeline, stage, deal_type, company, product)]),
        _Result(rows=[(stage.id, 1)]),
    )

    page = asyncio.run(
        api.list_sales_deals(
            SalesDealPageParams(
                outcome_code=["confirmed"],
                contract_ends_from=date(2026, 8, 25),
                contract_ends_to=date(2026, 9, 24),
            ),
            member,
            db,
        )
    )

    assert page.total == 1
    for statement in db.statements:
        sql = str(statement)
        assert "outcome_code IN" in sql
        assert "sales_deal.contract_ends_on >=" in sql
        assert "sales_deal.contract_ends_on <=" in sql


def test_renewal_window_rejects_a_reversed_range():
    with pytest.raises(ValidationError):
        SalesDealPageParams(
            contract_ends_from=date(2026, 9, 24), contract_ends_to=date(2026, 8, 25)
        )


def test_stage_tab_counts_ignore_the_chosen_stage():
    """단계 탭 옆 건수는 고른 단계만 빼고 센다.

    단계까지 넣고 세면 고른 탭에만 숫자가 남아 다른 단계에 무엇이 얼마나 있는지 알 수
    없다. 반대로 파이프라인·검색어까지 빼면 탭 숫자가 실제로 열리는 목록보다 커진다.
    """
    member = _member()
    pipeline = _pipeline(member)
    stage = _stage(pipeline, code="quote_sent", phase="quote", position=2)
    other = _stage(pipeline, code="quote_ready", phase="quote", position=1)
    db = _Db(
        _Result(scalar_values=[stage.id]),
        _Result(scalar=pipeline),
        _Result(scalar=0),
        _Result(rows=[]),
        _Result(rows=[(stage.id, 3), (other.id, 7)]),
    )

    page = asyncio.run(
        api.list_sales_deals(
            SalesDealPageParams(
                sales_pipeline_id=pipeline.id,
                sales_pipeline_stage_id=[stage.id],
                q="합성",
            ),
            member,
            db,
        )
    )

    assert page.counts == {str(stage.id): 3, str(other.id): 7}

    rows_sql = str(db.statements[3])
    counts_sql = str(db.statements[4])
    stage_filter = "sales_deal.sales_pipeline_stage_id IN"
    # 목록은 단계를 적용한다. 이 단언이 깨지면 아래 not in 이 헛돈다.
    assert stage_filter in rows_sql
    # 건수는 단계를 빼고 파이프라인과 검색어는 남긴다.
    assert stage_filter not in counts_sql
    assert "sales_deal.sales_pipeline_id = " in counts_sql
    assert "%합성%" in db.statements[4].compile().params.values()


def test_date_basis_moves_the_range_to_the_phase_date():
    """견적 화면의 기간은 발행일 기준이다. 딜 시작일로 걸면 다른 목록이 나온다.

    발행일이 아직 없는 딜은 시작일로 되돌려 세야, 번호를 매기기 전 견적이 기간에서
    통째로 사라지지 않는다.
    """
    member = _member()
    db = _Db(_Result(scalar=0), _Result(rows=[]), _Result(rows=[]))

    asyncio.run(
        api.list_sales_deals(
            SalesDealPageParams(
                phase_code=["quote"],
                date_basis="quote_issued",
                start_date=date(2026, 3, 1),
            ),
            member,
            db,
        )
    )

    sql = str(db.statements[0])
    assert "coalesce(public.sales_deal.quote_issued_on, public.sales_deal.opened_on) >=" in sql

    # 기본값은 예전 그대로 시작일이다. 대시보드 등 이미 쓰던 조회가 바뀌면 안 된다.
    default_db = _Db(_Result(scalar=0), _Result(rows=[]), _Result(rows=[]))
    asyncio.run(
        api.list_sales_deals(SalesDealPageParams(start_date=date(2026, 3, 1)), member, default_db)
    )
    default_sql = str(default_db.statements[0])
    assert "public.sales_deal.opened_on >=" in default_sql
    assert "coalesce" not in default_sql.lower()


def test_pipeline_status_filter_narrows_the_scope():
    """발주를 넣을 딜을 고르는 칸은 보관된 파이프라인의 딜을 빼고 받는다.

    전건을 받아 화면에서 거르던 자리라, 서버가 걸러 주지 않으면 쪽으로 끊는 순간
    첫 30건이 전부 보관된 딜일 수 있다.
    """
    params = SalesDealPageParams(sales_pipeline_status_code=["published"])
    assert params.sales_pipeline_status_code == ["published"]
    # 안 주면 예전처럼 전부 본다.
    assert SalesDealPageParams().sales_pipeline_status_code is None
    with pytest.raises(ValidationError):
        SalesDealPageParams(sales_pipeline_status_code=["draft"])
