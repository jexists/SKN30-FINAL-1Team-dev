from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import activity_documents

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

    def scalar_one_or_none(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def all(self):
        return self.rows

    def scalars(self):
        return _Scalars(self.scalar_values)


class _Db:
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "예상보다 많은 쿼리가 실행되었습니다."
        return self.results.pop(0)


def _activity(*, sales_deal_id=None, product_id=None):
    return SimpleNamespace(id=uuid4(), sales_deal_id=sales_deal_id, product_id=product_id)


def _document(title: str):
    return SimpleNamespace(
        id=uuid4(),
        document_no=f"DOC-{title}",
        category_code="contract",
        title=title,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


def _file(file_name: str, version_no: int, summary: str | None = None):
    return SimpleNamespace(
        id=uuid4(),
        file_name=file_name,
        version_no=version_no,
        summary_markdown=summary,
        uploaded_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


@pytest.mark.anyio
async def test_related_documents_keep_only_the_latest_file_version():
    """문서 하나가 버전을 여러 개 들고 있어도 목록에는 한 줄만 선다."""
    document = _document("계약서")
    db = _Db(
        # 정렬이 최신 버전을 먼저 주므로 첫 행만 담긴다.
        _Result(rows=[(document, _file("계약서_v2.pdf", 2)), (document, _file("계약서.pdf", 1))]),
        _Result(scalar=None),  # 딜의 상품
        _Result(scalar_values=[]),  # 딜 견적 품목의 상품
    )

    groups = await activity_documents.list_for_activity(
        db,
        team_id=uuid4(),
        activity=_activity(sales_deal_id=uuid4()),
        customer_company_id=uuid4(),
    )

    assert [item["file_name"] for item in groups["related"]] == ["계약서_v2.pdf"]
    assert groups["product"] == []


@pytest.mark.anyio
async def test_documents_carry_the_saved_summary():
    """자료요약 Agent 가 저장한 요약을 파일명과 함께 내려 화면이 다시 조회하지 않는다."""
    db = _Db(
        _Result(rows=[(_document("계약서"), _file("계약서.pdf", 1, summary="## 결제 조건"))]),
        _Result(scalar=None),
        _Result(scalar_values=[]),
    )

    groups = await activity_documents.list_for_activity(
        db,
        team_id=uuid4(),
        activity=_activity(sales_deal_id=uuid4()),
        customer_company_id=uuid4(),
    )

    assert groups["related"][0]["summary_markdown"] == "## 결제 조건"


@pytest.mark.anyio
async def test_product_documents_are_separated_and_not_duplicated():
    """예전 자료는 상품과 고객사를 함께 들고 있다 — 양쪽에 같은 문서를 세우지 않는다."""
    shared = _document("공용")
    catalog = _document("카탈로그")
    db = _Db(
        _Result(rows=[(shared, _file("공용.pdf", 1))]),
        _Result(rows=[(shared, _file("공용.pdf", 1)), (catalog, _file("카탈로그.pdf", 1))]),
    )

    groups = await activity_documents.list_for_activity(
        db,
        team_id=uuid4(),
        activity=_activity(product_id=uuid4()),
        customer_company_id=uuid4(),
    )

    assert [item["title"] for item in groups["related"]] == ["공용"]
    assert [item["title"] for item in groups["product"]] == ["카탈로그"]


@pytest.mark.anyio
async def test_activity_without_links_runs_no_query():
    """딜도 고객사도 상품도 없으면 조회할 것이 없다 — 빈 IN 절을 만들지 않는다."""
    db = _Db()

    groups = await activity_documents.list_for_activity(
        db, team_id=uuid4(), activity=_activity(), customer_company_id=None
    )

    assert groups == {"related": [], "product": []}
    assert db.statements == []


@pytest.mark.anyio
async def test_product_ids_collect_activity_deal_and_quote_items():
    """상품은 미팅·딜·견적 품목 세 곳에 걸려 있어 전부 모아야 자료가 빠지지 않는다."""
    activity_product_id = uuid4()
    deal_product_id = uuid4()
    item_product_id = uuid4()
    db = _Db(_Result(scalar=deal_product_id), _Result(scalar_values=[item_product_id]))

    product_ids = await activity_documents._product_ids(
        db,
        team_id=uuid4(),
        activity=_activity(sales_deal_id=uuid4(), product_id=activity_product_id),
    )

    assert product_ids == {activity_product_id, deal_product_id, item_product_id}
