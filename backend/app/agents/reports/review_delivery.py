"""보고서 공개 반환값을 바꾸지 않고 worker에 검토 메타데이터를 전달한다."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from app.agents.reports.harness import WorkflowResult

_capture: ContextVar[dict | None] = ContextVar("report_review_delivery", default=None)


@contextmanager
def capture() -> Iterator[dict]:
    value: dict = {}
    token = _capture.set(value)
    try:
        yield value
    finally:
        _capture.reset(token)


def record(result: WorkflowResult) -> None:
    target = _capture.get()
    if target is not None:
        target["report_review"] = {
            "selected_version": result.selected_version,
            "initial_review_conducted": result.initial_review_conducted,
            "repair_completed": result.repair_completed,
            "review_required": result.review_incomplete,
            "review_incomplete": result.review_incomplete,
            "review_notes_may_predate_draft": bool(result.review_issues)
            and result.selected_version == 2,
            "issues": [issue.model_dump(mode="json") for issue in result.review_issues],
        }
