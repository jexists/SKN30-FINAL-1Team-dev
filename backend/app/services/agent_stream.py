"""실행 중인 보고서의 최신 미검증 미리보기. 최종 결과의 기준은 AgentRun DB다."""

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from uuid import UUID

# ponytail: 기존 실행기와 같은 단일 worker의 임시 미리보기다. 다중 worker에서는
# 공유 pub/sub로 교체한다. 캐시를 못 찾으면 클라이언트는 DB 완료 상태만 기다린다.
_states: OrderedDict[str, dict[str, Any]] = OrderedDict()
_current: ContextVar[dict[str, Any] | None] = ContextVar("agent_progress", default=None)
MAX_LIVE_PREVIEWS = 32
MAX_PREVIEW_SECTIONS = 102  # 선택 딜 최대 100개 + 공통 + 미지정
MAX_PREVIEW_CHARACTERS = 500_000
_STAGES = {
    "starting",
    "content_analysis",
    "report_writing",
    "report_review",
    "report_complete",
    "features",
    "analysis_complete",
}


@contextmanager
def progress_context(run_id: UUID):
    key = str(run_id)
    state: dict[str, Any] = {"run_id": key, "stage": "starting", "previews": {}, "sequence": 0}
    _states[key] = state
    while len(_states) > MAX_LIVE_PREVIEWS:
        _, evicted = _states.popitem(last=False)
        evicted["previews"].clear()
    token = _current.set(state)
    try:
        yield
    finally:
        _current.reset(token)
        if _states.get(key) is state:
            _states.pop(key)


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
    if preview is not None:
        section = preview.get("section")
        deal_id = preview.get("sales_deal_id")
        body, revision = preview.get("body"), preview.get("revision")
        if section not in {"deal", "common", "unassigned"}:
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
            or len(body) > 100_000
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
        state["previews"][key] = {
            "section": section,
            "sales_deal_id": deal_id,
            "body": body,
            "revision": revision,
        }
    state["sequence"] += 1


def progress_snapshot(run_id: UUID) -> dict[str, Any] | None:
    state = _states.get(str(run_id))
    if state is None:
        return None
    return {**state, "previews": [dict(item) for item in state["previews"].values()]}
