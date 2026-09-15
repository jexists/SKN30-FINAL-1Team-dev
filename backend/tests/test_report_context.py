from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.services import report_context


class _Result:
    def __init__(self, rows=(), scalar=None):
        self.rows = rows
        self.scalar = scalar

    def all(self):
        return self.rows

    def scalar_one_or_none(self):
        return self.scalar

    def scalar_one(self):
        return self.scalar


class _Db:
    def __init__(self, *results):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0)


def _rows():
    report = SimpleNamespace(
        id=uuid4(),
        source_activity_id=uuid4(),
        report_date=date(2026, 9, 15),
    )
    submission = SimpleNamespace(
        id=uuid4(),
        submitted_at=datetime(2026, 9, 15, 10, tzinfo=UTC),
        snapshot={
            "title": "LR1000 후속 협의",
            "common_body": "다음 방문에서 도입 일정을 확인합니다.",
            "unassigned_body": None,
            "deals": [
                {
                    "sales_deal_id": str(uuid4()),
                    "deal_title_snapshot": "LR1000 도입",
                    "body": "견적 범위를 다시 검토하기로 했습니다.",
                }
            ],
        },
    )
    return report, submission


@pytest.mark.anyio
async def test_recent_reports_reads_current_three():
    report, submission = _rows()
    db = _Db(_Result(rows=[(report, submission)]))
    member = SimpleNamespace(team_id=uuid4())
    output = await report_context.recent_reports(
        db,
        member=member,
        customer_company_id=uuid4(),
    )

    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert 3 in compiled.params.values()
    assert "report_submission.id = public.report.current_submission_id" in sql
    assert output[0]["meeting_shared"]["common_report"].startswith("다음 방문")
    assert output[0]["deal_reports"][0]["title"] == "LR1000 도입"


@pytest.mark.anyio
async def test_rag_search_includes_recent_reports_and_returns_ranked_context():
    report, submission = _rows()
    db = _Db(
        _Result(scalar=None),  # migrationless fallback
        _Result(scalar=1),  # full current-report corpus
        _Result(rows=[(report, submission, 0.5)]),
    )
    search = {}

    output = await report_context.search_historical_reports(
        db,
        member=SimpleNamespace(team_id=uuid4()),
        customer_company_id=uuid4(),
        query="LR1000 견적",
        search_info=search,
    )

    compiled = db.statements[2].compile(dialect=postgresql.dialect())
    assert "NOT IN" not in str(compiled)
    assert "report_submission.snapshot" in str(compiled)
    assert search == {
        "method": "keyword",
        "status": "completed",
        "corpus": "snapshot_fallback",
        "corpus_count": 1,
        "retrieved_count": 1,
    }
    assert output[0]["id"] == str(report.id)
    assert output[0]["score"] > 0


@pytest.mark.anyio
async def test_id_lookup_keeps_the_same_company_scope():
    report, submission = _rows()
    db = _Db(_Result(rows=[(report, submission)]))
    args = {
        "member": SimpleNamespace(team_id=uuid4()),
        "customer_company_id": uuid4(),
    }

    output = await report_context.reports_by_ids(db, **args, report_ids={report.id})

    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    assert [report.id] in compiled.params.values()
    assert output[0]["id"] == str(report.id)
