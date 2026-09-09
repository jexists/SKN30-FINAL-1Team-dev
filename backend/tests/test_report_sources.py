"""선택한 하위 제출본의 동결·권한·기간·확정 경계를 검사한다."""

import asyncio
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.models.content import Report, ReportSource, ReportSubmission
from app.models.workspace import Member, Team
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


def run_legacy(sample):
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

    async def build_legacy():
        rows = await service._report_source_rows(SourceDb(), parent.id)
        if not rows:
            desired, _ = await service._resolve_report_source_refs(SourceDb(), member, parent)
            rows = service._source_rows(parent.id, desired)
        return await service._build_normalized_sources(
            SourceDb(), member, parent, rows, legacy=True
        )

    return asyncio.run(build_legacy())


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

    result = run_legacy(sample)

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

    result = run_legacy(sample)

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

    result = run_legacy(sample)

    assert result["reports"][0]["submission_id"] == str(submission.id)
    assert result["reports"][0]["title"] == "확정 당시 제목"
    assert result["reports"][0]["values"] == {"body": "확정 당시 딜 본문"}
    assert submission.snapshot["deals"][0]["structured_values"]["next_step"] == "견적 전달"
    assert result["meetings"][0]["common_report"] == {"body": "확정 당시 공통 내용"}
    assert "변조된 현재 초안" not in str(result)
    assert "전달하면 안 되는" not in str(result)
    lookup.assert_not_awaited()


def test_generation_freezes_exact_meeting_submission_version(sample, monkeypatch):
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
            "team_id": str(member.team_id),
            "author_member_id": str(member.id),
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
    monkeypatch.setattr(
        service,
        "_resolve_report_source_refs",
        AsyncMock(return_value=([(None, submission.id)], [])),
    )
    monkeypatch.setattr(
        service,
        "_source_submissions",
        AsyncMock(return_value={submission.id: (submission, source)}),
    )

    source.current_submission_id = submission.id
    db = AsyncMock()
    db.get.return_value = member
    sources_input, frozen_refs = asyncio.run(service.freeze_report_sources(db, member, parent))

    assert sources_input["reports"][0]["submission_id"] == str(submission.id)
    assert sources_input["reports"][0]["values"] == {"body": "생성에 사용한 제출 본문"}
    assert sources_input["activities"] == []
    assert frozen_refs == [
        {
            "position": 0,
            "source_activity_id": None,
            "source_report_submission_id": str(submission.id),
            **report_submissions.submission_ref(submission),
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

    result = run_legacy(sample)

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


def test_legacy_period_materialization_materializes_selected_submission_as_canonical_source(
    sample, monkeypatch
):
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


def test_legacy_period_materialization_rejects_a_selected_draft_as_not_finalized(
    sample, monkeypatch
):
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

    result = run_legacy(sample)

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
    assert run_legacy(sample) == {"reports": [], "meetings": [], "activities": []}
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
        run_legacy(sample)
    assert error.value.detail == detail
    lookup.assert_not_awaited()


def test_source_count_limit_is_enforced_before_loading(sample):
    _, parent, _, lookup = sample
    parent.content["activities"] = [
        {"source": "업무보고서", "included": True, "refId": str(uuid4())}
        for _ in range(service.SOURCE_REPORT_LIMIT + 1)
    ]
    with pytest.raises(HTTPException) as error:
        run_legacy(sample)
    assert error.value.detail == "report_source_limit_exceeded"
    lookup.assert_not_awaited()


def test_missing_or_unauthorized_report_fails_instead_of_returning_partial_sources(sample):
    _, parent, sources, lookup = sample
    refs(parent, sources)
    lookup.side_effect = [(sources[0], None, None), HTTPException(404, "report_not_found")]
    with pytest.raises(HTTPException) as error:
        run_legacy(sample)
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
        run_legacy(sample)
    assert error.value.detail == detail


def test_weekly_includes_submitted_daily_reports_within_period(sample):
    _, parent, sources, _ = sample
    parent.report_kind = "weekly"
    parent.period_start, parent.period_end = date(2026, 8, 16), date(2026, 8, 22)
    for source in sources:
        source.report_kind, source.status_code = "daily", "submitted"
    refs(parent, sources, "일일보고서")
    assert len(run_legacy(sample)["reports"]) == 2
    sources[0].report_date = date(2026, 8, 23)
    with pytest.raises(HTTPException) as error:
        run_legacy(sample)
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
    assert len(run_legacy(sample)["reports"]) == 1
    source.period_start, source.period_end = date(2026, 7, 19), date(2026, 7, 25)
    with pytest.raises(HTTPException) as error:
        run_legacy(sample)
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

    result = run_legacy(sample)["reports"]

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
        run_legacy(sample)
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
    assert run_legacy(sample)["reports"][0]["values"] == {"body": "사람 검토 본문"}
    sources[0].body = None
    assert run_legacy(sample)["reports"][0]["values"] == {}


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
        run_legacy(sample)
    assert error.value.detail == "report_sources_invalid"
    lookup.assert_not_awaited()


def test_shared_body_is_not_truncated_or_replaced_with_a_summary(sample):
    _, parent, sources, _ = sample
    refs(parent, sources[:1])
    body = "딜 미지정 내용 " * 10_000
    sources[0].unassigned_body = body
    sources[0].content["meeting_shared"] = {"unassigned_report": {"body": body}}
    assert run_legacy(sample)["meetings"][0]["unassigned_report"]["body"] == body


def test_invalid_parent_period_fails_when_sources_are_selected(sample):
    _, parent, sources, _ = sample
    parent.report_kind = "weekly"
    sources[0].report_kind = "daily"
    refs(parent, sources[:1], "일일보고서")
    with pytest.raises(HTTPException) as error:
        run_legacy(sample)
    assert error.value.detail == "report_source_period_invalid"


def test_cannot_generate_someone_elses_parent_report_even_as_manager(sample):
    member, parent, sources, lookup = sample
    refs(parent, sources)
    member.role_code = "manager"
    parent.author_member_id = uuid4()
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.build_report_sources(AsyncMock(), member, parent))
    assert error.value.detail == "report_not_owned"
    lookup.assert_not_awaited()


@pytest.fixture
def source_db():
    """Run real ORM queries against isolated SQLite; no production schema or sockets."""
    from sqlalchemy import (
        JSON,
        CheckConstraint,
        DefaultClause,
        ForeignKeyConstraint,
        MetaData,
        create_engine,
        event,
        text,
    )
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.orm import Session

    from app.models.agent import AgentRun
    from app.models.content import ReportActivity, ReportAttachment, ReportDeal
    from app.models.crm import Activity

    engine = create_engine(
        "sqlite://", execution_options={"schema_translate_map": {"public": None}}
    )
    metadata = MetaData()
    for model in (
        Team,
        Member,
        Report,
        ReportDeal,
        ReportSubmission,
        ReportSource,
        ReportAttachment,
        ReportActivity,
        Activity,
        AgentRun,
    ):
        table = model.__table__.to_metadata(metadata)
        for constraint in list(table.constraints):
            if isinstance(constraint, (CheckConstraint, ForeignKeyConstraint)):
                table.constraints.remove(constraint)
        table.foreign_keys.clear()
        for column in table.columns:
            column.foreign_keys.clear()
            if isinstance(column.type, JSONB):
                column.type = JSON()
            if column.server_default is not None:
                default = (
                    str(column.server_default.arg).replace("::jsonb", "").replace("::text", "")
                )
                column.server_default = DefaultClause(
                    text(default.replace("now()", "CURRENT_TIMESTAMP"))
                )
    metadata.create_all(engine)

    def restore_driver_timezone(run, context, attrs=None):
        # SQLite drops tzinfo; PostgreSQL's timestamptz driver returns aware values.
        if run.payload_expires_at is not None and run.payload_expires_at.tzinfo is None:
            run.payload_expires_at = run.payload_expires_at.replace(tzinfo=UTC)

    event.listen(AgentRun, "load", restore_driver_timezone)
    event.listen(AgentRun, "refresh", restore_driver_timezone)
    try:
        with Session(engine, expire_on_commit=False) as session:
            yield SimpleNamespace(
                session=session,
                execute=AsyncMock(side_effect=session.execute),
                flush=AsyncMock(side_effect=session.flush),
                commit=AsyncMock(side_effect=session.commit),
                rollback=AsyncMock(side_effect=session.rollback),
                get=AsyncMock(side_effect=session.get),
                add=session.add,
            )
    finally:
        event.remove(AgentRun, "load", restore_driver_timezone)
        event.remove(AgentRun, "refresh", restore_driver_timezone)
        engine.dispose()


def confirmed_meeting(db, member, *, day="2026-08-31", bodies=("확정 딜 본문",), activity_id=None):
    from test_reports import _report

    from app.models.content import ReportDeal

    report = _report(member, kind="meeting", status_code="submitted")
    report.report_date = date.fromisoformat(day)
    report.source_activity_id = activity_id or uuid4()
    report.common_body, report.unassigned_body = "공통 본문", "미귀속 본문"
    sections = [
        ReportDeal(
            report_id=report.id,
            sales_deal_id=uuid4(),
            position=index,
            deal_snapshot={},
            content={},
            body=body,
            structured_values={},
        )
        for index, body in enumerate(bodies)
    ]
    snapshot = report_submissions.build_submission_snapshot(report, sections)
    submission = ReportSubmission(
        id=uuid4(),
        report_id=report.id,
        revision_no=1,
        report_version=1,
        team_id=member.team_id,
        submitted_by_member_id=member.id,
        snapshot=snapshot,
        snapshot_sha256=report_submissions.snapshot_sha256(snapshot),
        review_status="pending",
        submitted_at=datetime(2026, 9, 2, tzinfo=UTC),
    )
    report.current_submission_id = submission.id
    db.add(report)
    db.add(submission)
    for section in sections:
        db.add(section)
    db.session.flush()
    return report, submission


def period_parent(member, kind="daily"):
    from test_reports import _report

    parent = _report(member, kind=kind)
    parent.report_date = date(2026, 8, 31)
    if kind != "daily":
        parent.period_start = date(2026, 8, 1 if kind == "monthly" else 25)
        parent.period_end = date(2026, 8, 31)
    return parent


def confirmed_child(db, member, parent_kind):
    if parent_kind == "daily":
        return confirmed_meeting(db, member)
    source = period_parent(member, service._CHILD_KIND[parent_kind])
    source.content = {"activities": []}
    source.status_code = "submitted"
    source.body = "확정 하위 본문: 8월 31일 검토, 9월 2일 후속 계획"
    # Monthly accepts a week starting in the previous month by period overlap.
    if parent_kind == "monthly":
        source.report_date = source.period_start = date(2026, 7, 27)
        source.period_end = date(2026, 8, 2)
    db.add(source)
    submission = asyncio.run(report_submissions.create_submission(db, source, member, []))
    source.current_submission_id = submission.id
    db.session.flush()
    return source, submission


def select_children(parent, children, *, submission_ids=True):
    label = next(
        label
        for label, kind in service._SOURCES.items()
        if kind == service._CHILD_KIND[parent.report_kind]
    )
    parent.content = {
        "activities": [
            {
                "source": label,
                "refId": str(child.id),
                "included": True,
                **(
                    {"sourceSubmissionId": str(child.current_submission_id)}
                    if submission_ids
                    else {}
                ),
                "desc": "navigation body spoof",
            }
            for child in children
        ]
    }


@pytest.mark.parametrize("kind", ["daily", "weekly", "monthly"])
def test_hierarchy_freezes_selected_child_body_and_excludes_other_sources(source_db, kind):
    from test_reports import _member

    from app.agents.reports import period_sources

    member = _member()
    source_db.add(member)
    child, submission = confirmed_child(source_db, member, kind)
    other, _ = confirmed_child(source_db, member, kind)
    parent = period_parent(member, kind)
    select_children(parent, [child])
    parent.content["activities"].append(
        {
            "source": parent.content["activities"][0]["source"],
            "refId": str(other.id),
            "included": False,
        }
    )
    child.body = "unsubmitted spoof"
    # Completion/submission dates and mutable draft dates never replace snapshot dates.
    child.report_date = date(2026, 9, 2)
    normalized, frozen = asyncio.run(service.freeze_report_sources(source_db, member, parent))
    assert {item["id"] for item in normalized["reports"]} == {str(child.id)}
    assert [ref["source_report_submission_id"] for ref in frozen] == [str(submission.id)]
    assert "spoof" not in str(normalized)
    snapshot = period_sources.input_snapshot(parent, None)
    snapshot["report_sources"] = normalized
    units = period_sources.source_units(period_sources.build_source(snapshot))
    assert [unit["source_type"] for unit in units] == [
        "meeting_bundle" if kind == "daily" else "child_submission"
    ]
    if kind != "daily":
        assert normalized["meetings"] == []
        assert normalized["reports"][0]["source_activity_id"] is None
    if kind == "monthly":
        assert normalized["reports"][0]["period_start"] == "2026-07-27"
        assert normalized["reports"][0]["period_end"] == "2026-08-02"


@pytest.mark.parametrize(
    "case,detail",
    [
        ("peer", "report_not_found"),
        ("other_team", "report_not_found"),
        ("inactive", "report_not_found"),
        ("admin", "report_not_found"),
        ("recipient", "report_not_found"),
        ("draft", "report_source_not_finalized"),
        ("rejected", "report_source_not_finalized"),
        ("stale_id", "report_source_submission_changed"),
        ("kind", "report_not_found"),
        ("duplicate", "report_source_duplicate"),
    ],
)
def test_selected_source_authorization_status_and_identity(source_db, case, detail):
    from test_reports import _member

    member = _member()
    owner = _member(team_id=member.team_id)
    outsider = _member()
    for row in (member, owner, outsider):
        source_db.add(row)
    if case != "peer":
        member.role_code = "manager"
    child, submission = confirmed_child(source_db, owner, "weekly")
    parent = period_parent(member, "weekly")
    select_children(parent, [child])
    if case == "other_team":
        child.team_id = outsider.team_id
    elif case == "inactive":
        owner.active = False
    elif case == "admin":
        owner.role_code = "admin"
    elif case == "recipient":
        child.recipient_member_id = outsider.id
    elif case == "draft":
        child.status_code = "draft"
    elif case == "rejected":
        submission.review_status = "changes_requested"
    elif case == "stale_id":
        parent.content["activities"][0]["sourceSubmissionId"] = str(uuid4())
    elif case == "kind":
        child.report_kind = "meeting"
    elif case == "duplicate":
        parent.content["activities"] *= 2
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.freeze_report_sources(source_db, member, parent))
    assert error.value.detail == detail


@pytest.mark.parametrize(
    "kind,day,start,end",
    [
        ("daily", "2026-09-01", None, None),
        ("weekly", "2026-09-01", None, None),
        ("monthly", "2026-07-20", "2026-07-20", "2026-07-26"),
        ("monthly", "2026-09-01", "2026-09-01", "2026-09-07"),
    ],
)
def test_selected_snapshot_outside_parent_period_is_rejected(source_db, kind, day, start, end):
    import copy

    from test_reports import _member

    member = _member()
    source_db.add(member)
    child, submission = confirmed_child(source_db, member, kind)
    snapshot = copy.deepcopy(submission.snapshot)
    snapshot.update(report_date=day, period_start=start, period_end=end)
    submission.snapshot = snapshot
    submission.snapshot_sha256 = report_submissions.snapshot_sha256(snapshot)
    parent = period_parent(member, kind)
    select_children(parent, [child])
    with pytest.raises(HTTPException, match="report_source_outside_period"):
        asyncio.run(service.freeze_report_sources(source_db, member, parent))


def test_explicit_selection_reads_beyond_first_page_and_checks_cap(source_db):
    from test_reports import _member

    member = _member()
    source_db.add(member)
    children = [confirmed_meeting(source_db, member)[0] for _ in range(101)]
    parent = period_parent(member)
    select_children(parent, children[:100])
    normalized, _ = asyncio.run(service.freeze_report_sources(source_db, member, parent))
    assert len(normalized["meetings"]) == 100
    select_children(parent, children)
    with pytest.raises(HTTPException, match="report_source_limit_exceeded"):
        asyncio.run(service.freeze_report_sources(source_db, member, parent))


def test_large_weekly_keeps_five_valid_daily_submissions_in_every_stage(source_db, monkeypatch):
    from test_period_report_writing_deep import draft
    from test_report_writing_deep import scripted
    from test_reports import _member

    from app.agents.reports import period, period_sources
    from app.schemas.reports import REPORT_BODY_MAX_LENGTH

    member = _member()
    source_db.add(member)
    children = []
    for day in range(25, 30):
        child = period_parent(member)
        child.report_date = date(2026, 8, day)
        child.status_code = "submitted"
        child.body = str(day) + "가" * (REPORT_BODY_MAX_LENGTH - 2)
        source_db.add(child)
        submission = asyncio.run(report_submissions.create_submission(source_db, child, member, []))
        child.current_submission_id = submission.id
        children.append(child)
    source_db.session.flush()
    parent = period_parent(member, "weekly")
    select_children(parent, children)
    normalized, frozen = asyncio.run(service.freeze_report_sources(source_db, member, parent))
    assert len(frozen) == 5
    snapshot = period_sources.input_snapshot(parent, None)
    snapshot["report_sources"] = normalized
    seen = scripted(monkeypatch, [draft(), {"issues": ["조건을 보존하라."]}, draft()])

    assert asyncio.run(period.run(snapshot)).model_dump() == draft()

    assert len(seen) == 3
    for index, call in enumerate(seen):
        assert len(call["input_text"]) > 180_000
        payload = json.loads(call["input_text"])
        source = payload if index == 0 else payload["source"]
        reports = [unit["content"]["reports"][0] for unit in source["source_units"]]
        assert [report["values"]["body"] for report in reports] == [
            child.body for child in children
        ]
        assert [report["submission_id"] for report in reports] == [
            str(child.current_submission_id) for child in children
        ]


@pytest.mark.parametrize(
    "mutation,detail",
    [
        ("hash", "report_source_snapshot_hash_mismatch"),
        ("duplicate_deal", "report_source_duplicate"),
        ("duplicate_submission", "report_source_duplicate"),
        ("duplicate_activity", "report_source_duplicate"),
        ("identity", "report_source_identity_invalid"),
        ("team", "report_not_found"),
        ("author", "report_not_found"),
        ("period", "report_source_outside_period"),
        ("empty_body", "report_source_content_invalid"),
        ("shared_type", "report_source_shared_invalid"),
    ],
)
def test_normalized_meeting_sources_fail_closed(source_db, mutation, detail):
    import copy

    from test_reports import _member

    member = _member()
    source_db.add(member)
    report, submission = confirmed_meeting(source_db, member)
    parent = period_parent(member)
    rows = service._source_rows(parent.id, [(None, submission.id)])
    snapshot = copy.deepcopy(submission.snapshot)
    if mutation == "hash":
        submission.snapshot_sha256 = "0" * 64
    elif mutation == "duplicate_deal":
        snapshot["deals"].append(snapshot["deals"][0])
    elif mutation == "duplicate_submission":
        rows += service._source_rows(parent.id, [(None, submission.id)])
    elif mutation == "duplicate_activity":
        _, duplicate = confirmed_meeting(source_db, member, activity_id=report.source_activity_id)
        rows += service._source_rows(parent.id, [(None, duplicate.id)])
    elif mutation == "identity":
        snapshot["source_activity_id"] = str(uuid4())
    elif mutation == "team":
        submission.team_id = uuid4()
    elif mutation == "author":
        report.author_member_id = uuid4()
    elif mutation == "period":
        snapshot["report_date"] = "2026-09-01"
    elif mutation == "empty_body":
        snapshot["deals"][0]["body"] = ""
    elif mutation == "shared_type":
        snapshot["common_body"] = {"body": "spoof"}
    if mutation not in {"hash", "team", "author"}:
        submission.snapshot = snapshot
        submission.snapshot_sha256 = report_submissions.snapshot_sha256(snapshot)
    with pytest.raises(HTTPException) as error:
        asyncio.run(service._build_normalized_sources(source_db, member, parent, rows))
    assert error.value.detail == detail


def test_daily_shared_and_no_deal_meeting_bundles_are_not_collapsed(source_db):
    from test_reports import _member

    from app.agents.reports import period_sources

    member = _member()
    source_db.add(member)
    first, _ = confirmed_meeting(source_db, member)
    second, _ = confirmed_meeting(source_db, member, bodies=())
    parent = period_parent(member)
    select_children(parent, [first, second])
    snapshot = period_sources.input_snapshot(parent, None)
    snapshot["report_sources"], _ = asyncio.run(
        service.freeze_report_sources(source_db, member, parent)
    )
    units = period_sources.source_units(period_sources.build_source(snapshot))
    assert len(units) == 2
    assert len(units[0]["content"]["deal_reports"]) == 1
    assert units[1]["content"]["deal_reports"] == []
    assert units[1]["content"]["meeting_context"][0]["common_report"] == {"body": "공통 본문"}


@pytest.mark.parametrize(
    "kind,change",
    [
        ("daily", None),
        ("weekly", None),
        ("monthly", None),
        ("weekly", "new_submission"),
        ("weekly", "review"),
        ("weekly", "deleted"),
        ("weekly", "permission"),
        ("weekly", "selection"),
        ("weekly", "stale_input"),
        ("weekly", "hash"),
        ("monthly", "old_contract"),
    ],
)
def test_generation_finalize_and_cleanup_keep_exact_provenance(
    source_db, monkeypatch, kind, change
):
    import copy
    from contextlib import asynccontextmanager

    from fastapi import BackgroundTasks, Response
    from sqlalchemy import select
    from test_report_attachment_lifecycle import attachment
    from test_report_attachment_lifecycle import original as attachment_original
    from test_report_writing_deep import scripted
    from test_reports import TEMPLATE, _member

    from app.api import reports as api
    from app.models.agent import AgentRun
    from app.schemas.agent_runs import ReportGenerationCreate
    from app.schemas.reports import ReportFinalize
    from app.services import agent_runs

    member = _member()
    source_db.add(member)
    source_db.add(Team(id=member.team_id, name="합성 팀"))
    child, original = confirmed_child(source_db, member, kind)
    parent = period_parent(member, kind)
    select_children(parent, [child])
    selected = copy.deepcopy(parent.content)
    original_snapshot = copy.deepcopy(original.snapshot)
    file = attachment_original(member)
    source_db.add(file)
    document = attachment(file, purpose="reference")
    monkeypatch.setattr(type(agent_runs.settings), "llm_configured", property(lambda self: True))
    monkeypatch.setattr(agent_runs.settings, "llm_model", "synthetic-no-model-call")
    monkeypatch.setattr(
        api, "_detail", AsyncMock(side_effect=lambda db, owner, id: db.session.get(Report, id))
    )

    @asynccontextmanager
    async def session_scope():
        yield source_db

    monkeypatch.setattr(agent_runs, "get_sessionmaker", lambda: session_scope)

    async def scenario():
        generation = ReportGenerationCreate(
            idempotency_key=uuid4(),
            report_kind=kind,
            report_date=parent.report_date,
            period_start=parent.period_start,
            period_end=parent.period_end,
            template_snapshot=TEMPLATE,
            content={**selected, "values": {"body": "기존 본문"}},
            guidance="가격 요청은 구매 확정이 아닙니다.",
            attachments=[document],
        )
        read, run_id = await agent_runs.create_report_generation(generation, member, source_db)
        run = source_db.session.get(AgentRun, run_id)
        frozen_refs = copy.deepcopy(run.source_refs)
        assert frozen_refs["report_source_contract"] == "hierarchy.v2"
        assert [ref["source_report_submission_id"] for ref in frozen_refs["report_sources"]] == [
            str(original.id)
        ]
        draft = {"fields": [{"field_id": "body", "value": "**결과**\n\n확정 하위 본문입니다."}]}
        calls = scripted(monkeypatch, [draft, {"issues": ["조건을 보존하라."]}, draft])
        prepared = await agent_runs.prepare_claimed(run, "synthetic-worker")
        output = await agent_runs.dispatch(*prepared)
        assert len(calls) == 3
        source = json.loads(calls[0]["input_text"])
        assert json.loads(calls[1]["input_text"])["source"] == source
        assert json.loads(calls[2]["input_text"])["source"] == source
        assert source["run_context"]["current_body"] == "기존 본문"
        assert "navigation body spoof" not in str(source)
        assert source["source_units"][-1]["content"]["attachment"]["extract"] == document.extract
        assert [unit["source_type"] for unit in source["source_units"]] == [
            "meeting_bundle" if kind == "daily" else "child_submission",
            "attachment",
        ]
        run.status_code, run.output_snapshot = "completed", output.model_dump()
        payload = ReportFinalize(
            idempotency_key=uuid4(),
            agent_run_id=run.id,
            report_kind=kind,
            report_date=parent.report_date,
            period_start=parent.period_start,
            period_end=parent.period_end,
            template_snapshot=TEMPLATE,
            body="사람이 교정한 최종 BODY",
            content=copy.deepcopy(selected),
            transcript=generation.guidance,
            attachments=[document],
        )
        if change == "new_submission":
            newer = await report_submissions.create_submission(source_db, child, member, [])
            child.current_submission_id = newer.id
        elif change == "review":
            original.review_status = "changes_requested"
        elif change == "deleted":
            source_db.session.delete(child)
        elif change == "permission":
            child.recipient_member_id = uuid4()
        elif change == "selection":
            payload.content["activities"] = []
        elif change == "stale_input":
            payload.content["activities"][0]["sourceSubmissionId"] = str(uuid4())
        elif change == "hash":
            original.snapshot_sha256 = "0" * 64
        elif change == "old_contract":
            run.source_refs = {**run.source_refs, "report_source_contract": "confirmed_meeting.v1"}
            with pytest.raises(ValueError, match="report_generation_source_changed"):
                await agent_runs.prepare_claimed(run, "synthetic-worker")
        await source_db.commit()
        if change is not None:
            with pytest.raises(HTTPException) as error:
                await api.finalize_report(payload, Response(), BackgroundTasks(), member, source_db)
            assert (error.value.status_code, error.value.detail) == (
                409,
                "report_generation_source_changed",
            )
            assert (
                source_db.session.scalars(select(Report).where(Report.report_kind == kind)).all()
                == []
            )
            return
        saved = await api.finalize_report(payload, Response(), BackgroundTasks(), member, source_db)
        submission = source_db.session.get(ReportSubmission, saved.current_submission_id)
        assert submission.snapshot["body"] == payload.body
        assert submission.attachments_snapshot == [document.model_dump(mode="json")]
        assert file.report_id == saved.id and file.expires_at is None
        assert file.extracted_text == "원래 추출문"
        assert submission.snapshot["source_refs"] == frozen_refs["report_sources"]
        assert run.input_snapshot == run.request_snapshot == {} and run.output_snapshot is None
        assert run.source_refs == frozen_refs
        assert original.snapshot == original_snapshot
        assert original.snapshot_sha256 == report_submissions.snapshot_sha256(original_snapshot)
        # Retry is idempotent even after the generation payload was redacted.
        again = await api.finalize_report(payload, Response(), BackgroundTasks(), member, source_db)
        assert again.current_submission_id == submission.id
        # Deleting the run leaves durable source version/hash provenance intact.
        source_db.session.delete(run)
        await source_db.commit()
        assert submission.snapshot["source_refs"] == frozen_refs["report_sources"]

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["daily", "weekly", "monthly"])
@pytest.mark.parametrize(
    "edit", ["omitted", "body_only", "replace", "clear", "revision", "wrong_id"]
)
def test_manual_new_and_edit_use_explicit_selection_changes(source_db, monkeypatch, kind, edit):
    import copy

    from fastapi import BackgroundTasks, Response
    from test_reports import TEMPLATE, _member

    from app.api import reports as api
    from app.schemas.reports import ReportFinalize

    member = _member()
    source_db.add(member)
    source_db.add(Team(id=member.team_id, name="합성 팀"))
    child, original = confirmed_child(source_db, member, kind)
    other, other_submission = confirmed_child(source_db, member, kind)
    parent = period_parent(member, kind)
    select_children(parent, [child])
    content = copy.deepcopy(parent.content)
    monkeypatch.setattr(
        api, "_detail", AsyncMock(side_effect=lambda db, owner, id: db.session.get(Report, id))
    )

    async def scenario():
        payload = ReportFinalize(
            idempotency_key=uuid4(),
            report_kind=kind,
            report_date=parent.report_date,
            period_start=parent.period_start,
            period_end=parent.period_end,
            template_snapshot=TEMPLATE,
            body="수동 신규 본문",
            content=content,
        )
        saved = await api.finalize_report(payload, Response(), BackgroundTasks(), member, source_db)
        first = source_db.session.get(ReportSubmission, saved.current_submission_id)
        old_snapshot, old_hash = copy.deepcopy(first.snapshot), first.snapshot_sha256
        assert first.snapshot["source_refs"][0]["source_report_submission_id"] == str(original.id)
        sections = await service._report_deals(source_db, child.id)
        newer = await report_submissions.create_submission(source_db, child, member, sections)
        child.current_submission_id = newer.id
        await source_db.commit()
        changed_content = copy.deepcopy(content)
        expected_id = original.id
        if edit == "omitted":
            changed_content = {}
        elif edit == "body_only":
            changed_content["activities"][0]["desc"] = "본문 밖 표시값 수정"
        elif edit == "replace":
            select_children(parent, [other])
            changed_content = parent.content
            expected_id = other_submission.id
        elif edit == "clear":
            changed_content = {"activities": []}
        elif edit in {"revision", "wrong_id"}:
            changed_content["activities"][0]["sourceSubmissionId"] = str(
                newer.id if edit == "revision" else uuid4()
            )
            expected_id = newer.id
        revised = payload.model_copy(
            update={
                "idempotency_key": uuid4(),
                "report_id": saved.id,
                "expected_version": saved.version,
                "expected_status_code": "submitted",
                "body": "수동 수정 본문",
                "content": changed_content,
            }
        )
        if edit == "wrong_id":
            with pytest.raises(HTTPException, match="report_source_submission_changed"):
                await api.finalize_report(revised, Response(), BackgroundTasks(), member, source_db)
            assert source_db.session.get(Report, saved.id).current_submission_id == first.id
            return
        saved = await api.finalize_report(revised, Response(), BackgroundTasks(), member, source_db)
        revision = source_db.session.get(ReportSubmission, saved.current_submission_id)
        assert revision.revision_no == 2 and revision.snapshot["body"] == "수동 수정 본문"
        expected = [] if edit == "clear" else [str(expected_id)]
        assert [
            ref["source_report_submission_id"] for ref in revision.snapshot["source_refs"]
        ] == expected
        assert first.snapshot == old_snapshot and first.snapshot_sha256 == old_hash
        if edit == "omitted":
            assert saved.content["activities"] == content["activities"]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "field,value,detail",
    [
        ("active", False, "member_not_allowed"),
        ("role_code", "admin", "member_not_allowed"),
        ("team_id", uuid4(), "report_not_found"),
        ("id", uuid4(), "report_not_owned"),
    ],
)
def test_selected_source_query_checks_requester_before_access(source_db, field, value, detail):
    from test_reports import _member

    member = _member()
    parent = period_parent(member)
    setattr(member, field, value)
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.freeze_report_sources(source_db, member, parent))
    assert error.value.detail == detail
    source_db.execute.assert_not_awaited()


@pytest.mark.parametrize(
    "fault,detail",
    [
        (None, None),
        ("owner", "activity_not_found"),
        ("day", "report_source_outside_period"),
        ("deleted", "activity_not_found"),
    ],
)
def test_daily_calendar_freeze_uses_validated_database_values(source_db, fault, detail):
    from test_reports import _activity, _member

    from app.agents.reports import period_sources

    member = _member()
    source_db.add(member)
    activity = _activity(member)
    activity.customer_contact_id = uuid4()
    activity.customer_company_id = uuid4()
    activity.starts_at = datetime(2026, 8, 31, 1, tzinfo=UTC)
    activity.note = "검증된 활동 기록"
    source_db.add(activity)
    parent = period_parent(member)
    parent.content = {
        "activities": [
            {
                "source": "캘린더",
                "included": True,
                "refId": str(activity.id),
                "desc": "화면 위조 값",
            }
        ]
    }
    if fault == "owner":
        activity.owner_member_id = uuid4()
    elif fault == "day":
        activity.starts_at = datetime(2026, 9, 1, 1, tzinfo=UTC)
    elif fault == "deleted":
        activity.deleted_at = datetime.now(UTC)
    if detail:
        with pytest.raises(HTTPException, match=detail):
            asyncio.run(service.freeze_report_sources(source_db, member, parent))
        return
    normalized, frozen = asyncio.run(service.freeze_report_sources(source_db, member, parent))
    assert frozen == [
        {"position": 0, "source_activity_id": str(activity.id), "source_report_submission_id": None}
    ]
    snapshot = period_sources.input_snapshot(parent, None)
    snapshot["report_sources"] = normalized
    units = period_sources.source_units(period_sources.build_source(snapshot))
    assert units[0]["source_type"] == "direct_activity"
    assert "검증된 활동 기록" in str(units) and "화면 위조 값" not in str(units)
