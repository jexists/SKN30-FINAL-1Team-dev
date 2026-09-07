"""하위 보고서 집계 입력의 권한·기간·본문 경계를 mock으로 검사한다."""

import asyncio
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.models.content import Report, ReportSource, ReportSubmission
from app.models.workspace import Member
from app.services import report_sources as service
from app.services import report_submissions


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
            title=f"딜별 보고서 {index}",
            body=f"검토한 내용 {index}",
            common_body=None,
            unassigned_body=None,
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
    for source in sources:
        source.current_submission_id = uuid4()
    by_id = {source.id: source for source in sources}
    lookup = AsyncMock(side_effect=lambda db, member, source_id: (by_id[source_id], None, None))

    async def report_deals(_db, report_id):
        source = by_id[report_id]
        return [
            SimpleNamespace(
                sales_deal_id=source.sales_deal_id,
                title=source.title,
                body=source.body,
                content=source.content,
            )
        ]

    monkeypatch.setattr(service, "_report_deals", report_deals)
    monkeypatch.setattr(service, "_report_source_rows", AsyncMock(return_value=[]))

    async def source_submissions(_db, submission_ids):
        output = {}
        for submission_id in submission_ids:
            source = next(item for item in sources if item.current_submission_id == submission_id)
            snapshot = {
                "schema_version": "report_submission.v1",
                "report_id": str(source.id),
                "report_kind": source.report_kind,
                "report_date": source.report_date.isoformat(),
                "period_start": (
                    source.period_start.isoformat() if source.period_start is not None else None
                ),
                "period_end": (
                    source.period_end.isoformat() if source.period_end is not None else None
                ),
                "source_activity_id": (
                    str(source.source_activity_id)
                    if source.source_activity_id is not None
                    else None
                ),
                "title": source.title,
                "body": source.body,
                "common_body": source.common_body,
                "unassigned_body": source.unassigned_body,
                "structured_values": {},
                "deals": (
                    [
                        {
                            "sales_deal_id": str(source.sales_deal_id),
                            "title": source.title,
                            "body": source.body,
                            "structured_values": {},
                        }
                    ]
                    if source.report_kind == "meeting" and source.sales_deal_id is not None
                    else []
                ),
            }
            submission = ReportSubmission(
                id=submission_id,
                report_id=source.id,
                revision_no=1,
                report_version=1,
                team_id=source.team_id,
                submitted_by_member_id=source.author_member_id,
                snapshot=snapshot,
                snapshot_sha256=report_submissions.snapshot_sha256(snapshot),
                review_status="approved" if source.status_code == "approved" else "pending",
                reviewed_by_member_id=None,
                reviewed_at=None,
                review_note=None,
            )
            output[submission_id] = (submission, source)
        return output

    monkeypatch.setattr(service, "_source_submissions", source_submissions)
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
    member, parent, _, lookup = sample

    class SourceDb:
        async def execute(self, _statement):
            selected_ids = [
                item.get("refId")
                for item in parent.content.get("activities", [])
                if isinstance(item, dict)
                and item.get("included") is True
                and item.get("source") in service._SOURCES
            ]
            loaded = [
                (await lookup(self, member, UUID(str(source_id))))[0] for source_id in selected_ids
            ]
            result = MagicMock()
            result.scalars.return_value.all.return_value = loaded
            return result

    return asyncio.run(service.build_report_sources(SourceDb(), member, parent))


def test_daily_loads_stored_values_and_deduplicates_meeting_shared(sample):
    _, parent, sources, lookup = sample
    refs(parent, sources)
    for source in sources:
        source.common_body = "공통 배경"
        source.unassigned_body = "딜 미지정 · 확인 필요: 그것도 보내달라고 함"
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
        "submission_id": str(sources[0].current_submission_id),
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


def test_daily_keeps_shared_body_from_a_no_deal_meeting(sample):
    _, parent, sources, lookup = sample
    source = sources[0]
    source.sales_deal_id = None
    source.common_body = "고객사가 신규 사업 방향을 공유했습니다."
    refs(parent, [source])

    result = run(sample)

    assert result["reports"] == []
    assert result["meetings"] == [
        {
            "activity_id": str(source.source_activity_id),
            "common_report": {"body": source.common_body},
            "unassigned_report": None,
        }
    ]
    lookup.assert_awaited_once()


def test_normalized_source_reads_the_immutable_submission_instead_of_mutable_report(
    sample, monkeypatch
):
    member, parent, sources, lookup = sample
    source = sources[0]
    source.content = {"values": {"body": "제출 뒤 변조된 현재 초안"}}
    submission = ReportSubmission(
        id=uuid4(),
        report_id=source.id,
        revision_no=1,
        report_version=4,
        team_id=member.team_id,
        submitted_by_member_id=member.id,
        snapshot={
            "schema_version": "report_submission.v1",
            "report_id": str(source.id),
            "report_kind": "meeting",
            "report_date": parent.report_date.isoformat(),
            "period_start": None,
            "period_end": None,
            "source_activity_id": str(source.source_activity_id),
            "common_body": "확정 당시 공통 내용",
            "unassigned_body": None,
            "deals": [
                {
                    "sales_deal_id": str(source.sales_deal_id),
                    "title": "확정 당시 제목",
                    "body": "확정 당시 딜 본문",
                    "structured_values": {
                        "next_step": "견적 전달",
                        "transcript": "전달하면 안 되는 원문",
                        "ai_values": "전달하면 안 되는 초안",
                        "rawTranscript": "표기만 바꾼 원문",
                        "AI-Values": "표기만 바꾼 초안",
                    },
                }
            ],
        },
        snapshot_sha256="0" * 64,
        review_status="pending",
        reviewed_by_member_id=None,
        reviewed_at=None,
        review_note=None,
    )
    submission.snapshot_sha256 = report_submissions.snapshot_sha256(submission.snapshot)
    row = SimpleNamespace(
        source_activity_id=None,
        source_report_submission_id=submission.id,
    )
    monkeypatch.setattr(service, "_report_source_rows", AsyncMock(return_value=[row]))
    monkeypatch.setattr(
        service,
        "_source_submissions",
        AsyncMock(return_value={submission.id: (submission, source)}),
    )

    result = run(sample)

    assert result["reports"][0]["submission_id"] == str(submission.id)
    assert result["reports"][0]["title"] == "확정 당시 제목"
    assert result["reports"][0]["values"] == {"body": "확정 당시 딜 본문"}
    assert submission.snapshot["deals"][0]["structured_values"]["next_step"] == "견적 전달"
    assert result["meetings"][0]["common_report"] == {"body": "확정 당시 공통 내용"}
    assert "변조된 현재 초안" not in str(result)
    assert "전달하면 안 되는" not in str(result)
    lookup.assert_not_awaited()


def test_generation_freezes_the_same_submission_and_activity_refs_used_as_input(
    sample, monkeypatch
):
    member, parent, sources, _ = sample
    source = sources[0]
    source.body = "제출 뒤 바뀐 현재 본문"
    submission = ReportSubmission(
        id=uuid4(),
        report_id=source.id,
        revision_no=1,
        report_version=1,
        team_id=member.team_id,
        submitted_by_member_id=member.id,
        snapshot={
            "schema_version": "report_submission.v1",
            "report_id": str(source.id),
            "report_kind": "meeting",
            "report_date": parent.report_date.isoformat(),
            "period_start": None,
            "period_end": None,
            "source_activity_id": str(source.source_activity_id),
            "common_body": None,
            "unassigned_body": None,
            "deals": [
                {
                    "sales_deal_id": str(source.sales_deal_id),
                    "title": "생성에 사용한 제출 제목",
                    "body": "생성에 사용한 제출 본문",
                    "structured_values": {},
                }
            ],
        },
        snapshot_sha256="0" * 64,
        review_status="pending",
        reviewed_by_member_id=None,
        reviewed_at=None,
        review_note=None,
    )
    submission.snapshot_sha256 = report_submissions.snapshot_sha256(submission.snapshot)
    activity_id = uuid4()
    activity = {"id": activity_id, "source": "캘린더", "included": True}
    monkeypatch.setattr(
        service,
        "_resolve_report_source_refs",
        AsyncMock(
            return_value=(
                [(None, submission.id), (activity_id, None)],
                [activity],
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "_source_submissions",
        AsyncMock(return_value={submission.id: (submission, source)}),
    )

    sources_input, frozen_refs = asyncio.run(
        service.freeze_report_sources(AsyncMock(), member, parent)
    )

    assert sources_input["reports"][0]["submission_id"] == str(submission.id)
    assert sources_input["reports"][0]["values"] == {"body": "생성에 사용한 제출 본문"}
    assert sources_input["activities"] == [{**activity, "id": str(activity_id)}]
    assert frozen_refs == [
        {
            "position": 0,
            "source_activity_id": None,
            "source_report_submission_id": str(submission.id),
        },
        {
            "position": 1,
            "source_activity_id": str(activity_id),
            "source_report_submission_id": None,
        },
    ]


def test_submission_snapshot_keeps_ordered_source_revision_refs(sample):
    _, parent, _, _ = sample
    first_submission_id, second_submission_id = uuid4(), uuid4()
    direct_activity_id = uuid4()
    rows = [
        ReportSource(
            report_id=parent.id,
            position=2,
            source_activity_id=None,
            source_report_submission_id=second_submission_id,
        ),
        ReportSource(
            report_id=parent.id,
            position=0,
            source_activity_id=direct_activity_id,
            source_report_submission_id=None,
        ),
        ReportSource(
            report_id=parent.id,
            position=1,
            source_activity_id=None,
            source_report_submission_id=first_submission_id,
        ),
    ]

    snapshot = report_submissions.build_submission_snapshot(parent, [], rows)

    assert snapshot["source_refs"] == [
        {
            "position": 0,
            "source_activity_id": str(direct_activity_id),
            "source_report_submission_id": None,
        },
        {
            "position": 1,
            "source_activity_id": None,
            "source_report_submission_id": str(first_submission_id),
        },
        {
            "position": 2,
            "source_activity_id": None,
            "source_report_submission_id": str(second_submission_id),
        },
    ]


def test_normalized_direct_activity_is_not_silently_dropped(sample, monkeypatch):
    member, parent, _, lookup = sample
    activity_id = uuid4()
    row = SimpleNamespace(
        source_activity_id=activity_id,
        source_report_submission_id=None,
    )
    activity = {
        "id": activity_id,
        "source": "캘린더",
        "included": True,
        "title": "견적 검토 후속 전화",
    }
    monkeypatch.setattr(service, "_report_source_rows", AsyncMock(return_value=[row]))
    monkeypatch.setattr(service, "_source_submissions", AsyncMock(return_value={}))
    load_activities = AsyncMock(return_value=[activity])
    monkeypatch.setattr(service, "_source_activities", load_activities)

    result = run(sample)

    assert result == {
        "reports": [],
        "meetings": [],
        "activities": [{**activity, "id": str(activity_id)}],
    }
    load_activities.assert_awaited_once_with(
        ANY,
        member,
        parent,
        [activity_id],
    )
    lookup.assert_not_awaited()


def test_direct_activity_times_are_given_to_the_writer_in_seoul_time(sample):
    member, parent, _, _ = sample
    parent.report_date = date(2026, 9, 3)
    activity_id = uuid4()
    activity = SimpleNamespace(
        id=activity_id,
        title="합성 미팅",
        starts_at=datetime(2026, 9, 3, 0, tzinfo=UTC),
        ends_at=datetime(2026, 9, 3, 1, tzinfo=UTC),
        completed_at=datetime(2026, 9, 3, 2, tzinfo=UTC),
        location="온라인",
        note=None,
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [activity]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    rows = asyncio.run(service._source_activities(db, member, parent, [activity_id]))

    assert rows[0]["starts_at"].isoformat() == "2026-09-03T09:00:00+09:00"
    assert rows[0]["ends_at"].isoformat() == "2026-09-03T10:00:00+09:00"
    assert rows[0]["completed_at"].isoformat() == "2026-09-03T11:00:00+09:00"


def test_new_period_save_materializes_selected_submission_as_canonical_source(sample, monkeypatch):
    member, parent, sources, _ = sample
    source = sources[0]
    source.current_submission_id = uuid4()
    refs(parent, [source])
    result = MagicMock()
    result.scalars.return_value.all.return_value = [source]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    monkeypatch.setattr(service, "_report_source_rows", AsyncMock(return_value=[]))

    changed = asyncio.run(service.sync_report_sources_from_legacy_content(db, member, parent))

    assert changed
    stored = db.add.call_args.args[0]
    assert stored.report_id == parent.id
    assert stored.position == 0
    assert stored.source_activity_id is None
    assert stored.source_report_submission_id == source.current_submission_id
    db.flush.assert_awaited_once()


def test_missing_activity_selection_clears_existing_canonical_sources(sample, monkeypatch):
    member, parent, _, _ = sample
    parent.content = {"values": {"body": "새 본문"}}
    existing = ReportSource(
        report_id=parent.id,
        position=0,
        source_activity_id=uuid4(),
        source_report_submission_id=None,
    )
    monkeypatch.setattr(service, "_report_source_rows", AsyncMock(return_value=[existing]))
    db = AsyncMock()
    db.add = MagicMock()

    changed = asyncio.run(service.sync_report_sources_from_legacy_content(db, member, parent))

    assert changed is True
    assert "delete from public.report_source" in str(db.execute.await_args.args[0]).lower()
    db.add.assert_not_called()


def test_new_period_save_rejects_a_selected_draft_as_not_finalized(sample, monkeypatch):
    member, parent, sources, _ = sample
    source = sources[0]
    source.status_code = "draft"
    source.current_submission_id = uuid4()
    refs(parent, [source])
    result = MagicMock()
    result.scalars.return_value.all.return_value = [source]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    monkeypatch.setattr(service, "_report_source_rows", AsyncMock(return_value=[]))

    with pytest.raises(HTTPException) as error:
        asyncio.run(service.sync_report_sources_from_legacy_content(db, member, parent))

    assert error.value.status_code == 409
    assert error.value.detail == "report_source_not_finalized"


def test_legacy_finalized_source_is_materialized_before_parent_links(sample, monkeypatch):
    member, parent, sources, _ = sample
    source = sources[0]
    source.current_submission_id = None
    refs(parent, [source])
    result = MagicMock()
    result.scalars.return_value.all.return_value = [source]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    submission_id = uuid4()

    async def materialize(_db, legacy):
        legacy.current_submission_id = submission_id
        return SimpleNamespace(id=submission_id)

    ensure = AsyncMock(side_effect=materialize)
    monkeypatch.setattr(service, "materialize_legacy_submission", ensure)
    monkeypatch.setattr(service, "_report_source_rows", AsyncMock(return_value=[]))

    changed = asyncio.run(service.sync_report_sources_from_legacy_content(db, member, parent))

    assert changed
    ensure.assert_awaited_once_with(db, source)
    assert db.add.call_args.args[0].source_report_submission_id == submission_id


def test_legacy_submission_materialization_uses_the_report_author(sample, monkeypatch):
    member, report, _, _ = sample
    report.status_code = "submitted"
    report.current_submission_id = None
    submission = ReportSubmission(
        id=uuid4(),
        report_id=report.id,
        revision_no=1,
        report_version=1,
        team_id=report.team_id,
        submitted_by_member_id=member.id,
        snapshot={},
        snapshot_sha256="0" * 64,
        review_status="pending",
        reviewed_by_member_id=None,
        reviewed_at=None,
        review_note=None,
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=member)
    monkeypatch.setattr(service, "_report_source_rows", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_report_deals", AsyncMock(return_value=[]))
    create = AsyncMock(return_value=submission)
    monkeypatch.setattr(service, "create_submission", create)

    result = asyncio.run(service.materialize_legacy_submission(db, report))

    assert result is submission
    assert report.current_submission_id == submission.id
    create.assert_awaited_once_with(
        db,
        report,
        member,
        [],
        submitted_by_member_id=report.author_member_id,
    )


def test_legacy_approved_materialization_requires_original_review_metadata(sample, monkeypatch):
    member, report, _, _ = sample
    report.status_code = "approved"
    report.current_submission_id = None
    report.reviewed_by_member_id = None
    report.reviewed_at = None
    submission = SimpleNamespace(id=uuid4(), review_status="pending")
    db = AsyncMock()
    db.get = AsyncMock(return_value=member)
    monkeypatch.setattr(service, "_report_source_rows", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_report_deals", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "create_submission", AsyncMock(return_value=submission))

    with pytest.raises(HTTPException) as error:
        asyncio.run(service.materialize_legacy_submission(db, report))

    assert error.value.detail == "legacy_report_review_metadata_missing"
    assert report.current_submission_id is None


def test_daily_keeps_each_common_body_linked_to_its_meeting(sample):
    _, parent, sources, _ = sample
    refs(parent, sources)
    for index, source in enumerate(sources):
        source.common_body = f"공통 일정 {index}"
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
        {"activities": []},
    ],
)
def test_no_selected_report_sources_returns_empty(sample, content):
    _, parent, _, lookup = sample
    parent.content = content
    assert run(sample) == {"reports": [], "meetings": [], "activities": []}
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
    source.body = "주간 전체 논의이며 개별 사실의 날짜는 적혀 있지 않다."
    refs(parent, [source], "주간보고서")

    result = run(sample)["reports"]

    assert len(result) == 1
    assert result[0]["report_date"] == period_start.isoformat()
    assert result[0]["period_start"] == period_start.isoformat()
    assert result[0]["period_end"] == period_end.isoformat()
    assert result[0]["values"] == {"body": source.body}


def test_conflicting_shared_copies_do_not_silently_overwrite_one_another(sample):
    _, parent, sources, _ = sample
    refs(parent, sources)
    for index, source in enumerate(sources):
        source.unassigned_body = f"미지정 {index}"
        source.content["meeting_shared"] = {"unassigned_report": {"body": f"미지정 {index}"}}
    with pytest.raises(HTTPException) as error:
        run(sample)
    assert error.value.detail == "report_source_shared_conflict"


def test_body_values_never_fall_back_to_ai_or_metadata(sample):
    _, parent, sources, _ = sample
    refs(parent, sources[:1])
    sources[0].body = "사람 검토 본문"
    sources[0].content["values"] = {
        "body": "복원하면 안 되는 구형 본문",
        "ai_values": "AI 초안",
        "transcript": "원문",
        "deal_assessment": "승리",
        "rawTranscript": "표기만 바꾼 원문",
        "AI-Values": "표기만 바꾼 초안",
    }
    assert run(sample)["reports"][0]["values"] == {"body": "사람 검토 본문"}
    sources[0].body = None
    assert run(sample)["reports"][0]["values"] == {}


def test_submission_snapshot_reads_only_the_normalized_body(sample):
    _, report, _, _ = sample
    report.report_kind = "daily"
    report.template_snapshot = {
        "id": "legacy-daily",
        "fields": [
            {"id": "summary", "label": "요약"},
            {"id": "issue", "label": "이슈"},
            {"id": "body", "label": "본문"},
        ],
    }
    report.content = {
        "summary": "레거시 요약",
        "issue": "레거시 이슈",
        "body": "레거시 실제 본문",
        "ai_values": {"summary": "보존하면 안 되는 AI 초안"},
        "transcript": "보존하면 안 되는 원문",
        "activities": [{"title": "보존하면 안 되는 메타데이터"}],
    }
    report.body = "정규 본문"

    snapshot = report_submissions.build_submission_snapshot(report, [])

    assert snapshot["structured_values"] == {}
    assert snapshot["body"] == "정규 본문"


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
    sources[0].unassigned_body = body
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
