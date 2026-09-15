import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.content import Document
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


def _scope():
    return Document.sales_deal_id == uuid4()


@pytest.mark.anyio
async def test_documents_keep_only_one_file_per_document():
    """예전 자료가 파일을 여러 개 들고 있어도 목록에는 한 줄만 선다."""
    document = _document("계약서")
    db = _Db(
        # 정렬이 나중에 올린 것을 먼저 주므로 첫 행만 담긴다.
        _Result(rows=[(document, _file("계약서_v2.pdf", 2)), (document, _file("계약서.pdf", 1))])
    )

    documents = await activity_documents.list_documents(db, team_id=uuid4(), scopes=[_scope()])

    assert [item["file_name"] for item in documents] == ["계약서_v2.pdf"]
    assert json.loads(json.dumps(documents))[0]["file_name"] == "계약서_v2.pdf"


@pytest.mark.anyio
async def test_documents_carry_the_saved_summary():
    """자료요약 Agent 가 저장한 요약을 파일명과 함께 내려 화면이 다시 조회하지 않는다."""
    db = _Db(_Result(rows=[(_document("계약서"), _file("계약서.pdf", 1, summary="## 결제 조건"))]))

    documents = await activity_documents.list_documents(db, team_id=uuid4(), scopes=[_scope()])

    assert documents[0]["summary_markdown"] == "## 결제 조건"


@pytest.mark.anyio
async def test_no_scope_runs_no_query():
    """딜도 고객사도 상품도 없으면 조회할 것이 없다 — 빈 IN 절을 만들지 않는다."""
    db = _Db()

    assert await activity_documents.list_documents(db, team_id=uuid4(), scopes=[]) == []
    assert db.statements == []


@pytest.mark.anyio
async def test_product_ids_collect_activity_deal_and_quote_items():
    """상품은 미팅·딜·견적 품목 세 곳에 걸려 있어 전부 모아야 자료가 빠지지 않는다."""
    activity_product_id = uuid4()
    deal_product_id = uuid4()
    item_product_id = uuid4()
    db = _Db(
        _Result(scalar_values=[deal_product_id]),
        _Result(scalar_values=[item_product_id]),
    )

    product_ids = await activity_documents.product_ids(
        db,
        team_id=uuid4(),
        activity=_activity(sales_deal_id=uuid4(), product_id=activity_product_id),
    )

    assert product_ids == {deal_product_id, item_product_id}
    assert all("team_id" in str(statement) for statement in db.statements)


@pytest.mark.anyio
async def test_product_ids_collect_products_from_multiple_candidate_deals():
    deal_ids = [uuid4(), uuid4()]
    product_ids = [uuid4(), uuid4()]
    item_product_id = uuid4()
    db = _Db(_Result(scalar_values=product_ids), _Result(scalar_values=[item_product_id]))

    found = await activity_documents.product_ids_for_deals(
        db, team_id=uuid4(), sales_deal_ids=deal_ids
    )

    assert found == {*product_ids, item_product_id}
    assert all(
        "sales_deal.id IN" in str(statement)
        or "sales_deal_item.sales_deal_id IN" in str(statement)
        for statement in db.statements
    )


@pytest.mark.anyio
async def test_activity_product_without_deal_is_not_used():
    db = _Db()
    assert (
        await activity_documents.product_ids(
            db, team_id=uuid4(), activity=_activity(product_id=uuid4())
        )
        == set()
    )
    assert db.statements == []


@pytest.mark.anyio
async def test_report_product_name_adds_its_document_scope():
    lr1000_id = uuid4()
    unrelated_id = uuid4()
    db = _Db(_Result(rows=[(lr1000_id, "LR1000"), (unrelated_id, "LR2000")]))

    found = await activity_documents.mentioned_product_ids(
        db,
        team_id=uuid4(),
        values=[{"common_body": "다음 미팅에서는 lr1000 도입 조건을 논의합니다."}],
    )

    assert found == {lr1000_id}
    assert "product.active IS true" in str(db.statements[0])
