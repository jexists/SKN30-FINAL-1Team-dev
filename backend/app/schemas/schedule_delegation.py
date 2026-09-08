"""Explicit, bounded tool contracts. No CRM identifiers are model-controlled."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

MAX_SEARCHES = 2
MAX_TOOL_REQUESTS = 4
MAX_MODEL_CALLS = 5


class ScheduleConstraints(BaseModel):
    """Explicit user/server constraints, never inferred from model-generated prose."""
    model_config = ConfigDict(extra="forbid")

    not_before: AwareDatetime | None = None
    not_after: AwareDatetime | None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.not_before and self.not_after and self.not_before >= self.not_after:
            raise ValueError("invalid_schedule_constraints")
        return self


class ScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_starts_at: AwareDatetime
    preferred_ends_at: AwareDatetime
    duration_minutes: int = Field(ge=5, le=480, strict=True)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def valid_window(self):
        minutes = (self.preferred_ends_at - self.preferred_starts_at).total_seconds() / 60
        if minutes < self.duration_minutes:
            raise ValueError("invalid_search_window")
        return self

    def key(self) -> str:
        # Narrative changes and equivalent timezones do not create a new search.
        value = [
            self.preferred_starts_at.astimezone(UTC).isoformat(),
            self.preferred_ends_at.astimezone(UTC).isoformat(),
            self.duration_minutes,
        ]
        return hashlib.sha256(json.dumps(value).encode()).hexdigest()


class SafeScheduleCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str = Field(min_length=1, max_length=128)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    priority: int = Field(ge=1, le=100)


class ScheduleToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["candidates_found", "no_candidates", "failed"]
    reason_code: str
    schedule_run_id: str | None = None
    schedule_candidates: list[SafeScheduleCandidate] = Field(default_factory=list)
    applied_conditions: dict = Field(default_factory=dict)


def validate_search(request: ScheduleRequest, now: datetime, constraints: dict) -> None:
    if request.preferred_starts_at <= now:
        raise ValueError("search_in_past")
    for field, actual, minimum in (
        ("not_before", request.preferred_starts_at, True),
        ("not_after", request.preferred_ends_at, False),
    ):
        if constraints.get(field):
            bound = datetime.fromisoformat(constraints[field])
            if bound.tzinfo is None:
                raise ValueError("invalid_server_constraint")
            if (minimum and actual < bound) or (not minimum and actual > bound):
                raise ValueError("schedule_constraint_violation")
    if request.preferred_ends_at - now > timedelta(days=30):
        raise ValueError("search_horizon_exceeded")
