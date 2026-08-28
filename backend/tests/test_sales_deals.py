import asyncio
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import sales_deals as api
from app.models.configuration import SalesDealType
from app.models.crm import CustomerCompany
from app.models.sales import (
    Product,
    SalesDeal,
    SalesDealItem,
    SalesPipeline,
    SalesPipelineStage,
)
from app.models.workspace import Member
from app.schemas.sales_deals import (
    SalesDealCreate,
    SalesDealItemWrite,
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
        self.added = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results
        return self.results.pop(0)

    def add(self, instance):
        self.added.append(instance)

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
        quote_status_id=None,
        contract_status_id=None,
        quote_amount=None,
        contract_amount=None,
        quote_delivery_terms=None,
        warranty_terms=None,
        expected_delivery_at=None,
        memo=None,
        stage_position=0,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _deal_statements(db):
    """딜을 훑는 쿼리만. 품목·미팅 대상자·발주 상태는 다른 표에서 따로 가져온다."""
    return [
        statement for statement in db.statements if "FROM public.sales_deal JOIN" in str(statement)
    ]


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
        None,
        None,
        None,
        None,
        None,
        None,
        "성문메디컬",
        "1234567890",
        company.business_no,
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


def test_source_code_is_optional_and_limited_to_the_customer_source_set():
    base = {
        "customer_company_id": uuid4(),
        "product_id": uuid4(),
        "sales_pipeline_id": uuid4(),
        "sales_pipeline_stage_id": uuid4(),
        "deal_type_code": "new_installation",
        "deal_amount": 1,
        "opened_on": "2026-08-17",
    }
    assert SalesDealCreate(**base).source_code is None

    payload = SalesDealCreate(**(base | {"source_code": "referral"}))
    assert payload.source_code == "referral"
    # 생성은 model_dump 를 그대로 SalesDeal 에 넘긴다. 빠지면 값이 조용히 사라진다.
    assert "source_code" in payload.model_dump()

    # 유입경로는 모를 수 있는 값이라 PATCH 로 비울 수 있어야 한다.
    assert SalesDealPatch(source_code=None).model_dump(exclude_unset=True) == {"source_code": None}
    assert SalesDealPatch(source_code="online_form").source_code == "online_form"

    with pytest.raises(ValidationError):
        SalesDealCreate(**(base | {"source_code": "exhibition"}))
    with pytest.raises(ValidationError):
        SalesDealPatch(source_code="Online form")


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
        # 품목·미팅 대상자·최근 발주 상태는 쪽에 담긴 딜만 따로 훑는다.
        _Result(rows=[]),
        _Result(rows=[]),
        _Result(rows=[]),
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
    for statement in _deal_statements(db):
        sql = str(statement)
        assert "sales_deal.deleted_at IS NULL" in sql
        assert "sales_deal_type" in sql
        assert "%합성%" in statement.compile().params.values()


def test_quote_list_filters_by_status_and_counts_by_the_same_column():
    """견적현황은 파이프라인 단계가 아니라 견적 상태로 거르고 센다.

    phase_code 로 거르면 계약으로 넘어간 딜이 견적번호를 그대로 들고 있는데도 목록에서
    사라진다. 그래서 has_quote(상태가 붙었는가)로 거른다. 탭 옆 건수는 고른 탭 자신을
    범위에서 빼고 세야 나머지 탭 숫자가 0 으로 죽지 않는다.
    """
    member = _member()
    pipeline = _pipeline(member)
    stage = _stage(pipeline, code="quote_sent", phase="quote", position=2)
    deal_type = _deal_type(member)
    company = _company(member)
    product = _product(member)
    deal = _deal(member, pipeline, stage, deal_type, company, product)
    quote_status_id = uuid4()
    db = _Db(
        _Result(scalar=1),
        _Result(rows=[_row(deal, member, pipeline, stage, deal_type, company, product)]),
        _Result(rows=[]),
        _Result(rows=[]),
        _Result(rows=[]),
        _Result(rows=[(quote_status_id, 1)]),
    )

    page = asyncio.run(
        api.list_sales_deals(
            SalesDealPageParams(has_quote=True, quote_status_id=[quote_status_id]),
            member,
            db,
        )
    )

    assert page.counts == {str(quote_status_id): 1}

    rows_sql = str(db.statements[1])
    counts_sql = str(db.statements[-1])
    # 두 쿼리 모두 "견적이 붙은 딜" 로 좁힌다. 단계(phase_code)는 조건이 아니다.
    assert "sales_deal.quote_status_id IS NOT NULL" in rows_sql
    assert "sales_deal.quote_status_id IS NOT NULL" in counts_sql
    # 고른 탭은 목록에만 걸리고 건수에는 걸리지 않는다.
    assert "sales_deal.quote_status_id IN" in rows_sql
    assert "sales_deal.quote_status_id IN" not in counts_sql
    assert "GROUP BY public.sales_deal.quote_status_id" in counts_sql


def test_quote_amount_is_the_sum_of_items_not_what_the_client_sent():
    """견적금액은 품목의 합이 정답이다. 화면이 보낸 값과 어긋나면 합계가 이긴다."""
    member = _member()
    company = _company(member)
    pipeline = _pipeline(member)
    stage = _stage(pipeline)
    deal_type = _deal_type(member)
    product = _product(member)
    deal = _deal(member, pipeline, stage, deal_type, company, product)
    deal.quote_amount = 999

    db = _Db(_Result(scalar_values=[product]), _Result())
    values = [
        SalesDealItemWrite(product_id=product.id, quantity=2, unit_price=1_500),
        SalesDealItemWrite(product_id=product.id, quantity=1, unit_price=4_000),
    ]

    asyncio.run(api._replace_items(db, member, deal, values))

    assert deal.quote_amount == 2 * 1_500 + 4_000
    # 줄은 통째로 갈아 끼운다. 남은 줄이 섞이면 합계와 표가 어긋난다.
    assert "DELETE FROM public.sales_deal_item" in str(db.statements[1])
    assert [(item.quantity, item.unit_price, item.position) for item in db.added] == [
        (2, 1_500, 0),
        (1, 4_000, 1),
    ]
    assert all(isinstance(item, SalesDealItem) for item in db.added)


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
    # 옮길 때마다 품목·미팅 대상자·최근 발주 상태를 딸려 읽는다. 이 시험은 두 번 옮긴다.
    db = _Db(*[_Result(rows=[]) for _ in range(6)])

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
        # 품목·미팅 대상자·최근 발주 상태는 쪽에 담긴 딜만 따로 훑는다.
        _Result(rows=[]),
        _Result(rows=[]),
        _Result(rows=[]),
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
    for statement in _deal_statements(db):
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
