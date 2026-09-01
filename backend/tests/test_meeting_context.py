"""CRM 컨텍스트 권한·시점·직렬화 검사. 실제 DB/API에는 연결하지 않는다."""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.agents.meeting_content_analysis import DealGroundingContext
from app.api import activities, reports, sales_deals
from app.models.content import Report
from app.models.crm import Activity, CustomerContact
from app.models.sales import Product, SalesDeal
from app.models.workspace import Member
from app.schemas.sales_deals import SalesDealItemRead, SalesDealParticipantRead
from app.services import meeting_context as service


class Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def all(self):
        return self.rows

    def one_or_none(self):
        assert len(self.rows) <= 1
        return next(iter(self.rows), None)

    def scalars(self):
        return self


class Db:
    def __init__(self, *results):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "Unexpected database query"
        return self.results.pop(0)


@pytest.fixture
def sample(monkeypatch):
    member = Member(
        id=uuid4(), team_id=uuid4(), active=True, role_code="member", display_name="합성 담당자"
    )
    company_id = uuid4()
    contact = CustomerContact(
        id=uuid4(),
        company_id=company_id,
        owner_member_id=member.id,
        name="합성 고객",
        department="구매부",
        job_title="팀장",
        source_code="referral",
        memo="업무 협의 담당",
    )
    meeting_at = datetime(2026, 8, 20, 9, tzinfo=UTC)
    activity = Activity(
        id=uuid4(),
        team_id=member.team_id,
        owner_member_id=member.id,
        title="합성 미팅",
        customer_contact_id=contact.id,
        starts_at=meeting_at,
        ends_at=meeting_at + timedelta(hours=1),
    )
    deals = [
        SalesDeal(
            id=uuid4(),
            team_id=member.team_id,
            owner_member_id=member.id,
            customer_company_id=company_id,
            customer_contact_id=contact.id,
            deal_no=f"D-{index}",
            title=f"합성 딜 {index}",
            description="업무 범위 검토",
            product_id=uuid4(),
            source_code="event",
            deal_amount=100_000,
            opened_on=date(2026, 8, 1),
            created_at=meeting_at - timedelta(days=30),
            updated_at=meeting_at - timedelta(days=1),
        )
        for index in range(2)
    ]
    activity_row = (activity, member.display_name, contact, company_id, "합성 회사", None)
    deal_rows = {
        deal.id: (
            deal,
            member.display_name,
            "합성 회사",
            None,
            contact.name,
            f"상품 {i}",
            "영업",
            "published",
            True,
            "negotiating",
            "협상",
            "blue",
            "sales",
            "in_progress",
            1,
            "new",
            "신규",
            None,
            None,
            None,
            None,
            None,
            None,
        )
        for i, deal in enumerate(deals)
    }
    get_activity = AsyncMock(return_value=activity_row)
    get_deal = AsyncMock(side_effect=lambda db, member, deal_id: deal_rows[deal_id])
    get_items = AsyncMock(return_value={})
    get_participants = AsyncMock(return_value={})
    monkeypatch.setattr(activities, "_activity_row", get_activity)
    monkeypatch.setattr(sales_deals, "_sales_deal_row", get_deal)
    monkeypatch.setattr(sales_deals, "_items_by_deal_ids", get_items)
    monkeypatch.setattr(sales_deals, "_participants_by_deal_ids", get_participants)
    return {
        "member": member,
        "activity": activity,
        "contact": contact,
        "deals": deals,
        "ids": [deal.id for deal in deals],
        "activity_row": activity_row,
        "deal_rows": deal_rows,
        "get_activity": get_activity,
        "get_deal": get_deal,
        "get_items": get_items,
        "get_participants": get_participants,
    }


def build(sample, db):
    return asyncio.run(
        service.build_context(
            db,
            sample["member"],
            sample["activity"].id,
            sample["ids"],
        )
    )


def extra(sample, db, kind, deal_id=None):
    return asyncio.run(
        service.load_extra_context(
            db,
            sample["member"],
            sample["activity"].id,
            sample["ids"],
            kind,
            deal_id if deal_id is not None else sample["ids"][0],
        )
    )


def test_build_returns_grounding_and_serializable_current_crm(sample):
    deal = sample["deals"][0]
    item_id = uuid4()
    sample["get_items"].return_value = {
        deal.id: [
            SalesDealItemRead(
                id=uuid4(),
                product_id=item_id,
                product_name="추가 상품",
                quantity=2,
                unit_price=500,
                position=0,
            )
        ]
    }
    sample["get_participants"].return_value = {
        deal.id: [
            SalesDealParticipantRead(
                customer_contact_id=sample["contact"].id,
                customer_contact_name="합성 고객",
            )
        ]
    }

    result = build(sample, Db(Result(), Result(), Result()))

    json.dumps(result, ensure_ascii=False)
    assert [DealGroundingContext.model_validate(row).sales_deal_id for row in result["deals"]] == (
        sample["ids"]
    )
    assert result["deals"][0]["product_names"] == ["상품 0", "추가 상품"]
    crm = result["crm_context"]
    assert crm["contact"]["department"] == "구매부"
    assert crm["activity"]["starts_at"] == sample["activity"].starts_at.isoformat()
    assert crm["deals"][0]["id"] == crm["deals"][0]["sales_deal_id"] == str(deal.id)
    assert crm["deals"][0]["source_code"] == "referral"  # 고객값이 딜의 event보다 우선
    assert crm["deals"][0]["source_origin"] == "contact"
    assert crm["deals"][0]["products"][1]["product_id"] == str(item_id)
    assert crm["deals"][0]["participants"][0]["customer_contact_name"] == "합성 고객"
    assert crm["trade_history"] == []
    assert [history["items"] for history in crm["previous_reports"]] == [[], []]
    assert "not_proof_of_new_client" in crm["trade_history_metadata"]["empty_means"]
    assert not {"transcript", "ml", "golden"} & crm.keys()


@pytest.mark.parametrize("ids", [[], ["not-uuid"], [uuid4()] * 2, [uuid4() for _ in range(101)]])
def test_rejects_invalid_selection_before_loading_context(sample, ids):
    sample["ids"] = ids
    with pytest.raises(HTTPException) as error:
        build(sample, Db())
    assert error.value.detail == "selected_deal_ids_invalid"
    sample["get_activity"].assert_not_awaited()


def test_manager_cannot_analyze_someone_elses_activity(sample):
    sample["member"].role_code = "manager"
    sample["activity"].owner_member_id = uuid4()
    with pytest.raises(HTTPException) as error:
        build(sample, Db())
    assert error.value.status_code == 403
    assert error.value.detail == "activity_not_owned"
    sample["get_deal"].assert_not_awaited()


def test_wrong_company_or_inaccessible_deal_is_rejected(sample):
    sample["deals"][1].customer_company_id = uuid4()
    with pytest.raises(HTTPException) as error:
        build(sample, Db())
    assert error.value.status_code == 404
    sample["get_items"].assert_not_awaited()
    sample["get_deal"].side_effect = HTTPException(status_code=404, detail="deal_not_found")
    with pytest.raises(HTTPException, match="deal_not_found"):
        build(sample, Db())


@pytest.mark.parametrize(
    "kind,deal_id,detail",
    [
        ("raw_transcript", None, "meeting_context_kind_invalid"),
        ("product_details", uuid4(), "context_deal_not_selected"),
    ],
)
def test_extra_tools_reject_arbitrary_kind_or_unselected_deal(sample, kind, deal_id, detail):
    with pytest.raises(HTTPException) as error:
        extra(sample, Db(), kind, deal_id)
    assert error.value.detail == detail
    sample["get_activity"].assert_not_awaited()


def test_history_is_company_scoped_completed_and_strictly_before_meeting(sample):
    old = SalesDeal(
        id=uuid4(),
        customer_company_id=sample["contact"].company_id,
        deal_no="PAST-1",
        title="이전 계약",
        product_id=uuid4(),
        closed_on=date(2026, 8, 18),
        contract_signed_on=date(2026, 8, 1),
        contract_amount=30_000,
    )
    db = Db(Result([(old, "이전 상품")] * (service.INITIAL_HISTORY_LIMIT + 1)), Result(), Result())

    result = build(sample, db)["crm_context"]

    assert len(result["trade_history"]) == service.INITIAL_HISTORY_LIMIT
    row = result["trade_history"][0]
    assert row["customer_company_id"] == str(sample["contact"].company_id)
    assert row["sales_deal_id"] == str(old.id)
    assert row["closed_on"] == "2026-08-18"
    assert "delivered_at" not in row
    assert result["trade_history_metadata"]["truncated"] is True
    statement = db.statements[0].compile(dialect=postgresql.dialect())
    sql, params = str(statement), statement.params
    for predicate in [
        "sales_deal.team_id =",
        "sales_deal.owner_member_id =",
        "sales_deal.customer_company_id =",
        "sales_deal.id NOT IN",
        "phase_code =",
        "outcome_code =",
        "sales_deal.closed_on <",
        "sales_deal.created_at <",
        "sales_deal.updated_at <",
        "sales_deal.contract_signed_on <= public.sales_deal.closed_on",
    ]:
        assert predicate in sql
    assert "closed" in params.values() and "confirmed" in params.values()
    assert sample["activity"].starts_at in params.values()
    assert date(2026, 8, 20) in params.values()


def test_extra_history_has_larger_explicit_limit_and_company_scope(sample):
    db = Db(Result())
    result = extra(sample, db, "trade_history")
    assert result["limit"] == service.EXTRA_HISTORY_LIMIT
    assert result["kind"] == "trade_history"
    assert result["sales_deal_id"] == str(sample["ids"][0])
    assert result["items"] == []
    assert "same_company" in result["scope"]


def test_previous_reports_read_only_deal_values_without_raw_ml_or_shared(sample):
    report_id = uuid4()
    values = {
        "body": "확정한 이전 딜 내용",
        "transcript": "원문 금지",
        "ml_result": "승리",
        "meeting_shared": "공통 금지",
        "common_report": "공통 금지",
        "unassigned_report": "미지정 금지",
    }
    meeting_at = sample["activity"].starts_at - timedelta(days=1)
    db = Db(Result([(report_id, date(2026, 8, 1), values, meeting_at, "approved")]))

    result = extra(sample, db, "previous_reports")

    assert result["items"][0]["values"] == {"body": "확정한 이전 딜 내용"}
    assert result["items"][0]["report_id"] == str(report_id)
    assert result["items"][0]["meeting_at"] == meeting_at.isoformat()
    assert result["items"][0]["status_code"] == "approved"
    assert result["time_basis"] == "historical_context_not_current_meeting_facts"
    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    for predicate in [
        "report.team_id =",
        "report.author_member_id =",
        "report.sales_deal_id =",
        "report.source_activity_id !=",
        "activity.team_id =",
        "activity.starts_at <",
        "report.created_at <",
        "report.updated_at <",
        "report.status_code IN",
        "activity.deleted_at IS NULL",
    ]:
        assert predicate in sql
    assert "values" in compiled.params.values()
    assert "transcript" not in sql and "ai_evidence" not in sql and "source_snapshot" not in sql
    assert ["submitted", "approved"] in compiled.params.values()
    assert sample["ids"][0] in compiled.params.values()
    assert sample["activity"].starts_at in compiled.params.values()
    assert "ORDER BY public.activity.starts_at DESC" in sql


def test_initial_history_is_loaded_once_per_deal_using_the_same_scoped_query(sample):
    meeting_at = sample["activity"].starts_at - timedelta(days=1)
    rows = [
        (uuid4(), meeting_at.date(), {"body": f"이전 논의 {i}"}, meeting_at, "submitted")
        for i in range(service.PREVIOUS_REPORT_LIMIT + 1)
    ]
    db = Db(Result(), Result(rows), Result())

    histories = build(sample, db)["crm_context"]["previous_reports"]

    assert len(db.statements) == 3  # 거래 이력 1회, 선택 딜 2개의 보고서 각 1회
    sample["get_activity"].assert_awaited_once()
    assert sample["get_deal"].await_count == 2
    assert [history["sales_deal_id"] for history in histories] == list(map(str, sample["ids"]))
    assert len(histories[0]["items"]) == service.PREVIOUS_REPORT_LIMIT
    assert histories[0]["truncated"] is True
    assert histories[1]["items"] == [] and histories[1]["truncated"] is False
    assert "not_proof" in histories[1]["empty_means"]
    assert histories[0] == extra(sample, Db(Result(rows)), "previous_reports")
    assert histories[0]["items"][0]["status_code"] == "submitted"
    for statement, deal_id in zip(db.statements[1:], sample["ids"], strict=True):
        params = statement.compile(dialect=postgresql.dialect()).params
        assert deal_id in params.values()
        assert service.PREVIOUS_REPORT_LIMIT + 1 in params.values()


def test_report_values_have_explicit_text_limit_and_no_legacy_root_fallback():
    assert service._report_values(None) == ({}, False)
    cleaned, truncated = service._report_values({"body": "가" * (service.REPORT_TEXT_LIMIT + 5)})
    assert len(cleaned["body"]) == service.REPORT_TEXT_LIMIT
    assert truncated is True


def test_product_lookup_is_bound_to_selected_deal_team_and_returns_no_storage_key(sample):
    product = Product(
        id=sample["deals"][0].product_id,
        name="단종 상품",
        active=False,
        category_code="system",
        unit_price=50_000,
        shelf_life_months=None,
        memo="규격",
        image_storage_key="private/storage",
    )
    db = Db(Result([product]))

    result = extra(sample, db, "product_details")

    json.dumps(result)
    assert result["items"][0]["active"] is False
    assert "image_storage_key" not in result["items"][0]
    assert result["time_basis"] == "current_catalog_not_historical_price"
    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "product.team_id =" in sql
    assert "sales_deal_item.sales_deal_id =" in sql
    assert sample["ids"][0] in compiled.params.values()
    assert sample["member"].team_id in compiled.params.values()


def test_db_failure_is_not_silently_changed_to_unknown_or_empty(sample):
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("synthetic database failure")
    with pytest.raises(RuntimeError, match="synthetic database failure"):
        extra(sample, db, "previous_reports")


def test_unknown_legacy_source_is_not_guessed_as_other():
    assert service._source("legacy-source", "referral")["source_code"] is None
    assert service._source(None, "event") == {"source_code": "event", "source_origin": "deal"}


def test_product_limit_includes_primary_product_not_an_extra_unbounded_row(sample):
    items = [
        SalesDealItemRead(
            id=uuid4(),
            product_id=uuid4(),
            product_name=f"추가 상품 {index}",
            quantity=1,
            unit_price=100,
            position=index,
        )
        for index in range(service.RELATED_ITEM_LIMIT)
    ]
    products, truncated = service._products(sample["deals"][0], "대표 상품", items)
    assert len(products) == service.RELATED_ITEM_LIMIT
    assert products[0]["id"] == sample["deals"][0].product_id
    assert truncated is True


def test_existing_access_scopes_keep_member_and_team_boundaries(sample):
    member = sample["member"]
    activity_sql = str(activities._joined_select(Activity).where(*activities._scope(member)))
    deal_sql = str(sales_deals._joined_select(SalesDeal).where(*sales_deals._scope(member)))
    report_sql = str(reports._joined_select(Report).where(*reports._scope(member)))
    assert "activity.team_id =" in activity_sql and "activity.owner_member_id =" in activity_sql
    assert "sales_deal.team_id =" in deal_sql and "sales_deal.owner_member_id =" in deal_sql
    assert "report.team_id =" in report_sql and "report.author_member_id =" in report_sql
