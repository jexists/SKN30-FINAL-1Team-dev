"""PostgreSQL을 영속 큐로 쓰는 AgentRun worker."""

import argparse
import asyncio
import copy
import hashlib
import json
import socket
from datetime import UTC, datetime, timedelta
from typing import get_args
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.agent import AgentRun
from app.models.content import Report, ReportDeal
from app.schemas.agent_runs import AgentCode
from app.services import agent_runs
from app.services.agent_logging import agent_operation, collect_token_usage, log_agent_error
from app.services.agent_stream import progress_context

MAX_ATTEMPTS = 2
LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 30
RETRY_DELAY_SECONDS = 5
REQUIRED_SCHEMA = {
    "agent_run": {
        "report_id",
        "request_snapshot",
        "request_hash",
        "scope_key",
        "error_code",
        "current_stage_code",
        "attempt_count",
        "payload_expires_at",
        "payload_redacted_at",
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
    "report_submission": {"agent_run_id", "idempotency_key", "request_hash"},
    "report_source": set(),
}


def _runnable_conditions(now: datetime):
    return (
        AgentRun.agent_code.in_(get_args(AgentCode)),
        or_(
            AgentRun.agent_code.not_in(agent_runs.REPORT_GENERATION_CODES),
            and_(
                AgentRun.payload_redacted_at.is_(None),
                AgentRun.payload_expires_at > now,
            ),
        ),
    )


async def _fail_exhausted_leases(now: datetime) -> None:
    sessionmaker = agent_runs.get_sessionmaker()
    async with sessionmaker() as session:
        await session.execute(
            update(AgentRun)
            .where(
                *_runnable_conditions(now),
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
            *_runnable_conditions(now),
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
        if run.request_snapshot and not run.input_snapshot:
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


def _expired_payload_values(now: datetime) -> dict[str, object]:
    return {
        "status_code": "cancelled",
        "current_stage_code": "cancelled",
        "request_snapshot": {},
        "input_snapshot": {},
        "output_snapshot": None,
        "evidence": None,
        "error_code": "agent_run_payload_expired",
        "error_message": "agent_run_payload_expired",
        "payload_expires_at": None,
        "payload_redacted_at": now,
        "lease_owner": None,
        "lease_expires_at": None,
        "heartbeat_at": now,
        "finished_at": now,
    }


async def _redact_expired_claim(
    session: AsyncSession, run: AgentRun, lease_owner: str, now: datetime
) -> bool:
    result = await session.execute(
        update(AgentRun)
        .where(
            AgentRun.id == run.id,
            AgentRun.status_code == "running",
            AgentRun.lease_owner == lease_owner,
            AgentRun.agent_code.in_(agent_runs.REPORT_GENERATION_CODES),
            AgentRun.payload_redacted_at.is_(None),
            or_(
                AgentRun.payload_expires_at.is_(None),
                AgentRun.payload_expires_at <= now,
            ),
        )
        .values(**_expired_payload_values(now))
    )
    return getattr(result, "rowcount", 1) > 0


async def _complete(
    run: AgentRun, lease_owner: str, output, usage: dict[str, int] | None = None
) -> None:
    sessionmaker = agent_runs.get_sessionmaker()
    async with sessionmaker() as session:
        is_partial = run.agent_code == "meeting_analysis" and any(item.error for item in output)
        status_code = "partial" if is_partial else "completed"
        now = datetime.now(UTC)
        parent = None
        if run.agent_code == "meeting_analysis" and run.parent_run_id is not None:
            # Every split child lifecycle takes the parent lock before its own row.  Finalize
            # uses the same order, so late analysis cannot race a report generation switch.
            parent = (
                await session.execute(
                    select(AgentRun)
                    .where(AgentRun.id == run.parent_run_id)
                    .with_for_update(of=AgentRun)
                )
            ).scalar_one_or_none()
        output_snapshot = (
            output.model_dump(mode="json")
            if hasattr(output, "model_dump")
            else [item.model_dump(mode="json") for item in output]
        )
        if run.agent_code == "meeting_analysis":
            output_snapshot = {"analyses": output_snapshot}
        values = {
            "status_code": status_code,
            "current_stage_code": status_code,
            "output_snapshot": output_snapshot,
            "evidence": agent_runs.evidence(run.agent_code, output, run.input_snapshot),
            "error_code": "agent_run_partial" if is_partial else None,
            "error_message": None,
            "lease_owner": None,
            "lease_expires_at": None,
            "heartbeat_at": now,
            "finished_at": now,
            **_token_values(run, usage),
        }
        conditions = [
            AgentRun.id == run.id,
            AgentRun.status_code == "running",
            AgentRun.lease_owner == lease_owner,
        ]
        if run.agent_code in agent_runs.REPORT_GENERATION_CODES:
            conditions.extend(
                (
                    AgentRun.payload_redacted_at.is_(None),
                    AgentRun.payload_expires_at > now,
                )
            )
        result = await session.execute(update(AgentRun).where(*conditions).values(**values))
        if getattr(result, "rowcount", 1) == 0:
            if await _redact_expired_claim(session, run, lease_owner, now):
                await session.commit()
                for field, value in _expired_payload_values(now).items():
                    setattr(run, field, value)
                return
            raise RuntimeError("agent_run_lease_lost")
        if run.agent_code == "meeting_processing" and status_code == "completed":
            await _enqueue_meeting_children(session, run, output)
        if run.agent_code == "meeting_analysis" and status_code in {"completed", "partial"}:
            await _persist_late_meeting_analysis(session, run, output, parent=parent)
        await session.commit()
        for field, value in values.items():
            setattr(run, field, value)


async def _enqueue_meeting_children(session: AsyncSession, parent: AgentRun, output) -> None:
    """근거가 확정된 뒤 보고서와 ML을 각각 독립 큐 작업으로 만든다."""
    evidence_snapshot = {
        "source": parent.input_snapshot.get("source", {}),
        "deals": parent.input_snapshot.get("deals", []),
        "evidence": output.evidence.model_dump(mode="json"),
        "crm_context": output.crm_context,
    }
    report_attachments = [
        copy.deepcopy(item)
        for item in parent.input_snapshot.get("attachments", [])
        if isinstance(item, dict) and item.get("kind") != "audio"
    ]
    existing = {
        row.agent_code
        for row in (
            await session.execute(select(AgentRun).where(AgentRun.parent_run_id == parent.id))
        )
        .scalars()
        .all()
    }
    children = (("meeting_report_writing", "report"), ("meeting_analysis", "analysis"))
    for code, suffix in children:
        if code in existing:
            continue
        child_snapshot = copy.deepcopy(evidence_snapshot)
        if code == "meeting_report_writing" and report_attachments:
            child_snapshot["attachments"] = report_attachments
        child_id = uuid4()
        request_snapshot = {"parent_run_id": str(parent.id), "kind": suffix}
        request_hash = hashlib.sha256(
            json.dumps(
                child_snapshot,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        session.add(
            AgentRun(
                id=child_id,
                team_id=parent.team_id,
                parent_run_id=parent.id,
                requested_by_member_id=parent.requested_by_member_id,
                agent_code=code,
                trigger_code="meeting_processing",
                idempotency_key=child_id,
                report_id=None,
                status_code="queued",
                llm_model_name=parent.llm_model_name,
                prompt_version=agent_runs._prompt_version(code),
                request_snapshot=request_snapshot,
                request_hash=request_hash,
                scope_key=f"{code}:{parent.source_refs.get('source_activity_id')}",
                source_refs={
                    **parent.source_refs,
                    "parent_run_id": str(parent.id),
                    "evidence_transcript_sha256": output.evidence.transcript_sha256,
                },
                input_snapshot=child_snapshot,
                output_snapshot=None,
                evidence=None,
                error_message=None,
                error_code=None,
                current_stage_code="queued",
                attempt_count=0,
                payload_expires_at=parent.payload_expires_at,
                payload_redacted_at=None,
                lease_owner=None,
                lease_expires_at=None,
                heartbeat_at=None,
                next_attempt_at=datetime.now(UTC),
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                created_at=datetime.now(UTC),
                started_at=None,
                finished_at=None,
            )
        )


async def _persist_late_meeting_analysis(
    session: AsyncSession,
    run: AgentRun,
    output,
    *,
    parent: AgentRun | None = None,
    failure_code: str | None = None,
) -> None:
    """확정 보고서가 먼저 저장돼도 같은 보고서 세대의 분석 결과만 보강한다."""
    if run.parent_run_id is None:
        return
    if parent is None:
        parent = (
            await session.execute(
                select(AgentRun)
                .where(AgentRun.id == run.parent_run_id)
                .with_for_update(of=AgentRun)
            )
        ).scalar_one_or_none()
    if parent is None or parent.report_id is None:
        return
    report = (
        await session.execute(select(Report).where(Report.id == parent.report_id))
    ).scalar_one_or_none()
    if report is None:
        return
    source_snapshot = report.source_snapshot if isinstance(report.source_snapshot, dict) else {}
    report_child_id = source_snapshot.get("agent_run_id")
    if not report_child_id:
        return
    try:
        report_child_uuid = UUID(str(report_child_id))
    except (TypeError, ValueError):
        return
    report_child = (
        await session.execute(
            select(AgentRun)
            .where(
                AgentRun.id == report_child_uuid,
                AgentRun.report_id == report.id,
                AgentRun.agent_code == "meeting_report_writing",
            )
            .with_for_update(of=AgentRun)
        )
    ).scalar_one_or_none()
    if (
        report_child is None
        or report_child.parent_run_id != run.parent_run_id
        or (report_child.source_refs or {}).get("parent_run_id") != str(run.parent_run_id)
    ):
        return
    report = (
        await session.execute(
            select(Report)
            .where(Report.id == parent.report_id)
            .execution_options(populate_existing=True)
            .with_for_update(of=Report)
        )
    ).scalar_one_or_none()
    if report is None:
        return
    source_snapshot = report.source_snapshot if isinstance(report.source_snapshot, dict) else {}
    if source_snapshot.get("agent_run_id") != str(report_child.id):
        return
    source_generation = source_snapshot.get("generation_input_version")
    if source_generation is not None and source_generation != getattr(
        report, "generation_input_version", None
    ):
        return
    rows = (
        (
            await session.execute(
                select(ReportDeal).where(ReportDeal.report_id == report.id).with_for_update()
            )
        )
        .scalars()
        .all()
    )
    raw_items = output.get("analyses", []) if isinstance(output, dict) else output
    by_deal = {}
    for item in raw_items or []:
        sales_deal_id = item.get("sales_deal_id") if isinstance(item, dict) else item.sales_deal_id
        if sales_deal_id is not None:
            by_deal[UUID(str(sales_deal_id))] = item
    for row in rows:
        item = by_deal.get(row.sales_deal_id)
        if isinstance(item, dict):
            error = item.get("error")
            assessment = item.get("assessment")
            features = item.get("features")
        elif item is None:
            error = failure_code
            assessment = None
            features = None
        else:
            error = item.error
            assessment = item.assessment.model_dump(mode="json") if item.assessment else None
            features = item.features.model_dump(mode="json") if item.features else None
        row.ai_evidence = {
            "meeting_run_id": str(run.id),
            "analysis_run_id": str(run.id),
            "analysis_status": (
                "failed" if error else ("pending" if item is None else "completed")
            ),
            "deal_assessment": assessment,
            "features": features,
            "analysis_error": error,
            "report_error": None,
        }


async def _fail(
    run: AgentRun,
    lease_owner: str,
    error_code: str,
    usage: dict[str, int] | None = None,
) -> None:
    sessionmaker = agent_runs.get_sessionmaker()
    async with sessionmaker() as session:
        now = datetime.now(UTC)
        parent = None
        if run.agent_code == "meeting_analysis" and run.parent_run_id is not None:
            parent = (
                await session.execute(
                    select(AgentRun)
                    .where(AgentRun.id == run.parent_run_id)
                    .with_for_update(of=AgentRun)
                )
            ).scalar_one_or_none()
        if run.agent_code in agent_runs.REPORT_GENERATION_CODES and (
            run.payload_expires_at is None or run.payload_expires_at <= now
        ):
            values = _expired_payload_values(now)
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
            return
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
            values.update(
                status_code="queued",
                current_stage_code="retry_wait",
                next_attempt_at=now + timedelta(seconds=RETRY_DELAY_SECONDS),
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
        if values.get("status_code") == "failed" and run.agent_code == "meeting_analysis":
            await _persist_late_meeting_analysis(
                session,
                run,
                [],
                parent=parent,
                failure_code=error_code,
            )
        await session.commit()
        for field, value in values.items():
            setattr(run, field, value)


async def run_claimed(run: AgentRun, lease_owner: str) -> None:
    heartbeat = asyncio.create_task(_heartbeat(run.id, lease_owner))
    usage: dict[str, int] | None = None
    try:
        try:
            retention_seconds = None
            if run.agent_code in agent_runs.REPORT_GENERATION_CODES:
                retention_seconds = max(
                    0.0,
                    (run.payload_expires_at - datetime.now(UTC)).total_seconds()
                    if run.payload_expires_at is not None
                    else 0.0,
                )
            async with asyncio.timeout(retention_seconds):
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
                    agent_code, input_snapshot, requester_id = await agent_runs.prepare_claimed(
                        run, lease_owner
                    )
                    output = await agent_runs.dispatch(agent_code, input_snapshot, requester_id)
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
                await _fail(run, lease_owner, error_code, usage)
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
    now = datetime.now(UTC)
    await _fail_exhausted_leases(now)
    await agent_runs.redact_expired_payloads(now)
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
            now = datetime.now(UTC)
            await _fail_exhausted_leases(now)
            await agent_runs.redact_expired_payloads(now)
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
                        'agent_run', 'report', 'report_deal',
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
