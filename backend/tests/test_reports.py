from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.content import Report
from app.models.crm import Activity
from app.models.workspace import Member
from app.schemas.reports import (
    ReportCreate,
    ReportPageParams,
    ReportPatch,
    ReportSubmit,
)

ORIGIN = settings.cors_origin_list[0]
NOW = datetime(2026, 8, 17, 9, tzinfo=UTC)
START = datetime(2026, 8, 17, 1, tzinfo=UTC)
TEMPLATE = {"fields": [{"id": "summary", "label": "요약"}]}
CONTENT = {"summary": "합성 보고 내용"}
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
    def __init__(self, *results: _Result, flush_error: Exception | None = None):
        self.results = list(results)
        self.flush_error = flush_error
        self.statements = []
        self.added = []
        self.deleted = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "예상보다 많은 쿼리가 실행되었습니다."
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    async def delete(self, value):
        self.deleted.append(value)

    async def flush(self):
        self.flush_count += 1
        if self.flush_error is not None:
            raise self.flush_error
        for value in self.added:
            if isinstance(value, Report):
                value.created_at = value.created_at or NOW
                value.updated_at = value.updated_at or NOW

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _member(*, role: str = "member", team_id: UUID | None = None) -> Member:
    return Member(
        id=uuid4(),
        team_id=team_id or uuid4(),
        display_name="합성 영업 담당자",
        role_code=role,
        job_title="영업 담당자",
        active=True,
    )


def _report(member: Member, *, kind: str = "daily", status_code: str = "draft") -> Report:
    return Report(
        id=uuid4(),
        team_id=member.team_id,
        author_member_id=member.id,
        recipient_member_id=None,
        template_snapshot=TEMPLATE,
        source_activity_id=None,
        report_kind=kind,
        report_date=date(2026, 8, 17),
        period_start=None,
        period_end=None,
        status_code=status_code,
        content=CONTENT,
        transcript=None,
        source_snapshot=None,
        ai_evidence=None,
        note=None,
        reviewed_by_member_id=None,
        reviewed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _activity(member: Member) -> Activity:
    return Activity(
        id=uuid4(),
        team_id=member.team_id,
        owner_member_id=member.id,
        customer_contact_id=None,
        end_user_contact_id=None,
        activity_category_id=uuid4(),
        title="합성 미팅",
        starts_at=START,
        ends_at=None,
        all_day=False,
        due_at=None,
        location=None,
        activity_action_tag_id=None,
        completed_at=None,
        note=None,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
        product_id=None,
        sales_deal_id=None,
        purchase_order_id=None,
    )


def _row(report: Report, author: Member, recipient_display_name: str | None = None):
    return (report, author.display_name, recipient_display_name)


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def test_report_request_rejects_unsafe_values():
    """기간·근거 규칙과 중복 일정은 스키마에서 막는다."""
    with pytest.raises(ValidationError):
        # 주간 보고는 기간이 필요하다.
        ReportCreate(
            report_kind="weekly",
            report_date="2026-08-17",
            template_snapshot=TEMPLATE,
            content=CONTENT,
        )

    with pytest.raises(ValidationError):
        # 월간도 기간을 덮으므로 주간과 같은 규칙을 받는다.
        ReportCreate(
            report_kind="monthly",
            report_date="2026-08-31",
            template_snapshot=TEMPLATE,
            content=CONTENT,
        )

    with pytest.raises(ValidationError):
        # 끝이 시작보다 빠를 수 없다.
        ReportCreate(
            report_kind="weekly",
            report_date="2026-08-17",
            period_start="2026-08-17",
            period_end="2026-08-10",
            template_snapshot=TEMPLATE,
            content=CONTENT,
        )

    with pytest.raises(ValidationError):
        # 미팅보고서는 근거 일정이 있어야 한다.
        ReportCreate(
            report_kind="meeting",
            report_date="2026-08-17",
            template_snapshot=TEMPLATE,
            content=CONTENT,
        )

    duplicated = uuid4()
    with pytest.raises(ValidationError):
        ReportCreate(
            report_kind="daily",
            report_date="2026-08-17",
            template_snapshot=TEMPLATE,
            content=CONTENT,
            activity_ids=[duplicated, duplicated],
        )

    # 상태와 작성자는 요청으로 정하지 않는다.
    with pytest.raises(ValidationError):
        ReportCreate(
            report_kind="daily",
            report_date="2026-08-17",
            template_snapshot=TEMPLATE,
            content=CONTENT,
            status_code="submitted",
        )
    with pytest.raises(ValidationError):
        ReportCreate(
            report_kind="daily",
            report_date="2026-08-17",
            template_snapshot=TEMPLATE,
            content=CONTENT,
            author_member_id=str(uuid4()),
        )

    assert ReportPatch(note=None).model_dump(exclude_unset=True) == {"note": None}
    with pytest.raises(ValidationError):
        ReportPageParams(start_date="2026-08-17", end_date="2026-08-10")

    # 업무보고 목록 화면이 실제로 보내는 조합이다. monthly 가 빠지면 여기서 422 가 난다.
    assert ReportPageParams(report_kind=["daily", "weekly", "monthly"]).report_kind == [
        "daily",
        "weekly",
        "monthly",
    ]


class _CreateDb(_Db):
    """생성한 Report 를 그대로 상세 조회 응답으로 돌려준다."""

    def __init__(self, author: Member):
        super().__init__()
        self.author = author

    async def execute(self, statement):
        self.statements.append(statement)
        report = next(value for value in self.added if isinstance(value, Report))
        # 상세 조회는 _report_row, _activities_by_report_ids 순서로 두 번 실행된다.
        if len(self.statements) == 1:
            return _Result(rows=[_row(report, self.author)])
        return _Result(rows=[])


def test_create_starts_as_draft_and_ignores_client_status():
    member = _member()
    db = _CreateDb(member)

    with _client(db, member) as client:
        response = client.post(
            "/api/reports",
            headers={"Origin": ORIGIN},
            json={
                "report_kind": "daily",
                "report_date": "2026-08-17",
                "template_snapshot": TEMPLATE,
                "content": CONTENT,
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status_code"] == "draft"
    assert body["author_member_id"] == str(member.id)
    assert body["team_id"] == str(member.team_id)
    assert body["activities"] == []
    assert response.headers["Location"] == f"/api/reports/{body['id']}"
    assert db.flush_count == db.commit_count == 1


def test_changes_requested_report_is_editable_again():
    """유스케이스 RPT-004: 팀장이 수정 요청하면 팀원이 다시 고쳐 제출한다."""
    member = _member()
    report = _report(member, status_code="changes_requested")

    submit_db = _Db(
        _Result(scalar=report),
        _Result(rows=[_row(report, member)]),
        _Result(rows=[]),
    )
    with _client(submit_db, member) as client:
        submitted = client.post(
            f"/api/reports/{report.id}/submit",
            headers={"Origin": ORIGIN},
            json={"expected_status_code": "changes_requested"},
        )
    assert submitted.status_code == 200
    assert submitted.json()["status_code"] == "submitted"
    assert submit_db.commit_count == 1

    # 검토 결과 상태는 팀원이 제출 시작점으로 쓸 수 없다.
    with pytest.raises(ValidationError):
        ReportSubmit(expected_status_code="approved")
    with pytest.raises(ValidationError):
        ReportSubmit(expected_status_code="rejected")


def test_submitted_report_is_not_editable_or_deletable():
    member = _member()

    submitted = _report(member, status_code="submitted")
    patch_db = _Db(_Result(scalar=submitted))
    with _client(patch_db, member) as client:
        patched = client.patch(
            f"/api/reports/{submitted.id}",
            headers={"Origin": ORIGIN},
            json={"content": {"summary": "고치기"}},
        )
    assert patched.status_code == 409
    assert patched.json() == {"detail": "report_not_editable"}
    assert patch_db.commit_count == 0
    assert patch_db.rollback_count == 1

    delete_db = _Db(_Result(scalar=submitted))
    with _client(delete_db, member) as client:
        removed = client.delete(
            f"/api/reports/{submitted.id}",
            headers={"Origin": ORIGIN},
        )
    assert removed.status_code == 409
    assert removed.json() == {"detail": "report_not_editable"}
    assert delete_db.deleted == []
    assert delete_db.commit_count == 0


def test_submit_moves_draft_and_rejects_stale_expectation():
    member = _member()
    report = _report(member)

    submit_db = _Db(
        _Result(scalar=report),
        _Result(rows=[_row(report, member)]),
        _Result(rows=[]),
    )
    with _client(submit_db, member) as client:
        submitted = client.post(
            f"/api/reports/{report.id}/submit",
            headers={"Origin": ORIGIN},
            json={"expected_status_code": "draft"},
        )
    assert submitted.status_code == 200
    assert submitted.json()["status_code"] == "submitted"
    assert report.status_code == "submitted"
    assert "FOR UPDATE" in str(submit_db.statements[0])
    assert submit_db.flush_count == submit_db.commit_count == 1

    stale_db = _Db(_Result(scalar=report))
    with _client(stale_db, member) as client:
        stale = client.post(
            f"/api/reports/{report.id}/submit",
            headers={"Origin": ORIGIN},
            json={"expected_status_code": "draft"},
        )
    assert stale.status_code == 409
    assert stale.json() == {"detail": "invalid_state_transition"}
    assert stale_db.commit_count == 0
    assert stale_db.rollback_count == 1


def test_member_scope_hides_other_authors_report():
    member = _member()
    hidden_db = _Db(_Result(rows=[]))
    report_id = uuid4()
    with _client(hidden_db, member) as client:
        hidden = client.get(f"/api/reports/{report_id}")
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "report_not_found"}

    sql = str(hidden_db.statements[0])
    assert "report.author_member_id" in sql

    locked_db = _Db(_Result(scalar=None))
    with _client(locked_db, member) as client:
        missing = client.post(
            f"/api/reports/{report_id}/submit",
            headers={"Origin": ORIGIN},
            json={"expected_status_code": "draft"},
        )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "report_not_found"}
    assert locked_db.rollback_count == 1


def test_member_cannot_attach_another_owners_activity():
    member = _member()
    foreign = _activity(_member(team_id=member.team_id))

    db = _Db(_Result(scalar_values=[]))
    with _client(db, member) as client:
        response = client.post(
            "/api/reports",
            headers={"Origin": ORIGIN},
            json={
                "report_kind": "daily",
                "report_date": "2026-08-17",
                "template_snapshot": TEMPLATE,
                "content": CONTENT,
                "activity_ids": [str(foreign.id)],
            },
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "activity_not_found"}
    assert db.commit_count == 0
    assert db.rollback_count == 1

    sql = str(db.statements[0])
    assert "activity.owner_member_id" in sql
    assert "activity.deleted_at IS NULL" in sql


def test_manager_author_filter_is_limited_to_same_team():
    member = _member(role="member")
    denied_db = _Db()
    with _client(denied_db, member) as client:
        denied = client.get(f"/api/reports?author_member_id={uuid4()}")
    assert denied.status_code == 403
    assert denied.json() == {"detail": "scope_not_allowed"}

    manager = _member(role="manager")
    unknown_db = _Db(_Result(scalar_values=[]))
    with _client(unknown_db, manager) as client:
        unknown = client.get(f"/api/reports?author_member_id={uuid4()}")
    assert unknown.status_code == 403
    assert unknown.json() == {"detail": "scope_not_allowed"}


def test_write_failure_rolls_back_transaction():
    member = _member()
    db = _Db(flush_error=RuntimeError("synthetic failure"))

    with _client(db, member) as client, pytest.raises(RuntimeError, match="synthetic failure"):
        client.post(
            "/api/reports",
            headers={"Origin": ORIGIN},
            json={
                "report_kind": "daily",
                "report_date": "2026-08-17",
                "template_snapshot": TEMPLATE,
                "content": CONTENT,
            },
        )

    assert db.commit_count == 0
    assert db.rollback_count == 1


def test_source_activity_filter_reaches_the_query():
    """이 일정으로 쓴 보고서가 있는지를 서버가 직접 답해야 한다.

    이 조건이 쿼리에 실리지 않으면 저장 화면이 목록 첫 페이지만 보고 없다고 판단해,
    이미 보고서가 있는 일정에 같은 보고서를 하나 더 만든다.
    """
    member = _member()
    activity_id = uuid4()
    db = _Db(_Result(scalar=0), _Result(rows=[]))

    with _client(db, member) as client:
        response = client.get(
            "/api/reports",
            params={
                "report_kind": "meeting",
                "source_activity_id": str(activity_id),
                "limit": 1,
            },
        )

    assert response.status_code == 200
    assert response.json()["total"] == 0
    # 개수 쿼리와 행 쿼리 모두 같은 조건으로 좁혀야 총계와 목록이 어긋나지 않는다.
    for statement in db.statements:
        assert "report.source_activity_id = " in str(statement)


def test_approver_and_hospital_filters_reach_the_query():
    """보고 대상과 고객사는 컬럼이 아니라 content 안에 있다.

    예전에는 전건을 받아 화면에서 걸렀다. 한 쪽만 받는 지금 이 조건이 쿼리에 실리지
    않으면 첫 쪽에 없는 일치 항목이 통째로 빠진다.
    """
    member = _member(role="manager")
    db = _Db(_Result(scalar=0), _Result(rows=[]))

    with _client(db, member) as client:
        response = client.get(
            "/api/reports",
            params={"approver": "김팀장", "hospital": "한빛대학교병원"},
        )

    assert response.status_code == 200
    # 개수 쿼리와 행 쿼리 모두 같은 조건으로 좁혀야 총계와 목록이 어긋나지 않는다.
    for statement in db.statements:
        text = str(statement)
        assert "coalesce" in text.lower()
        assert "report.content -> " in text or "report.content ->> " in text


def test_search_also_looks_inside_the_report_body():
    """보고 본문은 content 에 있다. 여기를 빼면 검색이 메모 검색이 되어 버린다."""
    member = _member(role="manager")
    db = _Db(_Result(scalar=0), _Result(rows=[]))

    with _client(db, member) as client:
        response = client.get("/api/reports", params={"q": "한빛"})

    assert response.status_code == 200
    for statement in db.statements:
        assert "CAST(public.report.content AS TEXT)) LIKE" in str(statement)


def test_filter_options_only_count_values_in_scope():
    """선택지는 목록에 실제로 있는 값만 내놓아야 고르고도 0 건이 되지 않는다."""
    member = _member(role="manager")
    db = _Db(
        _Result(scalar_values=["김팀장", "박이사"]),
        _Result(scalar_values=["한빛대학교병원"]),
    )

    with _client(db, member) as client:
        response = client.get("/api/report-filter-options")

    assert response.status_code == 200
    assert response.json() == {
        "approvers": ["김팀장", "박이사"],
        "hospitals": ["한빛대학교병원"],
    }
    # 목록과 같은 범위를 봐야 한다. 범위 밖 작성자의 값이 선택지에 서면 고르고도 0 건이다.
    for statement in db.statements:
        assert "report.team_id = " in str(statement)


def test_unknown_report_filter_is_rejected():
    """오타 난 조건이 조용히 무시되면 화면은 걸렀다고 믿고 전건을 보여 준다."""
    with pytest.raises(ValidationError):
        ReportPageParams(hospitals=["한빛대학교병원"])
