"""자료·일정 변경이 AI 브리핑 갱신으로 이어지는 경로.

여기서 지키려는 것은 넷이다.

* 영향받는 **미래** 미팅만 예약한다. 무관한 딜과 지난 미팅은 건드리지 않는다.
* 같은 자료 상태(source revision)에 대해서는 한 번만 만든다.
* 자료 처리가 실패하면 아무것도 예약하지 않는다.
* 늦게 끝난 옛 실행이 더 새 자료로 만든 브리핑을 덮지 않고, 실패한 갱신이 마지막 성공
  브리핑을 지우지 않는다.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.config import settings
from app.models.agent import AgentRun
from app.models.crm import Activity
from app.models.workspace import Member
from app.services import briefing_refresh

NOW = datetime(2026, 9, 12, 9, tzinfo=UTC)
# 일정 API 는 서울 오프셋으로만 시각을 받는다.
_SEOUL = ZoneInfo("Asia/Seoul")


class _Result:
    def __init__(self, *, scalar=None, scalars=(), rows=()):
        self._scalar = scalar
        self._scalars = list(scalars)
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._scalars))

    def all(self):
        return list(self._rows)


class _Session:
    """문장 본문을 보고 답을 고르는 가짜 세션. 질의 순서에 묶이지 않게 한다."""

    def __init__(
        self,
        *,
        member=None,
        deal_product=None,
        item_products=(),
        files=(),
        activities=(),
        existing_run=None,
    ):
        self.member = member
        self.deal_product = deal_product
        self.item_products = item_products
        self.files = files
        self.activities = activities
        self.existing_run = existing_run
        self.statements = []
        self.added = []
        self.commits = 0

    async def execute(self, statement):
        text = str(statement)
        self.statements.append(text)
        # 바깥 FROM 절부터 본다. 자료 조회에는 공개 범위(member)와 고객사 범위(sales_deal)
        # 하위 질의가 들어 있어서, 덜 구체적인 조건을 먼저 보면 엉뚱한 답을 돌려준다.
        for marker, result in (
            ("FROM public.document", _Result(rows=self.files)),
            ("FROM public.activity", _Result(scalars=self.activities)),
            ("FROM public.agent_run", _Result(scalar=self.existing_run)),
            ("FROM public.sales_deal_item", _Result(scalars=self.item_products)),
            ("FROM public.sales_deal", _Result(scalar=self.deal_product)),
            ("FROM public.member", _Result(scalar=self.member)),
        ):
            if marker in text:
                return result
        raise AssertionError(f"예상하지 못한 질의입니다: {text[:120]}")

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _member(team_id):
    return Member(
        id=uuid4(),
        team_id=team_id,
        display_name="담당",
        role_code="member",
        active=True,
    )


def _activity(team_id, owner_id, *, starts_at=NOW + timedelta(days=3), **overrides):
    values = {
        "id": uuid4(),
        "team_id": team_id,
        "owner_member_id": owner_id,
        "customer_contact_id": uuid4(),
        "customer_company_id": uuid4(),
        "sales_deal_id": uuid4(),
        "product_id": None,
        "starts_at": starts_at,
        "deleted_at": None,
        "completed_at": None,
    }
    values.update(overrides)
    return Activity(**values)


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setattr(type(settings), "llm_configured", property(lambda _self: True))
    monkeypatch.setattr(settings, "llm_model", "test-model", raising=False)


# ---------------------------------------------------------------- source revision


@pytest.mark.anyio
async def test_revision_is_stable_for_the_same_material_state():
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    files = [(uuid4(), uuid4(), 1, NOW)]

    first = await briefing_refresh.source_revision(
        _Session(files=files), activity=activity, member=member
    )
    second = await briefing_refresh.source_revision(
        _Session(files=files), activity=activity, member=member
    )

    assert first == second
    # 같은 상태면 멱등키도 같다 — 같은 revision 은 한 번만 만들어진다.
    assert briefing_refresh.idempotency_key(activity.id, first) == briefing_refresh.idempotency_key(
        activity.id, second
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    ["new_file", "removed_file", "reprocessed", "new_version", "relinked"],
)
async def test_revision_changes_when_the_searchable_state_changes(change):
    """지문이 바뀌어야 하는 변화들. 하나라도 놓치면 브리핑이 낡은 채로 남는다."""
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    document_id, file_id = uuid4(), uuid4()
    before = [(document_id, file_id, 1, NOW)]
    after = {
        # 새 자료가 범위에 들어왔다.
        "new_file": [*before, (uuid4(), uuid4(), 1, NOW)],
        # 자료를 지웠다 — 조회 조건에서 빠지므로 목록에서 사라진다.
        "removed_file": [],
        # 재처리로 processed_at 만 바뀌었다.
        "reprocessed": [(document_id, file_id, 1, NOW + timedelta(hours=1))],
        # 같은 문서를 다시 올려 새 파일이 최신이 됐다.
        "new_version": [(document_id, uuid4(), 2, NOW)],
        "relinked": before,
    }[change]
    changed_activity = (
        _activity(team_id, member.id, sales_deal_id=uuid4(), id=activity.id)
        if change == "relinked"
        else activity
    )

    original = await briefing_refresh.source_revision(
        _Session(files=before), activity=activity, member=member
    )
    updated = await briefing_refresh.source_revision(
        _Session(files=after), activity=changed_activity, member=member
    )

    assert original != updated


@pytest.mark.anyio
async def test_revision_applies_the_document_visibility_rule():
    """팀원이 볼 수 없는 자료 때문에 브리핑이 다시 만들어지지 않도록, 지문 계산에도
    자료실 공개 범위를 그대로 건다."""
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    session = _Session(files=[])

    await briefing_refresh.source_revision(session, activity=activity, member=member)

    document_query = next(text for text in session.statements if "FROM public.document" in text)
    assert "created_by_member_id" in document_query
    assert "document.deleted_at IS NULL" in document_query
    assert "processing_status" in document_query


# ---------------------------------------------------------------- 대상 미팅 선택


def test_document_scope_only_covers_the_links_the_document_has():
    deal_only = briefing_refresh.document_activity_scopes(
        sales_deal_id=uuid4(), customer_company_id=None, product_id=None
    )
    unlinked = briefing_refresh.document_activity_scopes(
        sales_deal_id=None, customer_company_id=None, product_id=None
    )

    # 딜에만 붙은 자료는 그 딜만 본다 — 같은 고객사의 다른 딜 미팅은 건드리지 않는다.
    assert len(deal_only) == 1
    assert "activity.sales_deal_id =" in str(deal_only[0])
    assert "customer_company_id" not in str(deal_only[0])
    # 아무 데도 안 걸린 자료는 갱신 대상이 없다.
    assert unlinked == []


def test_product_scope_reaches_the_deal_product_and_the_quote_items():
    scope = str(briefing_refresh._product_scope(uuid4()))

    assert "activity.product_id =" in scope
    assert "FROM public.sales_deal" in scope
    assert "FROM public.sales_deal_item" in scope


@pytest.mark.anyio
async def test_only_future_uncompleted_meetings_are_selected():
    team_id = uuid4()
    session = _Session(activities=[])

    await briefing_refresh._future_meetings(
        session,
        team_id=team_id,
        scopes=[Activity.sales_deal_id == uuid4()],
        now=NOW,
    )

    query = session.statements[0]
    # 지난 미팅은 다시 만들지 않는다.
    assert "activity.starts_at >=" in query
    assert "activity.deleted_at IS NULL" in query
    assert "activity.completed_at IS NULL" in query
    assert "activity.team_id =" in query


# ---------------------------------------------------------------- 예약과 중복 방지


@pytest.mark.anyio
async def test_scheduling_queues_one_run_the_worker_can_claim(llm):
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    session = _Session(member=member, files=[])

    queued = await briefing_refresh.schedule_activities(session, [activity])

    assert len(queued) == 1
    run: AgentRun = session.added[0]
    assert run.agent_code == "contract_management_briefing"
    assert run.status_code == "queued"
    assert run.trigger_code == "system"
    # 범용 worker 가 집어가는 조건이다. 새 큐도 새 테이블도 만들지 않는다.
    assert run.request_hash is not None
    assert run.requested_by_member_id == member.id
    assert run.source_refs["activity_id"] == str(activity.id)
    assert run.source_refs["source_revision"]
    assert session.commits == 1


@pytest.mark.anyio
async def test_one_conflicting_meeting_does_not_lose_the_others(llm):
    """UNIQUE 충돌은 그 미팅에서만 끝나야 한다. 한 건 때문에 나머지 예약까지 날리면,
    같은 자료를 다시 올리기 전까지 그 미팅들은 낡은 브리핑을 그대로 들고 있게 된다."""
    team_id = uuid4()
    member = _member(team_id)
    first, second = _activity(team_id, member.id), _activity(team_id, member.id)
    taken = {first.id}

    class _Conflicting(_Session):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.pending = None

        async def execute(self, statement):
            if "FROM public.agent_run" in str(statement):
                return _Result(scalar=None)
            return await super().execute(statement)

        def add(self, value):
            self.pending = value
            super().add(value)

        async def commit(self):
            from sqlalchemy.exc import IntegrityError

            if UUID(self.pending.source_refs["activity_id"]) in taken:
                raise IntegrityError("insert", {}, Exception("duplicate key"))
            await super().commit()

    session = _Conflicting(member=member, files=[])

    queued = await briefing_refresh.schedule_activities(session, [first, second])

    assert len(queued) == 1
    assert session.commits == 1


@pytest.mark.anyio
async def test_the_same_revision_is_never_queued_twice(llm):
    """자료 여러 개가 연달아 처리돼도 검색 대상이 그대로면 브리핑은 한 번만 만든다."""
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    session = _Session(member=member, files=[], existing_run=uuid4())

    queued = await briefing_refresh.schedule_activities(session, [activity])

    assert queued == []
    assert session.added == []
    assert session.commits == 0


@pytest.mark.anyio
async def test_a_new_revision_is_queued_even_while_another_run_is_in_flight(llm):
    """queued/running 이 있다고 새 요청을 버리면, 실행이 시작된 뒤 올라온 자료가 누락된다.

    멱등키가 revision 을 포함하므로 "이미 도는 중" 이 아니라 "같은 상태" 일 때만 막힌다.
    """
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)

    old = await briefing_refresh.source_revision(
        _Session(files=[]), activity=activity, member=member
    )
    new = await briefing_refresh.source_revision(
        _Session(files=[(uuid4(), uuid4(), 1, NOW)]), activity=activity, member=member
    )

    assert briefing_refresh.idempotency_key(activity.id, old) != briefing_refresh.idempotency_key(
        activity.id, new
    )


@pytest.mark.anyio
async def test_meetings_owned_by_an_inactive_member_are_skipped(llm):
    """퇴사 처리된 담당자의 미팅은 큐에 넣어도 worker 가 반드시 실패시킨다."""
    team_id = uuid4()
    session = _Session(member=None, files=[])

    queued = await briefing_refresh.schedule_activities(session, [_activity(team_id, uuid4())])

    assert queued == []
    assert session.added == []


@pytest.mark.anyio
async def test_nothing_is_queued_without_an_llm(monkeypatch):
    monkeypatch.setattr(type(settings), "llm_configured", property(lambda _self: False))
    team_id = uuid4()
    member = _member(team_id)
    session = _Session(member=member, files=[])

    activities = [_activity(team_id, member.id)]

    assert await briefing_refresh.schedule_activities(session, activities) == []
    assert session.added == []


# ---------------------------------------------------------------- 후속 갱신


@pytest.mark.anyio
async def test_a_completed_run_schedules_a_follow_up_when_material_moved_on(monkeypatch, llm):
    """실행 중에 새 자료가 들어왔다면, 그 결과는 이미 낡았으므로 후속을 남긴다."""
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    run = SimpleNamespace(
        id=uuid4(),
        agent_code="contract_management_briefing",
        source_refs={"activity_id": str(activity.id), "source_revision": "실행-시작-시점"},
    )
    scheduled = []

    class _FollowUpSession(_Session):
        async def execute(self, statement):
            text = str(statement)
            if "FROM public.agent_run" in text:
                self.statements.append(text)
                return _Result(scalar=run)
            if "FROM public.activity" in text:
                self.statements.append(text)
                return _Result(scalar=activity)
            return await super().execute(statement)

    session = _FollowUpSession(member=member, files=[])
    monkeypatch.setattr(briefing_refresh, "get_sessionmaker", lambda: lambda: _Context(session))
    monkeypatch.setattr(
        briefing_refresh,
        "schedule_activities",
        _record(scheduled),
    )

    await briefing_refresh.follow_up_if_stale(run.id)

    assert scheduled == [[activity.id]]


@pytest.mark.anyio
async def test_no_follow_up_when_the_material_is_unchanged(monkeypatch, llm):
    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    current = await briefing_refresh.source_revision(
        _Session(files=[]), activity=activity, member=member
    )
    run = SimpleNamespace(
        id=uuid4(),
        agent_code="contract_management_briefing",
        source_refs={"activity_id": str(activity.id), "source_revision": current},
    )
    scheduled = []

    class _FollowUpSession(_Session):
        async def execute(self, statement):
            text = str(statement)
            if "FROM public.agent_run" in text:
                return _Result(scalar=run)
            if "FROM public.activity" in text:
                return _Result(scalar=activity)
            return await super().execute(statement)

    session = _FollowUpSession(member=member, files=[])
    monkeypatch.setattr(briefing_refresh, "get_sessionmaker", lambda: lambda: _Context(session))
    monkeypatch.setattr(briefing_refresh, "schedule_activities", _record(scheduled))

    assert await briefing_refresh.follow_up_if_stale(run.id) == []
    assert scheduled == []


class _Context:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


def _record(sink):
    async def schedule(_db, activities):
        sink.append([activity.id for activity in activities])
        return [uuid4() for _ in activities]

    return schedule


# ---------------------------------------------------------------- 예약 실패 격리


@pytest.mark.anyio
async def test_a_failed_schedule_never_breaks_the_work_that_was_already_saved():
    async def boom():
        raise RuntimeError("db down")

    # 예외가 밖으로 새면 자료 원문·요약 저장이 실패로 뒤집힌다.
    await briefing_refresh.schedule_quietly(boom())


# ---------------------------------------------------------------- 게시 규칙


def _run(*, status, observed_at, finished_at, error=None, snapshot=None):
    return AgentRun(
        id=uuid4(),
        status_code=status,
        output_snapshot=snapshot,
        error_message=error,
        finished_at=finished_at,
        input_snapshot={},
        source_refs={"activity_id": "a", "source_observed_at": observed_at},
        created_at=finished_at or NOW,
    )


class _RunsSession:
    def __init__(self, runs):
        self.runs = runs

    async def execute(self, _statement):
        return _Result(scalars=self.runs)


async def _briefing(runs, member):
    # 브리핑 응답에 자료 목록을 싣는 변경(briefing_documents)은 이번 범위가 아니다.
    # 관련자료는 계속 `GET /activities/{id}/documents` 로 따로 조회한다.
    from app.api import activities as activities_api

    return await activities_api._activity_briefing(_RunsSession(runs), member, uuid4())


@pytest.mark.anyio
async def test_a_late_finishing_old_run_does_not_overwrite_a_fresher_briefing():
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

    briefing = await _briefing([stale, fresh], member)

    assert briefing["content"] == {"contract_summary": "새 자료 반영"}


@pytest.mark.anyio
async def test_a_failed_refresh_keeps_the_last_successful_briefing():
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

    briefing = await _briefing([failed, succeeded], member)

    assert briefing["status"] == "completed"
    assert briefing["content"] == {"contract_summary": "지난 성공"}
    # 실패는 본문을 지우지 않고 따로만 알린다.
    assert briefing["refresh_error"] == "llm_timeout"
    assert briefing["refreshing"] is False


@pytest.mark.anyio
async def test_a_running_refresh_still_shows_the_stored_briefing():
    """갱신 중이어도 본문을 로딩으로 덮지 않는다 — 화면은 있는 결과를 바로 보여준다."""
    member = _member(uuid4())
    stored = _run(
        status="completed",
        observed_at="2026-09-12T09:00:00+00:00",
        finished_at=NOW,
        snapshot={"contract_summary": "저장된 브리핑"},
    )
    running = _run(status="running", observed_at=None, finished_at=None)
    running.created_at = NOW + timedelta(minutes=1)

    briefing = await _briefing([running, stored], member)

    assert briefing["content"] == {"contract_summary": "저장된 브리핑"}
    assert briefing["refreshing"] is True
    # 진행 중은 실패가 아니다.
    assert briefing["refresh_error"] is None


@pytest.mark.anyio
async def test_the_first_briefing_reports_itself_as_pending():
    """아직 완성된 적이 없을 때만 화면이 '준비 중' 을 보여줄 수 있어야 한다."""
    member = _member(uuid4())
    queued = _run(status="queued", observed_at=None, finished_at=None)

    briefing = await _briefing([queued], member)

    assert briefing["status"] == "queued"
    assert briefing["content"] is None
    assert briefing["refreshing"] is True


@pytest.mark.anyio
async def test_no_run_means_no_briefing_payload_at_all():
    assert await _briefing([], _member(uuid4())) is None


# ---------------------------------------------------------------- 자료 변경 트리거


class _DocumentSession:
    def __init__(self, document):
        self.document = document
        self.commits = 0

    async def execute(self, _statement):
        return _Result(scalar=self.document)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _document(team_id, member_id, **overrides):
    from app.models.content import Document

    values = {
        "id": uuid4(),
        "team_id": team_id,
        "created_by_member_id": member_id,
        "document_no": "SL-DC-2026-0001",
        "category_code": "contract",
        "title": "계약서",
        "description": None,
        "customer_company_id": None,
        "customer_contact_id": None,
        "sales_deal_id": None,
        "purchase_order_id": None,
        "product_id": None,
        "tags": [],
        "created_at": NOW,
        "deleted_at": None,
    }
    values.update(overrides)
    return Document(**values)


class _CapturingBackground:
    """예약된 갱신 범위를 그대로 받아 두는 BackgroundTasks 대역."""

    def __init__(self, monkeypatch):
        self.calls = []

        async def _schedule(**kwargs):
            self.calls.append(kwargs)
            return []

        monkeypatch.setattr(briefing_refresh, "schedule_for_document_scope", _schedule)

    def add_task(self, function, *args, **kwargs):
        self.tasks = getattr(self, "tasks", [])
        self.tasks.append((function, args, kwargs))

    async def drain(self):
        for function, args, kwargs in getattr(self, "tasks", []):
            await function(*args, **kwargs)


@pytest.mark.anyio
async def test_deleting_a_document_refreshes_the_meetings_that_used_it(monkeypatch):
    from app.api import documents as documents_api

    team_id = uuid4()
    member = _member(team_id)
    deal_id = uuid4()
    document = _document(team_id, member.id, sales_deal_id=deal_id)
    background = _CapturingBackground(monkeypatch)

    await documents_api.delete_document(document.id, background, member, _DocumentSession(document))
    await background.drain()

    assert background.calls == [
        {
            "team_id": team_id,
            "sales_deal_id": deal_id,
            "customer_company_id": None,
            "product_id": None,
        }
    ]


@pytest.mark.anyio
async def test_deleting_an_already_deleted_document_schedules_nothing(monkeypatch):
    from app.api import documents as documents_api

    team_id = uuid4()
    member = _member(team_id)
    document = _document(team_id, member.id, sales_deal_id=uuid4(), deleted_at=NOW)
    background = _CapturingBackground(monkeypatch)

    await documents_api.delete_document(document.id, background, member, _DocumentSession(document))
    await background.drain()

    assert background.calls == []


@pytest.mark.anyio
async def test_relinking_a_document_refreshes_both_the_old_and_the_new_scope(monkeypatch):
    """연결을 옮기면 자료를 잃는 미팅과 새로 얻는 미팅이 동시에 생긴다. 양쪽 다 갱신한다."""
    from app.api import documents as documents_api
    from app.schemas.documents import DocumentPatch

    team_id = uuid4()
    member = _member(team_id)
    old_deal, new_deal = uuid4(), uuid4()
    document = _document(team_id, member.id, sales_deal_id=old_deal)
    session = _DocumentSession(document)
    background = _CapturingBackground(monkeypatch)

    async def _detail(*_args, **_kwargs):
        return None

    async def _validate(*_args, **_kwargs):
        return None

    monkeypatch.setattr(documents_api, "_detail", _detail)
    monkeypatch.setattr(documents_api, "_validate_links", _validate)

    await documents_api.update_document(
        document.id,
        DocumentPatch(sales_deal_id=new_deal),
        background,
        member,
        session,
    )
    await background.drain()

    scheduled_deals = {call["sales_deal_id"] for call in background.calls}
    assert scheduled_deals == {old_deal, new_deal}


@pytest.mark.anyio
async def test_a_file_that_is_not_completed_or_whose_document_is_gone_schedules_nothing(
    monkeypatch,
):
    """삭제된 자료와 처리 중인 파일은 검색 대상이 아니다. 갱신을 일으켜도 얻을 것이 없다."""
    session = _Session(files=[])

    class _Empty(_Session):
        async def execute(self, statement):
            self.statements.append(str(statement))
            return _Result(scalar=None)

    empty = _Empty()
    monkeypatch.setattr(briefing_refresh, "get_sessionmaker", lambda: lambda: _Context(empty))

    assert await briefing_refresh.schedule_for_file(uuid4()) == []
    query = empty.statements[0]
    assert "file.processing_status" in query
    assert "document.deleted_at IS NULL" in query
    assert session.added == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        # 지난 일정이 미래로 옮겨 오면 그때 비로소 브리핑이 필요해진다.
        ({"starts_at": (NOW + timedelta(days=5)).astimezone(_SEOUL)}, True),
        ({"sales_deal_id": None}, True),
        # 검색 범위와 무관한 수정은 브리핑을 다시 만들지 않는다.
        ({"location": "본사 3층"}, False),
    ],
)
async def test_changing_a_meeting_link_or_time_refreshes_that_meeting(monkeypatch, patch, expected):
    """미팅 생성뿐 아니라 고객사·딜·시간 변경도 브리핑을 다시 만들게 한다."""
    from app.api import activities as activities_api
    from app.schemas.activities import ActivityPatch

    team_id = uuid4()
    member = _member(team_id)
    activity = _activity(team_id, member.id)
    scheduled = []

    async def _locked(*_args, **_kwargs):
        return activity

    async def _row(*_args, **_kwargs):
        return ()

    async def _schedule(activity_id):
        scheduled.append(activity_id)
        return []

    async def _contact(*_args, **_kwargs):
        return None

    async def _company(*_args, **_kwargs):
        return activity.customer_company_id, "고객사"

    async def _deal(*_args, **_kwargs):
        return None

    monkeypatch.setattr(activities_api, "_locked_activity", _locked)
    monkeypatch.setattr(activities_api, "_contact_info", _contact)
    monkeypatch.setattr(activities_api, "_resolve_company_id", _company)
    monkeypatch.setattr(activities_api, "_team_sales_deal", _deal)
    monkeypatch.setattr(activities_api, "_validate_customer_company", lambda *_args: None)
    monkeypatch.setattr(activities_api, "_activity_row", _row)
    monkeypatch.setattr(activities_api, "_activity_read", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(activities_api, "_validate_range", lambda *_args: None)
    monkeypatch.setattr(briefing_refresh, "schedule_for_activity", _schedule)
    background = _CapturingBackground(monkeypatch)

    await activities_api.update_activity(
        activity.id,
        ActivityPatch(**patch),
        background,
        member,
        _DocumentSession(activity),
    )
    await background.drain()

    assert scheduled == ([activity.id] if expected else [])


@pytest.mark.anyio
async def test_scheduling_for_an_activity_ignores_past_and_deleted_meetings(monkeypatch):
    captured = {}

    class _Lookup(_Session):
        async def execute(self, statement):
            captured["query"] = str(statement)
            return _Result(scalar=None)

    monkeypatch.setattr(briefing_refresh, "get_sessionmaker", lambda: lambda: _Context(_Lookup()))

    assert await briefing_refresh.schedule_for_activity(uuid4()) == []
    assert "activity.starts_at >=" in captured["query"]
    assert "activity.deleted_at IS NULL" in captured["query"]
    assert "activity.completed_at IS NULL" in captured["query"]
