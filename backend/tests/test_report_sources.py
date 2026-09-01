"""하위 보고서 집계 입력의 권한·기간·본문 경계를 mock으로 검사한다."""

import asyncio
import json
from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import reports
from app.models.content import Report
from app.models.workspace import Member
from app.services import report_sources as service


@pytest.fixture
def sample(monkeypatch):
    member = Member(id=uuid4(), team_id=uuid4(), active=True, role_code="member")
    parent = Report(
        id=uuid4(),
        team_id=member.team_id,
        author_member_id=member.id,
        report_kind="daily",
        report_date=date(2026, 8, 20),
        content={"activities": []},
    )
    activity_id = uuid4()
    sources = [
        Report(
            id=uuid4(),
            team_id=member.team_id,
            author_member_id=member.id,
            report_kind="meeting",
            report_date=parent.report_date,
            status_code="approved",
            sales_deal_id=uuid4(),
            source_activity_id=activity_id,
            content={
                "title": f"딜별 보고서 {index}",
                "values": {"body": f"검토한 내용 {index}"},
                "ai_values": {"body": "미검토 초안"},
                "deal_assessment": {"label": "high"},
            },
            transcript="전달하면 안 되는 전체 원문",
            ai_evidence={"prediction": "high"},
        )
        for index in range(2)
    ]
    by_id = {source.id: source for source in sources}
    lookup = AsyncMock(side_effect=lambda db, member, source_id: (by_id[source_id], None, None))
    monkeypatch.setattr(reports, "_report_row", lookup)
    return member, parent, sources, lookup


def refs(parent, sources, label="업무보고서"):
    parent.content["activities"] = [
        {
            "source": label,
            "included": True,
            "refId": str(source.id),
            "title": "클라이언트가 보낸 제목은 신뢰하지 않음",
            "desc": "가짜 요약",
        }
        for source in sources
    ]


def run(sample):
    member, parent, _, _ = sample
    return asyncio.run(service.build_report_sources(AsyncMock(), member, parent))


def test_daily_loads_stored_values_and_deduplicates_meeting_shared(sample):
    _, parent, sources, lookup = sample
    refs(parent, sources)
    for source in sources:
        source.content["meeting_shared"] = {
            "run_id": str(uuid4()),
            "common_report": {"body": "공통 배경", "evidence_ids": ["S0001"]},
            "unassigned_report": {
                "body": "딜 미지정 · 확인 필요: 그것도 보내달라고 함",
                "evidence_ids": ["S0002"],
            },
            "ml_result": "제외해야 함",
        }

    result = run(sample)

    json.dumps(result, ensure_ascii=False)
    assert len(result["reports"]) == 2
    assert result["reports"][0] == {
        "id": str(sources[0].id),
        "sales_deal_id": str(sources[0].sales_deal_id),
        "source_activity_id": str(sources[0].source_activity_id),
        "report_date": "2026-08-20",
        "period_start": None,
        "period_end": None,
        "title": "딜별 보고서 0",
        "values": {"body": "검토한 내용 0"},
    }
    assert result["meetings"] == [
        {
            "activity_id": str(sources[0].source_activity_id),
            "common_report": {"body": "공통 배경"},
            "unassigned_report": {"body": "딜 미지정 · 확인 필요: 그것도 보내달라고 함"},
        }
    ]
    assert "전체 원문" not in str(result) and "미검토 초안" not in str(result)
    assert "ml_result" not in str(result) and "evidence_ids" not in str(result)
    assert lookup.await_count == 2


def test_daily_keeps_each_common_body_linked_to_its_meeting(sample):
    _, parent, sources, _ = sample
    refs(parent, sources)
    for index, source in enumerate(sources):
        source.source_activity_id = uuid4()
        source.content["meeting_shared"] = {"common_report": {"body": f"공통 일정 {index}"}}

    result = run(sample)

    assert len(result["meetings"]) == 2
    meetings = {item["activity_id"]: item for item in result["meetings"]}
    for index, report in enumerate(result["reports"]):
        assert meetings[report["source_activity_id"]]["common_report"] == {
            "body": f"공통 일정 {index}"
        }
        assert "공통 일정" not in str(report["values"])


@pytest.mark.parametrize(
    "content",
    [
        {},
        {"summary": "legacy"},
        {"activities": []},
        {
            "activities": [
                {"source": "캘린더", "included": True, "refId": str(uuid4())},
                {"source": "업무보고서", "included": False, "refId": "not-loaded"},
            ],
        },
    ],
)
def test_no_report_sources_keeps_legacy_callers_compatible(sample, content):
    _, parent, _, lookup = sample
    parent.content = content
    assert run(sample) == {"reports": [], "meetings": []}
    lookup.assert_not_awaited()


@pytest.mark.parametrize(
    "mutation,detail",
    [
        (
            lambda p, s: p.content["activities"].append(p.content["activities"][0]),
            "report_source_duplicate",
        ),
        (
            lambda p, s: p.content["activities"][0].update(refId=str(p.id)),
            "report_source_self_reference",
        ),
        (
            lambda p, s: p.content["activities"][0].update(refId="bad-id"),
            "report_source_id_invalid",
        ),
        (
            lambda p, s: p.content["activities"][0].update(included="true"),
            "report_source_included_invalid",
        ),
        (
            lambda p, s: p.content["activities"][0].update(source="일일보고서"),
            "report_source_kind_invalid",
        ),
    ],
)
def test_invalid_source_selection_is_not_silently_skipped(sample, mutation, detail):
    _, parent, sources, lookup = sample
    refs(parent, sources)
    mutation(parent, sources)
    with pytest.raises(HTTPException) as error:
        run(sample)
    assert error.value.detail == detail
    lookup.assert_not_awaited()


def test_source_count_limit_is_enforced_before_loading(sample):
    _, parent, _, lookup = sample
    parent.content["activities"] = [
        {"source": "업무보고서", "included": True, "refId": str(uuid4())}
        for _ in range(service.SOURCE_REPORT_LIMIT + 1)
    ]
    with pytest.raises(HTTPException) as error:
        run(sample)
    assert error.value.detail == "report_source_limit_exceeded"
    lookup.assert_not_awaited()


def test_missing_or_unauthorized_report_fails_instead_of_returning_partial_sources(sample):
    _, parent, sources, lookup = sample
    refs(parent, sources)
    lookup.side_effect = [(sources[0], None, None), HTTPException(404, "report_not_found")]
    with pytest.raises(HTTPException) as error:
        run(sample)
    assert error.value.status_code == 404


@pytest.mark.parametrize(
    "field,value,detail",
    [
        ("report_kind", "daily", "report_source_kind_invalid"),
        ("status_code", "draft", "report_source_not_finalized"),
        ("status_code", "changes_requested", "report_source_not_finalized"),
        ("report_date", date(2026, 8, 21), "report_source_outside_period"),
    ],
)
def test_source_kind_status_and_day_are_verified_from_database(sample, field, value, detail):
    _, parent, sources, _ = sample
    refs(parent, sources)
    setattr(sources[0], field, value)
    with pytest.raises(HTTPException) as error:
        run(sample)
    assert error.value.detail == detail


def test_weekly_includes_submitted_daily_reports_within_period(sample):
    _, parent, sources, _ = sample
    parent.report_kind = "weekly"
    parent.period_start, parent.period_end = date(2026, 8, 16), date(2026, 8, 22)
    for source in sources:
        source.report_kind, source.status_code = "daily", "submitted"
    refs(parent, sources, "일일보고서")
    assert len(run(sample)["reports"]) == 2
    sources[0].report_date = date(2026, 8, 23)
    with pytest.raises(HTTPException) as error:
        run(sample)
    assert error.value.detail == "report_source_outside_period"


def test_monthly_accepts_previous_month_week_when_its_period_overlaps(sample):
    _, parent, sources, _ = sample
    parent.report_kind = "monthly"
    parent.period_start, parent.period_end = date(2026, 8, 1), date(2026, 8, 31)
    source = sources[0]
    source.report_kind = "weekly"
    source.report_date = date(2026, 7, 26)
    source.period_start, source.period_end = date(2026, 7, 26), date(2026, 8, 1)
    refs(parent, [source], "주간보고서")
    assert len(run(sample)["reports"]) == 1
    source.period_start, source.period_end = date(2026, 7, 19), date(2026, 7, 25)
    with pytest.raises(HTTPException) as error:
        run(sample)
    assert error.value.detail == "report_source_outside_period"


@pytest.mark.parametrize(
    "period_start,period_end",
    [
        (date(2026, 7, 26), date(2026, 8, 1)),
        (date(2026, 8, 30), date(2026, 9, 5)),
    ],
)
def test_monthly_preserves_cross_month_week_period_and_body(sample, period_start, period_end):
    _, parent, sources, _ = sample
    parent.report_kind = "monthly"
    parent.period_start, parent.period_end = date(2026, 8, 1), date(2026, 8, 31)
    source = sources[0]
    source.report_kind = "weekly"
    source.report_date = period_start
    source.period_start, source.period_end = period_start, period_end
    source.content["values"] = {"body": "주간 전체 논의이며 개별 사실의 날짜는 적혀 있지 않다."}
    refs(parent, [source], "주간보고서")

    result = run(sample)["reports"]

    assert len(result) == 1
    assert result[0]["report_date"] == period_start.isoformat()
    assert result[0]["period_start"] == period_start.isoformat()
    assert result[0]["period_end"] == period_end.isoformat()
    assert result[0]["values"] == source.content["values"]


def test_conflicting_shared_copies_do_not_silently_overwrite_one_another(sample):
    _, parent, sources, _ = sample
    refs(parent, sources)
    for index, source in enumerate(sources):
        source.content["meeting_shared"] = {"unassigned_report": {"body": f"미지정 {index}"}}
    with pytest.raises(HTTPException) as error:
        run(sample)
    assert error.value.detail == "report_source_shared_conflict"


def test_body_values_never_fall_back_to_ai_or_metadata(sample):
    _, parent, sources, _ = sample
    refs(parent, sources[:1])
    sources[0].content["values"] = {
        "body": "사람 검토 본문",
        "ai_values": "AI 초안",
        "transcript": "원문",
        "deal_assessment": "승리",
    }
    assert run(sample)["reports"][0]["values"] == {"body": "사람 검토 본문"}
    del sources[0].content["values"]
    assert run(sample)["reports"][0]["values"] == {}


def test_malformed_source_discriminator_returns_validation_error(sample):
    _, parent, _, lookup = sample
    parent.content["activities"] = [{"source": [], "included": True}]
    with pytest.raises(HTTPException) as error:
        run(sample)
    assert error.value.detail == "report_sources_invalid"
    lookup.assert_not_awaited()


def test_shared_body_is_not_truncated_or_replaced_with_a_summary(sample):
    _, parent, sources, _ = sample
    refs(parent, sources[:1])
    body = "딜 미지정 내용 " * 10_000
    sources[0].content["meeting_shared"] = {"unassigned_report": {"body": body}}
    assert run(sample)["meetings"][0]["unassigned_report"]["body"] == body


def test_invalid_parent_period_fails_when_sources_are_selected(sample):
    _, parent, sources, _ = sample
    parent.report_kind = "weekly"
    sources[0].report_kind = "daily"
    refs(parent, sources[:1], "일일보고서")
    with pytest.raises(HTTPException) as error:
        run(sample)
    assert error.value.detail == "report_source_period_invalid"


def test_cannot_generate_someone_elses_parent_report_even_as_manager(sample):
    member, parent, sources, lookup = sample
    refs(parent, sources)
    member.role_code = "manager"
    parent.author_member_id = uuid4()
    with pytest.raises(HTTPException) as error:
        run(sample)
    assert error.value.detail == "report_not_owned"
    lookup.assert_not_awaited()
