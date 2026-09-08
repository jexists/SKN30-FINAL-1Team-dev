"""Opt-in, allowlisted LangSmith spans; CRM payloads never enter the client."""

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import lru_cache

from langsmith import Client
from langsmith.run_trees import RunTree

from app.core.config import settings

_parent: ContextVar[RunTree | None] = ContextVar("contract_trace", default=None)
_ALLOWED = frozenset(
    {
        "run_id",
        "parent_run_id",
        "attempt",
        "model_call_count",
        "tool_call_count",
        "search_count",
        "status",
        "reason_code",
        "candidate_count",
        "reused",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_version",
        "action",
        "search_starts_at",
        "search_ends_at",
        "duration_minutes",
        "constraint_basis",
    }
)


def safe_fields(values: dict) -> dict:
    return {
        k: v for k, v in values.items() if k in _ALLOWED and isinstance(v, (str, int, float, bool))
    }


@lru_cache(maxsize=1)
def _client() -> Client:
    return Client(
        api_key=settings.langsmith_api_key.get_secret_value(),
        api_url=settings.langsmith_endpoint,
        hide_inputs=True,
        hide_outputs=True,
        omit_traced_runtime_info=True,
        timeout_ms=1500,
    )


@asynccontextmanager
async def span(name: str, **metadata):
    """Only our explicit safe metadata is sent, including on exception paths."""
    result = {}
    tree = None
    token = None
    if settings.contract_langsmith_enabled and settings.langsmith_api_key.get_secret_value():
        try:
            parent = _parent.get()
            if parent is None:
                tree = RunTree(
                    name=name,
                    run_type="chain",
                    inputs={},
                    extra={"metadata": safe_fields(metadata)},
                    project_name=settings.langsmith_project,
                    client=_client(),
                )
            else:
                tree = parent.create_child(
                    name=name,
                    run_type="chain",
                    inputs={},
                    extra={"metadata": safe_fields(metadata)},
                )
            await asyncio.to_thread(tree.post)
            token = _parent.set(tree)
        except Exception:
            tree = None
    try:
        yield result
    except BaseException:
        result["status"] = "failed"
        # Never serialize exception messages or model/provider responses.
        raise
    finally:
        if token is not None:
            _parent.reset(token)
        if tree is not None:
            try:
                tree.add_metadata(safe_fields(result))
                tree.end(outputs={})
                await asyncio.to_thread(tree.patch)
            except Exception:
                pass
