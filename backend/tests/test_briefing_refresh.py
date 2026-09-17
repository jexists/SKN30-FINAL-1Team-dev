"""AI 브리핑 입력 지문과 "재생성 필요" 판단.

브리핑은 일정 등록 때 한 번 만들고, 그 뒤에는 사람이 새로고침을 눌렀을 때만 다시 만든다.
여기서 지키려는 것은 셋이다.

* 브리핑 내용이 달라질 만한 입력(자료·보고서·딜·일정·고객·C/S)이 바뀌면 지문이 반드시 바뀐다.
* 같은 상태면 지문이 같다 — 아무것도 안 바뀌었는데 "재생성 필요"가 뜨지 않는다.
* 늦게 끝난 옛 실행이 더 새 자료로 만든 브리핑을 덮지 않고, 실패한 재생성이 마지막 성공
  브리핑을 지우지 않는다.
"""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.agent import AgentRun
from app.models.crm import Activity
from app.models.workspace import Member
from app.services import briefing_refresh

NOW = datetime(2026, 9, 12, 9, tzinfo=UTC)


class _Result:
    def __init__(self, *, scalar=None, scalars=(), rows=(), one=None):
        self._scalar = scalar
        self._scalars = list(scalars)
        self._rows = list(rows)
        self._one = one

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._scalars))

    def all(self):
        return list(self._rows)

    def one_or_none(self):
        return self._one


class _Session:
    """문장 본문을 보고 답을 고르는 가짜 세션. 질의 순서에 묶이지 않게 한다."""

    def __init__(
        self,
        *,
        member=None,
        deal_product=None,
        deals=(),
        item_products=(),
        files=(),
        reports=(),
        products=(),
        company_name="고객사",
        contact=("김담당", "구매팀", "과장"),
        prior_meeting=None,
        support_requests=(),
    ):
        self.member = member
        self.deal_product = deal_product
        self.deals = deals
        self.item_products = item_products
        self.files = files
        self.reports = reports
        self.products = products
        self.company_name = company_name
        self.contact = contact
        self.prior_meeting = prior_meeting
        self.support_requests = support_requests
        self.statements = []

    async def execute(self, statement):
        text = str(statement)
        self.statements.append(text)
        # 바깥 FROM 절부터 본다. 자료 조회에는 공개 범위(member)와 고객사 범위(sales_deal)
        # 하위 질의가 들어 있어서, 덜 구체적인 조건을 먼저 보면 엉뚱한 답을 돌려준다.
        if "FROM public.sales_deal" in text and "sales_deal.product_id" in text:
            return _Result(scalars=(() if self.deal_product is None else (self.deal_product,)))
        for marker, result in (
            ("FROM public.document", _Result(rows=self.files)),
            ("FROM public.support_request", _Result(rows=self.support_requests)),
            ("FROM public.report", _Result(rows=self.reports)),
            ("FROM public.product", _Result(rows=self.products)),
            ("FROM public.customer_company", _Result(scalar=self.company_name)),
            ("FROM public.customer_contact", _Result(one=self.contact)),
            ("FROM public.activity", _Result(scalar=self.prior_meeting)),
            ("FROM public.sales_deal_item", _Result(scalars=self.item_products)),
            ("FROM public.sales_deal JOIN public.sales_pipeline_stage", _Result(rows=self.deals)),
            ("FROM public.member", _Result(scalar=self.member)),
        ):
            if marker in text:
                return result
        raise AssertionError(f"예상하지 못한 질의입니다: {text[:120]}")


def _member(team_id):
    return Member(
        id=uuid4(),
        team_id=team_id,
        display_name="담당",
        role_code="member",
        active=True,
    )


def _activity(team_id, owner_id, **overrides):
    values = {
        "id": uuid4(),
        "team_id": team_id,
        "owner_member_id": owner_id,
        "customer_contact_id": uuid4(),
        "customer_company_id": uuid4(),
        "sales_deal_id": None,
        "product_id": None,
        "title": "정기 미팅",
        "starts_at": NOW + timedelta(days=3),
        "ends_at": NOW + timedelta(days=3, hours=1),
        "location": "본사",
        "note": "견적 검토",
        "deleted_at": None,
        "completed_at": None,
    }
    values.update(overrides)
    return Activity(**values)


def _deal(deal_id, **overrides):
    values = {
        "id": deal_id,
        "title": "장비 도입",
        "phase_code": "quote",
        "outcome_code": "in_progress",
        "deal_amount": 1_000_000,
        "contract_amount": None,
        "contract_ends_on": None,
        "contract_payment_terms": None,
        "quote_valid_until": date(2026, 9, 30),
        "expected_delivery_at": None,
    }
    values.update(overrides)
    return tuple(values.values())


async def _revision(activity, member, **session):
    return await briefing_refresh.source_revision(
        _Session(**session), activity=activity, member=member
    )


# ---------------------------------------------------------------- source revision


@pytest.mark.anyio
async def test_revision_is_stable_for_the_same_material_state():
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    deal_id = uuid4()
    state = {
        "deals": [_deal(deal_id)],
        "files": [(uuid4(), "contract", uuid4(), 1, NOW)],
        "reports": [(uuid4(), 1, uuid4(), NOW, {})],
    }

    assert await _revision(activity, member, **state) == await _revision(activity, member, **state)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    ["new_file", "removed_file", "reprocessed", "new_version", "recategorized"],
)
async def test_revision_changes_when_the_searchable_state_changes(change):
    """지문이 바뀌어야 하는 자료 변화들. 하나라도 놓치면 "재생성 필요"가 뜨지 않는다."""
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    document_id, file_id = uuid4(), uuid4()
    before = [(document_id, "quote", file_id, 1, NOW)]
    after = {
        # 새 자료가 범위에 들어왔다.
        "new_file": [*before, (uuid4(), "contract", uuid4(), 1, NOW)],
        # 자료를 지웠다 — 조회 조건에서 빠지므로 목록에서 사라진다.
        "removed_file": [],
        # 재처리로 processed_at 만 바뀌었다.
        "reprocessed": [(document_id, "quote", file_id, 1, NOW + timedelta(hours=1))],
        # 같은 문서를 다시 올려 새 파일이 최신이 됐다.
        "new_version": [(document_id, "quote", uuid4(), 2, NOW)],
        # 견적서를 계약서로 분류를 바꿨다 — "현재 영업 상태" 근거가 달라진다.
        "recategorized": [(document_id, "contract", file_id, 1, NOW)],
    }[change]

    assert await _revision(activity, member, files=before) != await _revision(
        activity, member, files=after
    )


@pytest.mark.anyio
async def test_revision_changes_when_a_recent_report_is_finalized():
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)

    original = await _revision(activity, member, reports=[])
    updated = await _revision(activity, member, reports=[(uuid4(), 2, uuid4(), NOW, {})])

    assert original != updated


@pytest.mark.anyio
async def test_revision_reads_only_the_current_report_submission():
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    session = _Session()

    await briefing_refresh.source_revision(session, activity=activity, member=member)

    report_query = next(text for text in session.statements if "FROM public.report" in text)
    assert "report_submission.id = public.report.current_submission_id" in report_query


@pytest.mark.anyio
async def test_revision_changes_when_a_deal_is_registered():
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)

    original = await _revision(activity, member, deals=[])
    updated = await _revision(activity, member, deals=[_deal(uuid4())])

    assert original != updated


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    [
        {"title": "장비 추가 도입"},
        {"phase_code": "contract"},
        {"outcome_code": "won"},
        {"deal_amount": 2_000_000},
        {"contract_amount": 1_500_000},
        {"contract_ends_on": date(2027, 9, 30)},
        {"contract_payment_terms": "선금 30%"},
        {"quote_valid_until": date(2026, 10, 15)},
        {"expected_delivery_at": NOW + timedelta(days=30)},
    ],
)
async def test_revision_changes_when_a_deal_field_changes(change):
    """브리핑 입력의 딜 요약(sales_deals)에 들어가는 값은 모두 지문에 들어간다."""
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    deal_id = uuid4()

    original = await _revision(activity, member, deals=[_deal(deal_id)])
    updated = await _revision(activity, member, deals=[_deal(deal_id, **change)])

    assert original != updated


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    [
        {"title": "계약 협의"},
        {"location": "고객사 회의실"},
        {"note": "계약 조건 확정"},
        {"starts_at": NOW + timedelta(days=4)},
        {"ends_at": NOW + timedelta(days=3, hours=2)},
        {"customer_contact_id": uuid4()},
        {"customer_company_id": uuid4()},
    ],
)
async def test_revision_changes_when_the_meeting_changes(change):
    """일정 등록 때 넣은 제목·장소·메모·시각도 브리핑 입력이다."""
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    changed = _activity(
        team_id,
        member.id,
        **{
            key: getattr(activity, key)
            for key in (
                "id",
                "customer_contact_id",
                "customer_company_id",
                "title",
                "starts_at",
                "ends_at",
                "location",
                "note",
            )
        }
        | change,
    )

    assert await _revision(activity, member) != await _revision(changed, member)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "session",
    [
        {"company_name": "새 회사명"},
        {"contact": ("김담당", "구매팀", "부장")},
        {"contact": ("김담당", "재무팀", "과장")},
        {"contact": ("이담당", "구매팀", "과장")},
        # 앞선 일정이 생기면 첫 미팅 브리핑이 관계 브리핑으로 바뀐다.
        {"prior_meeting": uuid4()},
    ],
)
async def test_revision_changes_when_the_customer_context_changes(session):
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)

    assert await _revision(activity, member) != await _revision(activity, member, **session)


def _support(request_id, **overrides):
    values = {
        "id": request_id,
        "title": "화면 깜빡임",
        "is_urgent": False,
        "status_code": "received",
        "occurred_at": NOW,
        "updated_at": None,
        "response_count": 0,
        "last_responded_at": None,
    }
    values.update(overrides)
    return tuple(values.values())


@pytest.mark.anyio
async def test_revision_changes_when_a_support_request_is_registered():
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)

    original = await _revision(activity, member, support_requests=[])
    updated = await _revision(activity, member, support_requests=[_support(uuid4())])

    assert original != updated


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    [
        {"status_code": "in_progress"},
        {"status_code": "completed"},
        {"is_urgent": True},
        {"title": "화면 꺼짐"},
        {"updated_at": NOW + timedelta(hours=1)},
        {"response_count": 1, "last_responded_at": NOW + timedelta(hours=2)},
    ],
)
async def test_revision_changes_when_a_support_request_changes(change):
    """C/S 상태·긴급 여부·본문 수정·대응 기록이 바뀌면 브리핑이 달라질 수 있다."""
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    request_id = uuid4()

    original = await _revision(activity, member, support_requests=[_support(request_id)])
    updated = await _revision(activity, member, support_requests=[_support(request_id, **change)])

    assert original != updated


@pytest.mark.anyio
async def test_revision_applies_the_support_request_visibility_rule():
    """브리핑 입력과 같이 팀원 담당자는 자기가 맡은 C/S만 지문에 넣는다."""
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    session = _Session()

    await briefing_refresh.source_revision(session, activity=activity, member=member)

    support_query = next(
        text for text in session.statements if "FROM public.support_request" in text
    )
    assert "support_request.assignee_member_id" in support_query
    assert "support_request.deleted_at IS NULL" in support_query


@pytest.mark.anyio
async def test_revision_applies_the_document_visibility_rule():
    """담당자가 볼 수 없는 자료 때문에 "재생성 필요"가 뜨지 않도록, 지문 계산에도
    자료실 공개 범위를 그대로 건다."""
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    session = _Session(deals=[_deal(uuid4())])

    await briefing_refresh.source_revision(session, activity=activity, member=member)

    document_query = next(text for text in session.statements if "FROM public.document" in text)
    assert "created_by_member_id" in document_query
    assert "document.deleted_at IS NULL" in document_query
    assert "processing_status" in document_query


# ---------------------------------------------------------------- 게시 규칙


def _run(*, status, observed_at, finished_at, error=None, snapshot=None, revision=None):
    source_refs = {"activity_id": "a", "source_observed_at": observed_at}
    if revision is not None:
        source_refs["source_revision"] = revision
    return AgentRun(
        id=uuid4(),
        status_code=status,
        output_snapshot=snapshot,
        error_message=error,
        finished_at=finished_at,
        input_snapshot={},
        source_refs=source_refs,
        created_at=finished_at or NOW,
    )


class _RunsSession:
    def __init__(self, runs, activity=None):
        self.runs = runs
        self.activity = activity
        self.statements = []

    async def execute(self, statement):
        text = str(statement)
        self.statements.append(text)
        if "FROM public.activity" in text:
            return _Result(scalar=self.activity)
        return _Result(scalars=self.runs)


async def _briefing(runs, member, monkeypatch, *, activity=None, current_revision="same"):
    from app.api import activities as activities_api
    from app.services import briefing_documents

    async def _documents(_db, **_kwargs):
        return {"related": [], "product": [], "search": {}}

    revisions = []

    async def _source_revision(_db, *, activity, member):
        revisions.append((activity, member))
        return current_revision

    async def _owner(_db, _activity):
        return member

    monkeypatch.setattr(briefing_documents, "visible_documents", _documents)
    monkeypatch.setattr(briefing_refresh, "source_revision", _source_revision)
    monkeypatch.setattr(briefing_refresh, "owner", _owner)
    briefing = await activities_api._activity_briefing(
        _RunsSession(runs, activity), member, uuid4()
    )
    return briefing, revisions


@pytest.mark.anyio
async def test_a_late_finishing_old_run_does_not_overwrite_a_fresher_briefing(monkeypatch):
    """옛 자료로 시작한 실행이 늦게 끝나도 더 새 자료로 만든 브리핑을 밀어내지 않는다.

    정렬 기준이 "언제 끝났나" 가 아니라 "어느 시점 자료를 봤나" 인 이유다.
    """
    member = _member(uuid4())
    fresh = _run(
        status="completed",
        observed_at="2026-09-12T10:00:00+00:00",
        finished_at=NOW + timedelta(minutes=5),
        snapshot={"contract_summary": "새 자료 반영"},
    )
    stale = _run(
        status="completed",
        observed_at="2026-09-12T09:00:00+00:00",
        # 더 나중에 끝났지만 본 자료는 더 옛것이다.
        finished_at=NOW + timedelta(minutes=30),
        snapshot={"contract_summary": "옛 자료"},
    )

    briefing, _ = await _briefing([stale, fresh], member, monkeypatch)

    assert briefing["content"] == {"contract_summary": "새 자료 반영"}


@pytest.mark.anyio
async def test_a_failed_refresh_keeps_the_last_successful_briefing(monkeypatch):
    member = _member(uuid4())
    succeeded = _run(
        status="completed",
        observed_at="2026-09-12T09:00:00+00:00",
        finished_at=NOW,
        snapshot={"contract_summary": "지난 성공"},
    )
    failed = _run(
        status="failed",
        observed_at="2026-09-12T10:00:00+00:00",
        finished_at=NOW + timedelta(minutes=10),
        error="llm_timeout",
    )
    failed.created_at = NOW + timedelta(minutes=10)

    briefing, _ = await _briefing([failed, succeeded], member, monkeypatch)

    assert briefing["status"] == "completed"
    assert briefing["content"] == {"contract_summary": "지난 성공"}
    # 실패는 본문을 지우지 않고 따로만 알린다.
    assert briefing["refresh_error"] == "llm_timeout"
    assert briefing["refreshing"] is False


@pytest.mark.anyio
async def test_a_running_refresh_still_shows_the_stored_briefing(monkeypatch):
    """재생성 중이어도 본문을 로딩으로 덮지 않는다 — 화면은 있는 결과를 바로 보여준다."""
    member = _member(uuid4())
    stored = _run(
        status="completed",
        observed_at="2026-09-12T09:00:00+00:00",
        finished_at=NOW,
        snapshot={"contract_summary": "저장된 브리핑"},
    )
    running = _run(status="running", observed_at=None, finished_at=None)
    running.created_at = NOW + timedelta(minutes=1)

    briefing, _ = await _briefing([running, stored], member, monkeypatch)

    assert briefing["content"] == {"contract_summary": "저장된 브리핑"}
    assert briefing["refreshing"] is True
    # 진행 중은 실패가 아니다.
    assert briefing["refresh_error"] is None


@pytest.mark.anyio
async def test_the_first_briefing_reports_itself_as_pending(monkeypatch):
    """아직 완성된 적이 없을 때만 화면이 '준비 중' 을 보여줄 수 있어야 한다."""
    member = _member(uuid4())
    queued = _run(status="queued", observed_at=None, finished_at=None)

    briefing, _ = await _briefing([queued], member, monkeypatch)

    assert briefing["status"] == "queued"
    assert briefing["content"] is None
    assert briefing["refreshing"] is True
    assert briefing["outdated"] is False


@pytest.mark.anyio
async def test_no_run_means_no_briefing_payload_at_all(monkeypatch):
    briefing, _ = await _briefing([], _member(uuid4()), monkeypatch)

    assert briefing is None


# ---------------------------------------------------------------- 재생성 필요 표시


@pytest.mark.anyio
@pytest.mark.parametrize(("current", "expected"), [("rev-1", False), ("rev-2", True)])
async def test_outdated_compares_the_published_briefing_with_the_current_state(
    monkeypatch, current, expected
):
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    published = _run(
        status="completed",
        observed_at="2026-09-12T09:00:00+00:00",
        finished_at=NOW,
        snapshot={"highlights": []},
        revision="rev-1",
    )

    briefing, revisions = await _briefing(
        [published], member, monkeypatch, activity=activity, current_revision=current
    )

    assert briefing["outdated"] is expected
    # 화면을 연 사람이 아니라 미팅 담당자 기준으로 계산한다.
    assert revisions == [(activity, member)]


@pytest.mark.anyio
async def test_outdated_is_not_computed_while_a_regeneration_is_running(monkeypatch):
    """재생성 완료를 기다리는 반복 조회마다 지문 질의를 되풀이하지 않는다."""
    team_id = uuid4()
    member = _member(team_id)
    stored = _run(
        status="completed",
        observed_at="2026-09-12T09:00:00+00:00",
        finished_at=NOW,
        snapshot={"highlights": []},
        revision="rev-1",
    )
    running = _run(status="running", observed_at=None, finished_at=None)
    running.created_at = NOW + timedelta(minutes=1)

    briefing, revisions = await _briefing(
        [running, stored],
        member,
        monkeypatch,
        activity=_activity(team_id, member.id),
        current_revision="rev-2",
    )

    assert briefing["outdated"] is False
    assert revisions == []


@pytest.mark.anyio
async def test_a_failed_regeneration_still_reports_the_published_briefing_as_outdated(
    monkeypatch,
):
    team_id = uuid4()
    member = _member(team_id)
    published = _run(
        status="completed",
        observed_at="2026-09-12T09:00:00+00:00",
        finished_at=NOW,
        snapshot={"highlights": []},
        revision="rev-1",
    )
    failed = _run(
        status="failed",
        observed_at="2026-09-12T10:00:00+00:00",
        finished_at=NOW + timedelta(minutes=10),
        error="llm_timeout",
    )
    failed.created_at = NOW + timedelta(minutes=10)

    briefing, _ = await _briefing(
        [failed, published],
        member,
        monkeypatch,
        activity=_activity(team_id, member.id),
        current_revision="rev-2",
    )

    assert briefing["content"] == {"highlights": []}
    assert briefing["outdated"] is True


# ---------------------------------------------------------------- C/S 링크


class _SupportSession:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    async def execute(self, statement):
        self.statements.append(str(statement))
        return _Result(rows=self.rows)


@pytest.mark.anyio
async def test_visible_support_requests_keep_briefing_order_and_current_values():
    from app.services import briefing_documents

    member = _member(uuid4())
    first, second, gone = uuid4(), uuid4(), uuid4()
    snapshot = {
        "support_requests": [
            {"id": str(first), "title": "실행 당시 제목"},
            {"id": str(gone), "title": "지워졌거나 권한 밖"},
            {"id": str(second), "title": "둘째"},
        ]
    }
    session = _SupportSession(
        [
            (second, "둘째", "completed", False),
            (first, "지금 제목", "in_progress", True),
        ]
    )

    result = await briefing_documents.visible_support_requests(
        session, member=member, snapshot=snapshot
    )

    assert result == [
        {"id": str(first), "title": "지금 제목", "status_code": "in_progress", "is_urgent": True},
        {"id": str(second), "title": "둘째", "status_code": "completed", "is_urgent": False},
    ]
    # 팀원은 C/S 화면과 같이 자기가 맡은 건만, 지운 건은 빼고 본다.
    assert "support_request.assignee_member_id" in session.statements[0]
    assert "support_request.deleted_at IS NULL" in session.statements[0]


@pytest.mark.anyio
async def test_visible_support_requests_without_support_input_skip_the_query():
    from app.services import briefing_documents

    session = _SupportSession([])

    result = await briefing_documents.visible_support_requests(
        session, member=_member(uuid4()), snapshot={}
    )

    assert result == []
    assert session.statements == []
