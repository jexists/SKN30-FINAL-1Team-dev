"""팀장의 보고서 검토(유스케이스 RPT-004).

제출된 보고서를 팀장이 확정하거나 반려한다. 반려는 rejected 가 아니라 changes_requested
로 가는데, 반려한 보고서는 팀원이 고쳐서 다시 내야 하고 고칠 수 있는 상태가 그쪽이기
때문이다. 이 규칙이 깨지면 반려가 곧 폐기가 된다.
"""

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
from app.models.workspace import Member
from app.schemas.reports import ReportReview

ORIGIN = settings.cors_origin_list[0]
NOW = datetime(2026, 8, 17, 9, tzinfo=UTC)
TEMPLATE = {"fields": [{"id": "summary", "label": "요약"}]}
CONTENT = {"summary": "합성 보고 내용"}
_MISSING = object()


class _Result:
    def __init__(self, *, scalar=_MISSING, rows=None):
        self.scalar = scalar
        self.rows = [] if rows is None else rows

    def scalar_one_or_none(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def scalar_one(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def one_or_none(self):
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class _Db:
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.statements = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "예상보다 많은 쿼리가 실행되었습니다."
        return self.results.pop(0)

    def add(self, value):
        raise AssertionError("검토는 행을 새로 만들지 않습니다.")

    async def flush(self):
        self.flush_count += 1

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


def _report(author: Member, *, status_code: str = "submitted") -> Report:
    return Report(
        id=uuid4(),
        team_id=author.team_id,
        author_member_id=author.id,
        recipient_member_id=None,
        template_snapshot=TEMPLATE,
        source_activity_id=None,
        sales_deal_id=None,
        report_kind="meeting",
        report_date=date(2026, 8, 17),
        period_start=None,
        period_end=None,
        status_code=status_code,
        content=CONTENT,
        transcript=None,
        source_snapshot=None,
        ai_evidence=None,
        note="활동 3건",
        review_note=None,
        reviewed_by_member_id=None,
        reviewed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def _params(db: _Db) -> list[UUID]:
    """첫 조회에 실린 source_activity_id 목록. IN 절이라 값이 목록으로 묶여 들어온다."""
    values = db.statements[0].compile().params.values()
    # role_code IN (...) 도 목록으로 들어오므로 UUID 로 된 목록만 고른다.
    return next(
        value
        for value in values
        if isinstance(value, list) and all(isinstance(item, UUID) for item in value)
    )


def _review(db: _Db, member: Member, report: Report, **payload):
    with _client(db, member) as client:
        return client.post(
            f"/api/reports/{report.id}/review",
            headers={"Origin": ORIGIN},
            json={"expected_status_code": "submitted", **payload},
        )


def test_review_requires_a_reason_when_rejecting():
    """반려에는 까닭이 있어야 한다. 무엇을 고칠지 없이 돌려보내면 같은 것이 다시 온다."""
    with pytest.raises(ValidationError):
        ReportReview(decision="reject", expected_status_code="submitted")

    # 확정은 사유가 없어도 된다.
    assert ReportReview(decision="approve", expected_status_code="submitted").reason is None

    with pytest.raises(ValidationError):
        # 제출되지 않은 보고서는 검토 대상이 아니다.
        ReportReview(decision="approve", expected_status_code="draft")


def test_approval_clears_the_review_note_even_if_a_reason_is_sent():
    """확정 요청에 사유가 실려 와도 남기지 않는다. 옛 지적이 붙어 있으면 무엇이 남은
    문제인지 알 수 없다."""
    manager = _member(role="manager")
    author = _member(team_id=manager.team_id)
    report = _report(author)
    report.review_note = "고객 요구사항 내용이 부족합니다."

    db = _Db(
        _Result(scalar=report),
        _Result(rows=[(report, author.display_name, None)]),
        _Result(rows=[]),
    )
    response = _review(db, manager, report, decision="approve", reason="확인했습니다.")

    assert response.status_code == 200
    assert report.status_code == "approved"
    assert report.review_note is None


def test_manager_approves_a_teammates_report():
    manager = _member(role="manager")
    author = _member(team_id=manager.team_id)
    report = _report(author)

    db = _Db(
        _Result(scalar=report),
        _Result(rows=[(report, author.display_name, None)]),
        _Result(rows=[]),
    )
    response = _review(db, manager, report, decision="approve")

    assert response.status_code == 200
    assert response.json()["status_code"] == "approved"
    assert report.status_code == "approved"
    assert report.reviewed_by_member_id == manager.id
    assert report.reviewed_at is not None
    # 확정하면 지난 반려 사유를 남겨 두지 않는다.
    assert report.review_note is None
    # 작성자가 적어 둔 note 는 검토가 건드리지 않는다. 일일보고서는 여기에 제 요약을 넣는다.
    assert report.note == "활동 3건"
    assert "FOR UPDATE" in str(db.statements[0])
    assert db.flush_count == db.commit_count == 1


def test_rejection_returns_the_report_to_an_editable_state():
    """반려는 changes_requested 다. 팀원이 고쳐서 다시 낼 수 있어야 한다."""
    manager = _member(role="manager")
    author = _member(team_id=manager.team_id)
    report = _report(author)

    db = _Db(
        _Result(scalar=report),
        _Result(rows=[(report, author.display_name, None)]),
        _Result(rows=[]),
    )
    response = _review(
        db,
        manager,
        report,
        decision="reject",
        reason="고객 요구사항 내용이 부족합니다.",
    )

    assert response.status_code == 200
    assert response.json()["status_code"] == "changes_requested"
    assert report.status_code == "changes_requested"
    assert report.review_note == "고객 요구사항 내용이 부족합니다."
    assert report.note == "활동 3건"
    # reports._EDITABLE_STATUSES 가 이 상태를 열어 주어야 반려가 폐기가 되지 않는다.
    from app.api.reports import _EDITABLE_STATUSES

    assert "changes_requested" in _EDITABLE_STATUSES


def test_members_cannot_review():
    """검토는 팀장의 일이다. 팀원은 남의 보고서를 확정할 수 없다."""
    teammate = _member()
    report = _report(_member(team_id=teammate.team_id))

    db = _Db()
    response = _review(db, teammate, report, decision="approve")

    assert response.status_code == 403
    assert response.json() == {"detail": "manager_required"}
    # 권한부터 끊으므로 조회조차 하지 않는다.
    assert db.statements == []
    assert db.commit_count == 0


def test_manager_cannot_review_their_own_report():
    """자기가 쓴 보고서를 자기가 확정하지 않는다."""
    manager = _member(role="manager")
    report = _report(manager)

    db = _Db(_Result(scalar=report))
    response = _review(db, manager, report, decision="approve")

    assert response.status_code == 403
    assert response.json() == {"detail": "self_review_not_allowed"}
    assert report.status_code == "submitted"
    assert db.commit_count == 0
    assert db.rollback_count == 1


def test_review_rejects_a_stale_expectation():
    """다른 팀장이 먼저 확정했으면 두 번째 검토는 덮어쓰지 않는다."""
    manager = _member(role="manager")
    author = _member(team_id=manager.team_id)
    report = _report(author, status_code="approved")

    db = _Db(_Result(scalar=report))
    response = _review(db, manager, report, decision="reject", reason="다시 봅니다.")

    assert response.status_code == 409
    assert response.json() == {"detail": "invalid_state_transition"}
    assert report.status_code == "approved"
    assert db.commit_count == 0


def test_missing_report_is_not_found():
    manager = _member(role="manager")
    report = _report(_member(team_id=manager.team_id))

    db = _Db(_Result(scalar=None))
    response = _review(db, manager, report, decision="approve")

    assert response.status_code == 404
    assert response.json() == {"detail": "report_not_found"}


def test_report_list_accepts_many_source_activities():
    """대시보드가 하루치 일정의 보고서 유무를 한 번에 묻는다.

    값 하나만 보내던 기존 호출(업무보고서 작성 화면의 중복 확인)도 그대로 통해야 한다.
    질의 문자열로 확인한다. 모델을 직접 만들면 FastAPI 가 붙여 주는 단일값 → 목록 변환을
    건너뛰어 실제 호출과 다른 것을 보게 된다.
    """
    member = _member(role="manager")
    one = uuid4()
    two = uuid4()

    many_db = _Db(_Result(scalar=0), _Result(rows=[]), _Result(rows=[]))
    with _client(many_db, member) as client:
        many = client.get(f"/api/reports?source_activity_id={one}&source_activity_id={two}")
    assert many.status_code == 200
    assert _params(many_db) == [one, two]

    single_db = _Db(_Result(scalar=0), _Result(rows=[]), _Result(rows=[]))
    with _client(single_db, member) as client:
        single = client.get(f"/api/reports?source_activity_id={one}")
    assert single.status_code == 200
    assert _params(single_db) == [one]
