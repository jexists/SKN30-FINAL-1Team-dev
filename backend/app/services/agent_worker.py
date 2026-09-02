"""PostgreSQL을 영속 큐로 쓰는 AgentRun worker."""

import argparse
import asyncio
import socket
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, text, update

from app.core.config import settings
from app.models.agent import AgentRun
from app.services import agent_runs
from app.services.agent_logging import agent_operation, collect_token_usage, log_agent_error
from app.services.agent_stream import progress_context

MAX_ATTEMPTS = 3
LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 30
RETRY_DELAYS_SECONDS = (5, 20)
REQUIRED_SCHEMA = {
    "agent_run": {
        "report_id",
        "request_snapshot",
        "request_hash",
        "error_code",
        "apply_status",
        "current_stage_code",
        "attempt_count",
        "base_report_version",
        "base_generation_input_version",
        "lease_owner",
        "lease_expires_at",
        "heartbeat_at",
        "next_attempt_at",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "created_at",
    },
    "report": set(),
    "report_deal": set(),
    "meeting_deal_analysis": set(),
    "report_submission": set(),
    "report_source": set(),
}


async def _fail_exhausted_leases(now: datetime) -> None:
    sessionmaker = agent_runs.get_sessionmaker()
    async with sessionmaker() as session:
        await session.execute(
            update(AgentRun)
            .where(
                AgentRun.status_code == "running",
                AgentRun.request_hash.is_not(None),
                AgentRun.lease_expires_at <= now,
                AgentRun.attempt_count >= MAX_ATTEMPTS,
            )
            .values(
                status_code="failed",
                current_stage_code="failed",
                error_code="agent_run_lease_exhausted",
                error_message="agent_run_lease_exhausted",
                lease_owner=None,
                lease_expires_at=None,
                finished_at=now,
            )
        )
        await session.commit()


async def claim(lease_owner: str, run_id: UUID | None = None) -> AgentRun | None:
    """queued 또는 lease가 만료된 실행 하나를 원자적으로 선점한다."""
    now = datetime.now(UTC)
    sessionmaker = agent_runs.get_sessionmaker()
    async with sessionmaker() as session:
        conditions = [
            AgentRun.attempt_count < MAX_ATTEMPTS,
            or_(
                and_(
                    AgentRun.status_code == "queued",
                    AgentRun.next_attempt_at <= now,
                ),
                and_(
                    AgentRun.status_code == "running",
                    AgentRun.lease_expires_at <= now,
                ),
            ),
        ]
        if run_id is not None:
            conditions.append(AgentRun.id == run_id)
        else:
            # 구 contract pipeline은 request_hash 없이 행을 만든 뒤 같은 프로세스에서
            # execute(run_id)를 직접 호출한다. 범용 worker는 새 영속 요청만 선점한다.
            conditions.append(AgentRun.request_hash.is_not(None))
        run = (
            await session.execute(
                select(AgentRun)
                .where(*conditions)
                .order_by(AgentRun.created_at.asc().nullsfirst(), AgentRun.id.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()
        if run is None:
            return None
        run.status_code = "running"
        if (
            run.agent_code == "meeting_processing"
            and run.output_snapshot
            and run.apply_status == "pending"
        ):
            run.current_stage_code = "applying"
        elif run.request_snapshot and not run.input_snapshot:
            run.current_stage_code = "building_input"
        else:
            run.current_stage_code = "running_agent"
        run.attempt_count = (run.attempt_count or 0) + 1
        run.lease_owner = lease_owner
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        run.started_at = run.started_at or now
        run.finished_at = None
        run.error_code = None
        run.error_message = None
        await session.commit()
        return run


async def _heartbeat(run_id: UUID, lease_owner: str) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        now = datetime.now(UTC)
        try:
            sessionmaker = agent_runs.get_sessionmaker()
            async with sessionmaker() as session:
                await session.execute(
                    update(AgentRun)
                    .where(
                        AgentRun.id == run_id,
                        AgentRun.status_code == "running",
                        AgentRun.lease_owner == lease_owner,
                    )
                    .values(
                        heartbeat_at=now,
                        lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
                    )
                )
                await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # 다음 heartbeat 또는 lease 복구가 처리한다. 원문/접속 문자열은 남기지 않는다.
            log_agent_error(
                error,
                stage="agent_worker.heartbeat",
                run_id=str(run_id),
                error_code="agent_heartbeat_failed",
            )


def _token_values(run: AgentRun, usage: dict[str, int] | None) -> dict[str, int]:
    if not usage or not any(usage.values()):
        return {}
    return {
        field: (getattr(run, field) or 0) + usage[field]
        for field in ("input_tokens", "output_tokens", "total_tokens")
    }


async def _complete(
    run: AgentRun, lease_owner: str, output, usage: dict[str, int] | None = None
) -> None:
    sessionmaker = agent_runs.get_sessionmaker()
    async with sessionmaker() as session:
        is_partial = run.agent_code == "meeting_processing" and bool(output.errors)
        status_code = "partial" if is_partial else "completed"
        now = datetime.now(UTC)
        values = {
            "status_code": status_code,
            "current_stage_code": status_code,
            "output_snapshot": output.model_dump(mode="json"),
            "evidence": agent_runs.evidence(run.agent_code, output, run.input_snapshot),
            "error_code": "agent_run_partial" if is_partial else None,
            "error_message": None,
            "lease_owner": None,
            "lease_expires_at": None,
            "heartbeat_at": now,
            "finished_at": now,
            **_token_values(run, usage),
        }
        result = await session.execute(
            update(AgentRun)
            .where(
                AgentRun.id == run.id,
                AgentRun.status_code == "running",
                AgentRun.lease_owner == lease_owner,
            )
            .values(**values)
        )
        if getattr(result, "rowcount", 1) == 0:
            raise RuntimeError("agent_run_lease_lost")
        await session.commit()
        for field, value in values.items():
            setattr(run, field, value)


async def _persist_meeting_output(
    run: AgentRun, lease_owner: str, output, usage: dict[str, int]
) -> bool:
    sessionmaker = agent_runs.get_sessionmaker()
    async with sessionmaker() as session:
        output_snapshot = output.model_dump(mode="json")
        run_evidence = agent_runs.evidence(run.agent_code, output, run.input_snapshot)
        result = await session.execute(
            update(AgentRun)
            .where(
                AgentRun.id == run.id,
                AgentRun.status_code == "running",
                AgentRun.lease_owner == lease_owner,
            )
            .values(
                output_snapshot=output_snapshot,
                evidence=run_evidence,
                current_stage_code="applying",
                **_token_values(run, usage),
            )
        )
        await session.commit()
        persisted = getattr(result, "rowcount", 1) != 0
        if persisted:
            run.output_snapshot = output_snapshot
            run.evidence = run_evidence
            run.current_stage_code = "applying"
            for field, value in _token_values(run, usage).items():
                setattr(run, field, value)
        return persisted


async def _apply_meeting_output(run: AgentRun, lease_owner: str, output) -> None:
    hook = getattr(agent_runs.meeting_processing, "apply_output", None)
    if hook is None:
        # 전환 중 구 코드와 함께 뜬 worker는 제안만 완료하고 기존 /apply를 남긴다.
        await _complete(run, lease_owner, output)
        return
    sessionmaker = agent_runs.get_sessionmaker()
    async with sessionmaker() as session:
        current = (
            await session.execute(
                select(AgentRun)
                .where(
                    AgentRun.id == run.id,
                    AgentRun.status_code == "running",
                    AgentRun.lease_owner == lease_owner,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if current is None:
            return
        apply_status = await hook(session, current)
        if apply_status not in {"applied", "stale"}:
            raise ValueError("meeting_apply_status_invalid")
        is_partial = bool(output.errors)
        current.status_code = "partial" if is_partial else "completed"
        current.current_stage_code = current.status_code
        current.apply_status = apply_status
        current.error_code = "agent_run_partial" if is_partial else None
        current.error_message = None
        current.lease_owner = None
        current.lease_expires_at = None
        current.heartbeat_at = datetime.now(UTC)
        current.finished_at = current.heartbeat_at
        await session.commit()


async def _fail(
    run: AgentRun,
    lease_owner: str,
    error_code: str,
    usage: dict[str, int] | None = None,
) -> None:
    sessionmaker = agent_runs.get_sessionmaker()
    async with sessionmaker() as session:
        now = datetime.now(UTC)
        # request_hash가 없는 구 system 실행은 범용 worker가 다시 선점하지 않는다.
        # 재시도 상태로 돌려놓으면 계약 pipeline이 영원히 queued에 묶인다.
        retry = (
            run.request_hash is not None
            and agent_runs.is_transient_error(error_code)
            and run.attempt_count < MAX_ATTEMPTS
        )
        values = {
            "error_code": error_code,
            "error_message": error_code,
            "lease_owner": None,
            "lease_expires_at": None,
            "heartbeat_at": now,
            **_token_values(run, usage),
        }
        if retry:
            retry_index = min(run.attempt_count - 1, len(RETRY_DELAYS_SECONDS) - 1)
            delay = RETRY_DELAYS_SECONDS[retry_index]
            values.update(
                status_code="queued",
                current_stage_code="retry_wait",
                next_attempt_at=now + timedelta(seconds=delay),
            )
        else:
            values.update(
                status_code="failed",
                current_stage_code="failed",
                finished_at=now,
            )
        await session.execute(
            update(AgentRun)
            .where(
                AgentRun.id == run.id,
                AgentRun.status_code == "running",
                AgentRun.lease_owner == lease_owner,
            )
            .values(**values)
        )
        await session.commit()
        for field, value in values.items():
            setattr(run, field, value)


async def run_claimed(run: AgentRun, lease_owner: str) -> None:
    heartbeat = asyncio.create_task(_heartbeat(run.id, lease_owner))
    usage: dict[str, int] | None = None
    usage_persisted = False
    try:
        try:
            with (
                agent_operation(
                    "agent_run",
                    run_id=str(run.id),
                    agent_code=run.agent_code,
                    model=settings.llm_model,
                    attempt=run.attempt_count,
                ),
                progress_context(run.id),
                collect_token_usage() as usage,
            ):
                if run.agent_code == "meeting_processing" and run.output_snapshot:
                    output = agent_runs.meeting_processing.MeetingProcessingOutput.model_validate(
                        run.output_snapshot
                    )
                else:
                    agent_code, input_snapshot, requester_id = await agent_runs.prepare_claimed(
                        run, lease_owner
                    )
                    output = await agent_runs.dispatch(agent_code, input_snapshot, requester_id)
                    if run.agent_code == "meeting_processing":
                        if not await _persist_meeting_output(run, lease_owner, output, usage):
                            return
                        usage_persisted = True
                if run.agent_code == "meeting_processing":
                    await _apply_meeting_output(run, lease_owner, output)
                else:
                    await _complete(run, lease_owner, output, usage)
        except Exception as error:
            error_code = agent_runs.safe_error_code(error)
            if error_code != "agent_run_lease_lost":
                log_agent_error(
                    error,
                    stage=run.agent_code,
                    run_id=str(run.id),
                    agent_code=run.agent_code,
                    attempt=run.attempt_count,
                    error_code=error_code,
                )
                await _fail(run, lease_owner, error_code, None if usage_persisted else usage)
            return
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)


async def execute(run_id: UUID) -> None:
    """기존 내부 호출 호환용. worker와 동일한 DB 선점 규칙을 사용한다."""
    lease_owner = f"direct:{uuid4()}"
    run = await claim(lease_owner, run_id)
    if run is not None:
        await run_claimed(run, lease_owner)


async def run_once(lease_owner: str) -> bool:
    await _fail_exhausted_leases(datetime.now(UTC))
    run = await claim(lease_owner)
    if run is None:
        return False
    await run_claimed(run, lease_owner)
    return True


async def run_forever(lease_owner: str, poll_seconds: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    next_cleanup = 0.0
    while True:
        if loop.time() >= next_cleanup:
            await _fail_exhausted_leases(datetime.now(UTC))
            next_cleanup = loop.time() + LEASE_SECONDS
        run = await claim(lease_owner)
        if run is None:
            await asyncio.sleep(poll_seconds)
        else:
            await run_claimed(run, lease_owner)


async def check_schema() -> None:
    """worker가 요구하는 migration이 적용됐는지 읽기 전용으로 확인한다."""
    sessionmaker = agent_runs.get_sessionmaker()
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name IN (
                        'agent_run', 'report', 'report_deal', 'meeting_deal_analysis',
                        'report_submission', 'report_source'
                      )
                    """
                )
            )
        ).all()
    actual: dict[str, set[str]] = {}
    for table_name, column_name in rows:
        actual.setdefault(table_name, set()).add(column_name)
    missing = []
    for table_name, required_columns in REQUIRED_SCHEMA.items():
        if table_name not in actual:
            missing.append(table_name)
            continue
        missing.extend(
            f"{table_name}.{column_name}"
            for column_name in sorted(required_columns - actual[table_name])
        )
    if missing:
        raise RuntimeError(f"agent_worker_schema_incomplete:{','.join(missing)}")


async def main(*, once: bool = False, poll_seconds: float = 2.0) -> None:
    """Docker image에서도 별도 worker 프로세스로 실행할 수 있는 진입점."""
    lease_owner = f"{socket.gethostname()}:{uuid4()}"
    if once:
        await run_once(lease_owner)
    else:
        await run_forever(lease_owner, poll_seconds)


def cli() -> None:
    parser = argparse.ArgumentParser(description="SalesLuv AgentRun worker")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="대기 중인 실행 하나만 처리")
    mode.add_argument(
        "--check-schema",
        action="store_true",
        help="필수 DB migration 적용 여부만 확인",
    )
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="빈 큐 조회 간격")
    args = parser.parse_args()
    if not 0.1 <= args.poll_seconds <= 60:
        parser.error("--poll-seconds must be between 0.1 and 60")
    if args.check_schema:
        asyncio.run(check_schema())
    else:
        asyncio.run(main(once=args.once, poll_seconds=args.poll_seconds))


if __name__ == "__main__":
    cli()
