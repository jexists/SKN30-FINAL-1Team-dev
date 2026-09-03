"""임시 초안은 격리하고, 재접속/완료/접근 검사는 기존 실행 하나에만 연결한다."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from test_agent_runs import _Db, _member, _Result, _SessionContext
from test_agent_runs import _run as _base_run

from app.api import agent_runs as api
from app.services import agent_stream as stream


def _run(member, *, status_code):
    run = _base_run(member, status_code=status_code)
    run.scope_key = "daily:2026-08-17"
    run.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)
    return run


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
    monkeypatch.setattr(api, "RETRY_AFTER_SECONDS", 0.01)

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


@pytest.mark.parametrize("viewer", ["manager", "expired"])
def test_report_preview_is_requester_only_and_expires_before_stream(viewer):
    owner = _member()
    run = _run(owner, status_code="running")
    member = owner
    if viewer == "manager":
        member = _member(role="manager", team_id=owner.team_id)
    else:
        run.payload_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    async def read():
        with stream.progress_context(run.id):
            stream.publish_progress(
                preview={
                    "section": "common",
                    "sales_deal_id": None,
                    "body": "노출되면 안 되는 본문",
                    "revision": 1,
                }
            )
            with pytest.raises(HTTPException) as caught:
                await api.stream_agent_run(
                    run.id,
                    SimpleNamespace(),
                    member,
                    _Db(_Result(scalar=run)),
                )
            assert caught.value.status_code == 404

    asyncio.run(read())


def test_stream_stops_before_preview_when_payload_expires(monkeypatch):
    member = _member()
    run = SimpleNamespace(id=uuid4(), status_code="running")
    checks = iter((True, False))

    async def get(*_args):
        return run

    async def connected():
        return False

    monkeypatch.setattr(api.agent_run_service, "get", get)
    monkeypatch.setattr(
        api.agent_run_service,
        "generation_payload_visible",
        lambda *_args: next(checks),
    )

    async def read():
        response = await api.stream_agent_run(
            run.id,
            SimpleNamespace(is_disconnected=connected),
            member,
            _Db(),
        )
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(read())
    assert len(chunks) == 1
    assert json.loads(chunks[0].split("data: ", 1)[1]) == {"detail": "agent_run_not_found"}


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
        with stream.progress_context(run.id):
            stream.publish_progress(
                preview={
                    "section": "common",
                    "sales_deal_id": None,
                    "body": "권한 회수 뒤에는 노출 금지",
                    "revision": 1,
                }
            )
            response = await api.stream_agent_run(
                run.id,
                SimpleNamespace(is_disconnected=connected),
                member,
                _Db(_Result(scalar=run)),
            )
            return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(read())
    assert chunks[-1].startswith("event: error") and "member_not_linked" in chunks[-1]
    assert not any(chunk.startswith(("event: progress", "event: done")) for chunk in chunks)


@pytest.mark.parametrize("timed_out", [False, True], ids=["recheck-unavailable", "deadline"])
def test_stream_failure_or_deadline_ends_without_done(monkeypatch, timed_out):
    member = _member()
    run = _run(member, status_code="running")
    errors = []

    async def broken(request, session):
        raise RuntimeError("db_gone")

    async def connected():
        return False

    ticks = iter([0, 0, 25 * 60 + 1])
    monkeypatch.setattr(api, "monotonic", lambda: next(ticks) if timed_out else 0)
    monkeypatch.setattr(api, "get_current_member", broken)
    monkeypatch.setattr(api, "get_sessionmaker", lambda: lambda: _SessionContext(_Db()))
    monkeypatch.setattr(api, "RETRY_AFTER_SECONDS", 0)
    monkeypatch.setattr(
        api, "log_agent_error", lambda error, **fields: errors.append((error, fields))
    )

    async def read():
        response = await api.stream_agent_run(
            run.id,
            SimpleNamespace(is_disconnected=connected),
            member,
            _Db(_Result(scalar=run)),
        )
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(read())
    expected = "agent_stream_timeout" if timed_out else "agent_stream_unavailable"
    assert chunks[-1].startswith("event: error")
    assert json.loads(chunks[-1].split("data: ", 1)[1]) == {"detail": expected}
    assert not any(chunk.startswith("event: done") for chunk in chunks)
    if timed_out:
        assert not errors
    else:
        assert len(errors) == 1 and isinstance(errors[0][0], RuntimeError)
        assert errors[0][1] == {
            "stage": "agent_stream",
            "run_id": str(run.id),
            "error_code": expected,
        }
