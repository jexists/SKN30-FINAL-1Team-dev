import json
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents import document_summary
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


class _StateDb:
    """최신 거래 문서 조회와 청크 조회를 순서대로 돌려주는 최소 DB 이중체."""

    def __init__(self, document_rows, chunks):
        self.document_rows = document_rows
        self.chunks = chunks
        self.calls = 0

    async def execute(self, _statement):
        self.calls += 1
        if self.calls == 1:
            return _Result(self.document_rows)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self.chunks.pop(0)))


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
    document = SimpleNamespace(id=document_id, category_code="계약서", sales_deal_id=None)

    async def _search(*_args, **_kwargs):
        return [(chunk, 0.91)]

    monkeypatch.setattr(document_processing, "search_chunks", _search)
    context = await sales_context.retrieve_briefing_context(
        _Db([(file_row, document)]),
        team_id=team_id,
        query="계약금",
    )

    assert context["query"] == "계약금"
    assert context["sources"][0]["file_name"] == "계약서.docx"
    assert context["sources"][0]["score"] == 0.91
    assert context["sources"][0]["category_code"] == "계약서"
    assert context["summaries"][0]["summary_payload"]["summary"] == "계약금은 선납한다."


@pytest.mark.anyio
async def test_retrieve_current_state_sources_keeps_latest_trade_chunks_as_citable_data():
    team_id, company_id, document_id, file_id, chunk_id = (uuid4() for _ in range(5))
    document = SimpleNamespace(
        id=document_id,
        team_id=team_id,
        category_code="contract",
        sales_deal_id=None,
        product_id=None,
        created_at=datetime(2026, 9, 16),
    )
    file_row = SimpleNamespace(id=file_id, file_name="최신 계약서.pdf")
    chunk = SimpleNamespace(
        id=chunk_id,
        document_id=document_id,
        file_id=file_id,
        chunk_no=2,
        page_start=1,
        page_end=1,
        section="지급 조건",
        content="계약금 30%, 잔금 70%입니다.",
        metadata_json={},
    )

    sources = await sales_context.retrieve_current_state_sources(
        _StateDb([(document, file_row)], [[chunk]]),
        team_id=team_id,
        customer_company_id=company_id,
    )

    assert sources == [
        {
            "chunk_id": str(chunk_id),
            "document_id": str(document_id),
            "file_id": str(file_id),
            "file_name": "최신 계약서.pdf",
            "category_code": "contract",
            "sales_deal_id": None,
            "product_id": None,
            "chunk_no": 2,
            "page_start": 1,
            "page_end": 1,
            "section": "지급 조건",
            "content": "계약금 30%, 잔금 70%입니다.",
            "score": None,
            "metadata": {},
            "source_role": "current_sales_state",
            "state_document_kind": "contract",
            "state_document_created_at": "2026-09-16T00:00:00",
        }
    ]


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


def test_to_briefing_prompt_block_separates_state_product_catalog_and_product_evidence():
    block = sales_context.to_briefing_prompt_block(
        {
            "query": "설치와 계약 조건",
            "current_state_sources": [
                {
                    "document_id": "contract-1",
                    "chunk_id": "contract-chunk-1",
                    "file_name": "최신 계약서.pdf",
                    "category_code": "contract",
                    "state_document_kind": "contract",
                    "state_document_created_at": "2026-09-16T09:00:00+09:00",
                    "content": "계약금 30%, 잔금 70%로 합의했다.",
                }
            ],
            "product_documents": [
                {
                    "document_id": "product-1",
                    "file_name": "LR2000.pdf",
                    "category_code": "product_brochure",
                    "summary_markdown": "설치 공간과 전원 조건을 확인한다.",
                }
            ],
            "sources": [
                {
                    "document_id": "contract-1",
                    "chunk_id": "contract-chunk-1",
                    "file_name": "최신 계약서.pdf",
                    "content": "계약금 30%, 잔금 70%로 합의했다.",
                },
                {
                    "document_id": "product-1",
                    "chunk_id": "product-chunk-1",
                    "file_name": "LR2000.pdf",
                    "content": "설치 공간은 1000mm 이상 필요하다.",
                },
            ],
        }
    )

    assert "[현재 영업 상태]" in block
    assert "[연결된 제품 자료 목록]" in block
    assert "[제품 상세 근거]" in block
    assert "계약금 30%, 잔금 70%" in block
    assert "설치 공간은 1000mm 이상" in block
    assert block.count("contract-chunk-1") == 1


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
    deal_id = uuid4()
    document = SimpleNamespace(id=document_id, category_code="계약서", sales_deal_id=deal_id)

    async def _search(*_args, **_kwargs):
        return [(chunk, 0.9)]

    monkeypatch.setattr(document_processing, "search_chunks", _search)

    context = await sales_context.retrieve_briefing_context(
        _Db([(file_row, document)]),
        team_id=uuid4(),
        query="계약금",
        sales_deal_id=uuid4(),
    )

    json.dumps(context)  # 여기서 TypeError 가 나면 브리핑 실행을 만들 수 없다.
    assert context["sources"][0]["chunk_id"] == str(chunk_id)
    assert context["summaries"][0]["document_id"] == str(document_id)
    assert context["summaries"][0]["sales_deal_id"] == str(deal_id)


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


def test_current_state_score_counts_money_and_dates_not_length():
    """조건이 적힌 칸은 긴 칸이 아니라 금액·날짜가 든 칸이다."""
    items = "| LR1000 | 1 | 4,500,000 |\n| LR-PRO | 2 | 12,000,000 |"
    # 약관은 길지만 값이 없다.
    terms = (
        '8.2 "을"과 사전 협의 없이 "갑"이 임의로 제품의 사양을 변경하거나 분해 또는 '
        '조립하여 발생된 고장은 "을"이 책임지지 아니한다. ' * 2
    )
    assert len(terms) > len(items)
    assert sales_context.current_state_score(items) > sales_context.current_state_score(terms)
    assert sales_context.current_state_score(terms) == 0
    # 날짜만 있는 짧은 칸도 조건이다 — 납기가 여기 있다.
    assert sales_context.current_state_score("공급일자 : 2026 년 09 월 22 일 까지") > 0


def test_select_current_state_chunks_keeps_the_short_delivery_date_clause():
    """계약서 실측 재현: 길이순이면 품목표(5위)와 납기(16위)가 약관에 밀려 빠진다."""
    contents = [
        "물품 공급 계약서",
        "| LR1000 | 1 | 4,500,000 | | LR-PRO | 2 | 12,000,000 | 합계 19,295,000 |",
        "공급일자 : 2026 년 09 월 22 일 까지",
        "계약금 1,929,500 원 / 잔금 17,365,500 원 / 납품 후 7 일 이내 결제 시 15% 할인",
        "제 8 조 책임한계. " + "고장은 책임지지 아니한다. " * 30,
        "제 9 조 계약의 해제 또는 해지. " + "즉시 해지할 수 있다. " * 30,
    ]
    picked = sales_context.select_current_state_chunks(contents)
    assert 1 in picked, "품목표"
    assert 2 in picked, "납기"
    assert 3 in picked, "계약금·잔금"
    # 문서 순서로 돌려줘야 계약금 → 잔금 같은 앞뒤 관계가 프롬프트에서 살아 있다.
    assert picked == sorted(picked)


def test_select_current_state_chunks_skips_only_what_does_not_fit():
    """예산을 넘는 칸에서 멈추면 큰 약관 하나가 뒤의 짧은 금액 칸까지 막는다."""
    budget = sales_context._CURRENT_STATE_DOC_CHARS
    contents = [
        # 점수가 가장 높지만 혼자 예산을 거의 다 먹는다.
        "1,000,000 " * (budget // 10 + 1),
        "잔금 17,365,500 원",
    ]
    assert len(contents[0]) > budget
    assert sales_context.select_current_state_chunks(contents) == [1]


def test_current_state_doc_budget_always_admits_one_chunk():
    """예산을 청크 상한의 배수로 파생해 '첫 칸조차 안 들어가는' 상태를 없앤다."""
    assert sales_context._CURRENT_STATE_DOC_CHARS >= document_summary.CHUNK_SIZE
    longest = "x" * document_summary.CHUNK_SIZE
    assert sales_context.select_current_state_chunks([longest]) == [0]


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
