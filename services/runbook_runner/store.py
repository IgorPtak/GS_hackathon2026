"""SQL for action_runs, approval_requests and the audit checks the runner needs.

Every function takes the connection of the job's transaction; nothing here commits.
`RunbookStore` is the narrow interface the step walker depends on (tests substitute a fake).
"""

import secrets
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

import asyncpg
from alerting_contracts.alerts import AuditEntry, AuditVerb
from alerting_contracts.common import Actor
from alerting_contracts.runbooks import ActionRun, ActionRunStatus, ApprovalRequest
from alerting_core.ids import new_uuid7
from alerting_core.logging import get_logger
from alerting_core.storage.audit import append_audit
from alerting_core.storage.rows import row_to_dict

log = get_logger(__name__)

RUNNER_ACTOR = Actor(id="system:runbook-runner")
MAX_CODE_ATTEMPTS = 10


class RunbookStore(Protocol):
    """What the walker needs from storage."""

    async def has_audit(self, alert_id: str, verb: AuditVerb, runbook_id: str) -> bool: ...

    async def append_audit(
        self, alert_id: str, verb: AuditVerb, detail: dict[str, Any], outcome: str = "ok"
    ) -> AuditEntry: ...

    async def runs_for_step(
        self, alert_id: str, runbook_id: str, step_index: int
    ) -> list[ActionRun]: ...

    async def get_run(self, run_id: str, for_update: bool = False) -> ActionRun | None: ...

    async def create_run(
        self,
        alert_id: str,
        runbook_id: str,
        step_index: int,
        action_id: str,
        params: dict[str, str],
        status: ActionRunStatus,
        attempt: int = 1,
        requested_by: Actor | None = None,
    ) -> ActionRun: ...

    async def update_run(
        self,
        run_id: str,
        status: ActionRunStatus,
        attempt: int,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ActionRun: ...

    async def create_approval(self, run: ActionRun, team: str, summary: str) -> ApprovalRequest: ...


async def lock_alert(connection: asyncpg.Connection, alert_id: str) -> None:
    """Take the transaction-scoped advisory lock that serializes runners per alert."""
    await connection.execute("SELECT pg_advisory_xact_lock(hashtext($1))", alert_id)


def random_code() -> str:
    """A random 4-digit approval code, leading zeros kept."""
    return f"{secrets.randbelow(10_000):04d}"


def _run(record: asyncpg.Record) -> ActionRun:
    return ActionRun.model_validate(row_to_dict(record))


class PgStore:
    """RunbookStore over one asyncpg connection inside the job's transaction."""

    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def has_audit(self, alert_id: str, verb: AuditVerb, runbook_id: str) -> bool:
        found = await self._connection.fetchval(
            "SELECT 1 FROM audit_entries WHERE alert_id = $1::uuid AND verb = $2 "
            "AND detail->>'runbook_id' = $3 LIMIT 1",
            alert_id,
            verb.value,
            runbook_id,
        )
        return found is not None

    async def append_audit(
        self, alert_id: str, verb: AuditVerb, detail: dict[str, Any], outcome: str = "ok"
    ) -> AuditEntry:
        return await append_audit(
            self._connection, alert_id, RUNNER_ACTOR, verb, outcome=outcome, detail=detail
        )

    async def runs_for_step(
        self, alert_id: str, runbook_id: str, step_index: int
    ) -> list[ActionRun]:
        """Runs of one step, oldest first (the last one is the latest attempt)."""
        records = await self._connection.fetch(
            "SELECT * FROM action_runs WHERE alert_id = $1::uuid AND runbook_id = $2 "
            "AND step_index = $3 ORDER BY attempt, created_at",
            alert_id,
            runbook_id,
            step_index,
        )
        return [_run(record) for record in records]

    async def get_run(self, run_id: str, for_update: bool = False) -> ActionRun | None:
        """One run; `for_update` row-locks it until the job's transaction ends."""
        record = await self._connection.fetchrow(
            "SELECT * FROM action_runs WHERE id = $1::uuid" + (" FOR UPDATE" if for_update else ""),
            run_id,
        )
        return _run(record) if record else None

    async def create_run(
        self,
        alert_id: str,
        runbook_id: str,
        step_index: int,
        action_id: str,
        params: dict[str, str],
        status: ActionRunStatus,
        attempt: int = 1,
        requested_by: Actor | None = None,
    ) -> ActionRun:
        """Insert a run; `requested_by` defaults to the runner (the API passes the human)."""
        record = await self._connection.fetchrow(
            "INSERT INTO action_runs (id, alert_id, runbook_id, step_index, action_id, params, "
            "status, attempt, requested_by) "
            "VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9) RETURNING *",
            new_uuid7(),
            alert_id,
            runbook_id,
            step_index,
            action_id,
            params,
            status.value,
            attempt,
            (requested_by or RUNNER_ACTOR).model_dump(mode="json"),
        )
        if record is None:
            raise RuntimeError("action_runs insert returned no row")
        return _run(record)

    async def update_run(
        self,
        run_id: str,
        status: ActionRunStatus,
        attempt: int,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ActionRun:
        record = await self._connection.fetchrow(
            "UPDATE action_runs SET status = $2, attempt = $3, result = $4, error = $5, "
            "updated_at = now() WHERE id = $1::uuid RETURNING *",
            run_id,
            status.value,
            attempt,
            result,
            error,
        )
        if record is None:
            raise RuntimeError(f"action run {run_id} vanished")
        return _run(record)

    async def create_approval(self, run: ActionRun, team: str, summary: str) -> ApprovalRequest:
        """Insert the approval with a random code unique among pending requests.

        Each try runs in a savepoint so a unique violation does not abort the job's transaction.
        """
        for _ in range(MAX_CODE_ATTEMPTS):
            try:
                async with self._connection.transaction():
                    record = await self._connection.fetchrow(
                        "INSERT INTO approval_requests (id, action_run_id, alert_id, team, "
                        "runbook_id, step_index, action_id, params, summary, approval_code, "
                        "requested_at) VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, "
                        "$8, $9, $10, $11) RETURNING *",
                        new_uuid7(),
                        run.id,
                        run.alert_id,
                        team,
                        run.runbook_id,
                        run.step_index,
                        run.action_id,
                        run.params,
                        summary,
                        random_code(),
                        datetime.now(UTC),
                    )
            except asyncpg.UniqueViolationError:
                log.info("approval_code_collision", extra={"alert_id": run.alert_id})
                continue
            if record is None:
                raise RuntimeError("approval_requests insert returned no row")
            return ApprovalRequest.model_validate(
                {**row_to_dict(record), "approval_code": str(record["approval_code"]).strip()}
            )
        raise RuntimeError(f"no free approval code after {MAX_CODE_ATTEMPTS} tries")


def latest(runs: Sequence[ActionRun]) -> ActionRun | None:
    """The most recent attempt of a step, or None."""
    return runs[-1] if runs else None
