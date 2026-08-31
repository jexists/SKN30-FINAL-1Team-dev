"""임시 초안은 격리하고, 재접속/완료/접근 검사는 기존 실행 하나에만 연결한다."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from test_agent_runs import _Db, _member, _Result, _run, _SessionContext

from app.api import agent_runs as api
from app.services import agent_stream as stream


def test_preview_isolated_bounded_replayed_and_replaced_not_appended():
    async def check(run_id, text):
        deal_id = str(uuid4())
        with stream.progress_context(run_id):
            stream.publish_progress(
                "report_writing",
                preview={
                    "section": "deal",
                    "sales_deal_id": deal_id,
                    "body": text,
                    "revision": 1,
                },
            )
            await asyncio.sleep(0)
            assert stream.progress_snapshot(run_id)["previews"][0]["body"] == text
            stream.publish_progress("report_review", review_attempt=2, review_limit=10)
            stream.publish_progress("analysis_complete")
            assert stream.progress_snapshot(run_id)["stage"] == "report_review"
            for revision, body in ((2, "수정"), (1, "오래된 응답"), (2, "수정 중")):
                stream.publish_progress(
                    preview={
                        "section": "deal",
                        "sales_deal_id": deal_id,
                        "body": body,
                        "revision": revision,
                    }
                )
            snapshot = stream.progress_snapshot(run_id)
            assert snapshot["previews"][0]["body"] == "수정 중"
            snapshot["previews"][0]["body"] = "외부 변경"
            assert stream.progress_snapshot(run_id)["previews"][0]["body"] == "수정 중"
            stream.publish_progress(
                preview={
                    "section": "deal",
                    "sales_deal_id": "invalid",
                    "body": "차단",
                    "revision": 3,
                }
            )
            assert len(stream.progress_snapshot(run_id)["previews"]) == 1
        assert stream.progress_snapshot(run_id) is None

    async def both():
        await asyncio.gather(check(uuid4(), "보고서A"), check(uuid4(), "보고서B"))

    asyncio.run(both())
    assert not stream._states


def test_preview_cache_has_hard_limit_and_cleanup(monkeypatch):
    monkeypatch.setattr(stream, "MAX_LIVE_PREVIEWS", 1)
    first, second = uuid4(), uuid4()
    with stream.progress_context(first):
        old_state = stream._current.get()
        stream.publish_progress(
            preview={
                "section": "common",
                "sales_deal_id": None,
                "body": "폐기할 미리보기",
                "revision": 1,
            }
        )
        with stream.progress_context(second):
            assert stream.progress_snapshot(first) is None
            assert stream.progress_snapshot(second)
            assert not old_state["previews"]
        stream.publish_progress(
            preview={
                "section": "common",
                "sales_deal_id": None,
                "body": "다시 쌓지 않음",
                "revision": 2,
            }
        )
        assert not old_state["previews"]
    assert not stream._states


def test_preview_character_cap_does_not_replace_previous_snapshot(monkeypatch):
    monkeypatch.setattr(stream, "MAX_PREVIEW_CHARACTERS", 5)
    run_id = uuid4()
    with stream.progress_context(run_id):
        for section, body in (("common", "12345"), ("unassigned", "6"), ("common", "123456")):
            stream.publish_progress(
                preview={
                    "section": section,
                    "sales_deal_id": None,
                    "body": body,
                    "revision": 1,
                }
            )
        previews = stream.progress_snapshot(run_id)["previews"]
        assert len(previews) == 1 and previews[0]["body"] == "12345"


def test_events_replay_current_preview_recheck_access_release_db_and_end(monkeypatch):
    member = _member()
    run = _run(member, status_code="running")
    initial = _Db(_Result(scalar=run))
    finished = _run(member, status_code="completed")
    finished.id = run.id
    finished.output_snapshot = {"result": "validated"}
    later = _Db(_Result(scalar=finished))
    checks = []

    async def authenticated(request, db):
        checks.append(db)
        return member

    async def connected():
        return False

    monkeypatch.setattr(api, "get_current_member", authenticated)
    monkeypatch.setattr(api, "get_sessionmaker", lambda: lambda: _SessionContext(later))
    monkeypatch.setattr(api, "RETRY_AFTER_SECONDS", 0)

    async def read():
        with stream.progress_context(run.id):
            stream.publish_progress(
                "report_review",
                review_attempt=1,
                review_limit=10,
                preview={
                    "section": "unassigned",
                    "sales_deal_id": None,
                    "body": "미지정 원문",
                    "revision": 1,
                },
            )
            response = await api.stream_agent_run(
                run.id,
                SimpleNamespace(is_disconnected=connected),
                member,
                initial,
            )
            assert initial.rollback_count == 1
            return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(read())
    assert checks == [later]
    events = [part for part in chunks if part.startswith("event:")]
    assert events[0].startswith("event: progress")
    assert "미지정 원문" in events[0]
    done = json.loads(events[-1].split("data: ", 1)[1])
    assert done["id"] == str(run.id) and done["output_snapshot"] == {"result": "validated"}
    assert initial.added == later.added == []  # 스트림은 실행/저장 작업을 시작하지 않는다.


def test_events_refuse_unknown_or_unauthorized_run_before_preview():
    async def read():
        with pytest.raises(HTTPException) as caught:
            await api.stream_agent_run(
                uuid4(), SimpleNamespace(), _member(), _Db(_Result(scalar=None))
            )
        assert caught.value.status_code == 404

    asyncio.run(read())


def test_terminal_reconnect_uses_db_without_cached_preview():
    member = _member()
    run = _run(member, status_code="failed")
    run.error_message = "report_agent_timeout"

    async def connected():
        return False

    async def read():
        response = await api.stream_agent_run(
            run.id,
            SimpleNamespace(is_disconnected=connected),
            member,
            _Db(_Result(scalar=run)),
        )
        return [chunk async for chunk in response.body_iterator]

    events = asyncio.run(read())
    assert len(events) == 1 and events[0].startswith("event: done")
    assert "report_agent_timeout" in events[0]


def test_stream_stops_when_current_access_is_revoked(monkeypatch):
    member = _member()
    run = _run(member, status_code="running")

    async def denied(request, session):
        raise HTTPException(403, "member_not_linked")

    async def connected():
        return False

    monkeypatch.setattr(api, "get_current_member", denied)
    monkeypatch.setattr(api, "get_sessionmaker", lambda: lambda: _SessionContext(_Db()))
    monkeypatch.setattr(api, "RETRY_AFTER_SECONDS", 0)

    async def read():
        response = await api.stream_agent_run(
            run.id,
            SimpleNamespace(is_disconnected=connected),
            member,
            _Db(_Result(scalar=run)),
        )
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(read())
    assert chunks[-1].startswith("event: error") and "member_not_linked" in chunks[-1]
    assert not any(chunk.startswith("event: done") for chunk in chunks)
