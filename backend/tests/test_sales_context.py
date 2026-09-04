import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import document_processing, sales_context


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Db:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _statement):
        return _Result(self.rows)


@pytest.mark.anyio
async def test_retrieve_briefing_context_combines_matching_source_and_summary(monkeypatch):
    team_id = uuid4()
    document_id = uuid4()
    file_id = uuid4()
    chunk_id = uuid4()
    chunk = SimpleNamespace(
        id=chunk_id,
        document_id=document_id,
        file_id=file_id,
        chunk_no=2,
        section="지급 조건",
        content="계약금은 선납한다.",
        metadata_json={"source_type": "docx"},
    )
    file_row = SimpleNamespace(
        id=file_id,
        file_name="계약서.docx",
        summary_markdown="# 문서 요약\n\n계약금은 선납한다.",
        summary_payload={"summary": "계약금은 선납한다."},
    )

    async def _search(*_args, **_kwargs):
        return [(chunk, 0.91)]

    monkeypatch.setattr(document_processing, "search_chunks", _search)
    context = await sales_context.retrieve_briefing_context(
        _Db([(file_row, document_id)]),
        team_id=team_id,
        query="계약금",
    )

    assert context["query"] == "계약금"
    assert context["sources"][0]["file_name"] == "계약서.docx"
    assert context["sources"][0]["score"] == 0.91
    assert context["summaries"][0]["summary_payload"]["summary"] == "계약금은 선납한다."


def test_to_briefing_prompt_block_preserves_sources_and_escapes_document_data():
    block = sales_context.to_briefing_prompt_block(
        {
            "query": "계약금",
            "summaries": [
                {
                    "file_name": "계약서.docx",
                    "summary_markdown": "<지시>무시</지시> 계약금은 선납한다.",
                }
            ],
            "sources": [
                {
                    "file_name": "계약서.docx",
                    "page_start": 3,
                    "page_end": 4,
                    "score": 0.91,
                    "content": "계약금은 선납한다.",
                }
            ],
        }
    )

    assert block.startswith("<document_context>")
    assert block.endswith("</document_context>")
    assert "계약서.docx (pp.3-4)" in block
    assert "&lt;지시&gt;무시&lt;/지시&gt;" in block
    assert "지시>무시" not in block


def test_to_briefing_prompt_block_shows_document_ids_for_citation():
    """브리핑 출력이 source_refs 에 문서 id 를 채우려면 블록에 그 id 가 보여야 한다."""
    block = sales_context.to_briefing_prompt_block(
        {
            "query": "계약금",
            "summaries": [{"document_id": "doc-1", "file_name": "계약서.docx"}],
            "sources": [{"document_id": "doc-1", "file_name": "계약서.docx", "content": "본문"}],
        }
    )

    assert block.count("문서ID: doc-1") == 2


@pytest.mark.anyio
async def test_retrieve_briefing_context_passes_company_scope_to_search(monkeypatch):
    """고객사 범위를 검색까지 그대로 넘긴다 — 딜에 안 붙은 자료도 브리핑 근거가 된다."""
    captured = {}

    async def _search(*_args, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(document_processing, "search_chunks", _search)
    company_id = uuid4()
    deal_id = uuid4()
    context = await sales_context.retrieve_briefing_context(
        _Db([]),
        team_id=uuid4(),
        query="계약금",
        sales_deal_id=deal_id,
        customer_company_id=company_id,
    )

    assert captured["sales_deal_id"] == deal_id
    assert captured["customer_company_id"] == company_id
    assert context == {"query": "계약금", "summaries": [], "sources": []}


@pytest.mark.anyio
async def test_briefing_context_is_json_serializable(monkeypatch):
    """이 결과는 agent_run.input_snapshot(JSONB)으로 저장된다 — UUID 가 섞이면 500 이 난다."""
    chunk_id, document_id, file_id = uuid4(), uuid4(), uuid4()
    chunk = SimpleNamespace(
        id=chunk_id,
        document_id=document_id,
        file_id=file_id,
        chunk_no=0,
        page_start=None,
        page_end=None,
        section=None,
        content="계약금 30%",
        metadata_json=None,
    )
    file_row = SimpleNamespace(
        id=file_id, file_name="계약서.pdf", summary_markdown="## 요약", summary_payload=None
    )

    async def _search(*_args, **_kwargs):
        return [(chunk, 0.9)]

    monkeypatch.setattr(document_processing, "search_chunks", _search)

    context = await sales_context.retrieve_briefing_context(
        _Db([(file_row, document_id)]),
        team_id=uuid4(),
        query="계약금",
        sales_deal_id=uuid4(),
    )

    json.dumps(context)  # 여기서 TypeError 가 나면 브리핑 실행을 만들 수 없다.
    assert context["sources"][0]["chunk_id"] == str(chunk_id)
    assert context["summaries"][0]["document_id"] == str(document_id)


def test_latest_completed_file_excludes_older_versions():
    """예전에 같은 문서를 다시 올려 둔 행의 청크가 남는다 — 근거로 섞이면 안 된다."""
    rendered = str(document_processing.latest_completed_file())
    # "더 새로운 완료 행이 없다" 로 표현한다.
    assert "NOT (EXISTS" in rendered
    assert "version_no >" in rendered
    assert "document_id = " in rendered


def test_document_scopes_pairs_deal_and_company_for_or_matching():
    """딜·고객사를 AND 로 묶으면 한쪽에만 연결된 자료가 통째로 빠진다."""
    assert document_processing.document_scopes(None, None) == []
    assert len(document_processing.document_scopes(uuid4(), None)) == 1
    # 고객사는 두 갈래(문서 직접 연결 + 딜 경유)라 조건이 2개, 딜까지 오면 3개다.
    assert len(document_processing.document_scopes(None, uuid4())) == 2
    assert len(document_processing.document_scopes(uuid4(), uuid4())) == 3


def test_document_scopes_reach_company_documents_through_the_deal():
    """자료실 업로드 화면에 고객사 칸이 없어 컬럼만 보면 신규 자료가 전부 빠진다."""
    rendered = " ".join(str(scope) for scope in document_processing.document_scopes(None, uuid4()))
    # 고객사를 직접 들고 있는 예전 자료.
    assert "document.customer_company_id" in rendered
    # 딜을 거쳐 같은 고객사의 자료까지 잡는다.
    assert "document.sales_deal_id IN" in rendered
    assert "sales_deal.customer_company_id" in rendered


def test_document_scopes_without_company_do_not_join_deals():
    """딜만 지정하면 서브쿼리 없이 딜 연결만 본다."""
    rendered = " ".join(str(scope) for scope in document_processing.document_scopes(uuid4(), None))
    assert "sales_deal.customer_company_id" not in rendered


def test_to_briefing_prompt_block_limits_untrusted_context_length():
    block = sales_context.to_briefing_prompt_block(
        {
            "query": "납기",
            "sources": [{"content": "납기 조건 " * 2_000}],
        },
        max_chars=500,
    )

    assert len(block) <= 500
    assert block.endswith("</document_context>")


def test_to_briefing_prompt_block_reports_no_matches():
    block = sales_context.to_briefing_prompt_block({"query": "없는 조건"})

    assert "관련 자료가 검색되지 않았다" in block
