"""실행 중인 보고서의 최신 미검증 미리보기. 최종 결과의 기준은 AgentRun DB다."""

import asyncio
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from app.schemas.reports import REPORT_BODY_MAX_LENGTH
from app.services.agent_logging import log_agent_error

# ponytail: DB snapshot이 worker/API 프로세스를 잇고, 이 cache는 같은 프로세스의 빠른 경로다.
_states: OrderedDict[str, dict[str, Any]] = OrderedDict()
_current: ContextVar[dict[str, Any] | None] = ContextVar("agent_progress", default=None)
MAX_LIVE_PREVIEWS = 32
MAX_PREVIEW_SECTIONS = 102  # 선택 딜 최대 100개 + 공통 + 미지정
MAX_PREVIEW_CHARACTERS = 500_000
MAX_STAGE_RESULTS = 64
MAX_STAGE_RESULT_CHARACTERS = 12_000
_STAGES = {
    "starting",
    "content_analysis",
    "report_writing",
    "report_preparing",
    "report_revising",
    "report_review",
    "report_complete",
    "features",
    "analysis_complete",
}


@contextmanager
def progress_context(
    run_id: UUID, *, lease_owner: str | None = None, attempt_count: int | None = None
):
    key = str(run_id)
    state: dict[str, Any] = {
        "run_id": key,
        "stage": "starting",
        "previews": {},
        "confirmed_previews": {},
        "stage_results": {},
        "sequence": 0,
        "lease_owner": lease_owner,
        "attempt_count": attempt_count,
        "persist_task": None,
    }
    _states[key] = state
    while len(_states) > MAX_LIVE_PREVIEWS:
        _, evicted = _states.popitem(last=False)
        evicted["previews"].clear()
        evicted["confirmed_previews"].clear()
        evicted["stage_results"].clear()
    token = _current.set(state)
    try:
        yield
    finally:
        task = state.get("persist_task")
        if task is not None and not task.done():
            task.cancel()
        _current.reset(token)
        if _states.get(key) is state:
            _states.pop(key)


def _db_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": state["run_id"],
        "stage": state["stage"],
        "previews": [dict(item) for item in state["previews"].values()],
        "confirmed_previews": [dict(item) for item in state["confirmed_previews"].values()],
        "stage_results": [dict(item) for item in state["stage_results"].values()],
        "sequence": state["sequence"],
        "attempt_count": state["attempt_count"],
        **{
            key: state[key]
            for key in (
                "report_kind",
                "phase_counts",
                "recovery_reason",
                "review_attempt",
                "review_limit",
            )
            if key in state
        },
    }


async def _persist_state(state: dict[str, Any]) -> None:
    try:
        from sqlalchemy import update

        from app.db.session import get_sessionmaker
        from app.models.agent import AgentRun

        async with get_sessionmaker()() as session:
            result = await session.execute(
                update(AgentRun)
                .where(
                    AgentRun.id == UUID(state["run_id"]),
                    AgentRun.status_code == "running",
                    AgentRun.lease_owner == state["lease_owner"],
                    AgentRun.attempt_count == state["attempt_count"],
                )
                .values(progress_snapshot=_db_snapshot(state))
            )
            await session.commit()
            if result.rowcount == 0:
                return
    except Exception as error:
        log_agent_error(
            error,
            stage="agent_stream.persist",
            run_id=state["run_id"],
            error_code="progress_snapshot_unavailable",
        )


async def _persist_later(state: dict[str, Any]) -> None:
    await asyncio.sleep(0.25)
    await _persist_state(state)


def _schedule_persist(state: dict[str, Any]) -> None:
    if state["lease_owner"] is None:
        return
    task = state.get("persist_task")
    if task is None or task.done():
        state["persist_task"] = asyncio.create_task(_persist_later(state))


async def flush_progress_snapshot(run_id: UUID) -> None:
    state = _states.get(str(run_id))
    if state is None or state["lease_owner"] is None:
        return
    task = state.get("persist_task")
    if task is not None and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    state["persist_task"] = None
    await _persist_state(state)


def publish_progress(stage: str | None = None, *, preview: dict | None = None, **metrics):
    """토큰 콜백에서 호출한다. 원문/추론/도구 인수를 그대로 이벤트로 전달하지 않는다."""
    state = _current.get()
    if state is None or _states.get(state["run_id"]) is not state:
        return
    if stage in _STAGES:
        # 병렬 ML 완료 때문에 현재 보고서 검토 단계가 덮어써지지 않게 한다.
        if stage not in {"features", "analysis_complete"} or state["stage"] in {
            "starting",
            "content_analysis",
            "features",
        }:
            state["stage"] = stage
    for key in ("review_attempt", "review_limit"):
        value = metrics.get(key)
        if type(value) is int and 0 <= value <= 100:
            state[key] = value
    recovery_reason = metrics.get("recovery_reason")
    if recovery_reason in {"original_source_fallback", "valid_draft_fallback"}:
        state["recovery_reason"] = recovery_reason
    if isinstance(metrics.get("report_kind"), str):
        state["report_kind"] = metrics["report_kind"]
    if "phase_counts" in metrics and isinstance(metrics["phase_counts"], dict):
        state["phase_counts"] = dict(metrics["phase_counts"])
    if preview is not None:
        section = preview.get("section")
        deal_id = preview.get("sales_deal_id")
        body, revision = preview.get("body"), preview.get("revision")
        if section not in {"deal", "common", "unassigned", "body"}:
            return
        if section == "deal":
            try:
                deal_id = str(UUID(str(deal_id)))
            except ValueError:
                return
        elif deal_id is not None:
            return
        if (
            not isinstance(body, str)
            or len(body) > REPORT_BODY_MAX_LENGTH
            or type(revision) is not int
            or revision < 0
        ):
            return
        key = (section, deal_id)
        prior = state["previews"].get(key)
        if prior is not None and revision < prior["revision"]:
            return
        if prior is None and len(state["previews"]) >= MAX_PREVIEW_SECTIONS:
            return
        size = sum(len(item["body"]) for item in state["previews"].values())
        if size - len(prior["body"] if prior else "") + len(body) > MAX_PREVIEW_CHARACTERS:
            return  # 화면용 캐시 상한이다. 실제 생성·최종 결과는 자르지 않는다.
        item = {
            "section": section,
            "sales_deal_id": deal_id,
            "body": body,
            "revision": revision,
            **{
                field: preview[field]
                for field in ("phase", "draft_version", "preview_state")
                if field in preview
            },
        }
        state["previews"][key] = item
        if item.get("preview_state") == "confirmed":
            state["confirmed_previews"][key] = dict(item)
    state["sequence"] += 1
    _schedule_persist(state)


def publish_stream_preview(
    *,
    section: str,
    sales_deal_id: str | None,
    body: str,
    phase: str,
    draft_version: int,
    preview_state: str = "streaming",
) -> None:
    """Publish streaming or confirmed body through the single revision allocator."""
    state = _current.get()
    if state is None or _states.get(state["run_id"]) is not state:
        return
    if not isinstance(body, str) or not body.strip():
        return
    if section == "deal":
        try:
            sales_deal_id = str(UUID(str(sales_deal_id)))
        except (TypeError, ValueError):
            return
    elif sales_deal_id is not None:
        return
    key = (section, sales_deal_id)
    prior = state["previews"].get(key)
    if prior is not None and draft_version < prior.get("draft_version", 0):
        return
    if (
        prior is not None
        and prior.get("preview_state") == "confirmed"
        and preview_state == "streaming"
        and draft_version <= prior.get("draft_version", 0)
    ):
        return
    revision = (prior["revision"] if prior else 0) + 1
    publish_progress(
        preview={
            "section": section,
            "sales_deal_id": sales_deal_id,
            "body": body,
            "revision": revision,
            "phase": phase,
            "draft_version": draft_version,
            "preview_state": preview_state,
        }
    )


def publish_stage_result(
    *, stage: str, key: str, body: str, preview_state: str = "streaming"
) -> None:
    """Publish bounded user-facing prepare/review output separately from body previews."""
    state = _current.get()
    if state is None or _states.get(state["run_id"]) is not state:
        return
    if (
        stage not in {"prepare", "review_initial", "content_analysis", "repair"}
        or not key
        or not isinstance(body, str)
    ):
        return
    body = body.strip()
    if not body or len(body) > 320:
        return
    public_key = f"{stage}:{key}"
    item = state["stage_results"].get(public_key)
    if item is not None and item.get("body") == body and item.get("preview_state") == preview_state:
        return
    if item is None and len(state["stage_results"]) >= MAX_STAGE_RESULTS:
        return
    total = sum(len(value["body"]) for value in state["stage_results"].values())
    if total - len(item["body"] if item else "") + len(body) > MAX_STAGE_RESULT_CHARACTERS:
        return
    if (
        item is not None
        and item.get("preview_state") == "confirmed"
        and preview_state == "streaming"
    ):
        return
    state["stage_results"][public_key] = {
        "stage": stage,
        "key": public_key,
        "body": body,
        "preview_state": preview_state,
    }
    state["sequence"] += 1
    _schedule_persist(state)


def progress_snapshot(run_id: UUID) -> dict[str, Any] | None:
    state = _states.get(str(run_id))
    if state is None:
        return None
    return _db_snapshot(state)
