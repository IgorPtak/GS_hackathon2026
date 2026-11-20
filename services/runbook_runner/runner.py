"""Runbook step walking (pure over a store and plugins) and the job handler around it."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any

import asyncpg
import orjson
from alerting_contracts.alerts import Alert, AuditVerb, RunbookJob
from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import (
    ActionRun,
    ActionRunStatus,
    RenderedRunbook,
    RenderedRunbookStep,
    Runbook,
    RunIf,
    StepKind,
)
from alerting_contracts.sse import (
    ActionRunUpdatedEvent,
    ApprovalRequestedEvent,
    AuditAppendedEvent,
)
from alerting_core.config.registry import ConfigRegistry
from alerting_core.durations import parse_duration
from alerting_core.logging import get_logger
from alerting_core.publishing import publish_team_event
from alerting_core.runbooks.rendering import render_runbook
from alerting_core.settings import Settings
from alerting_core.storage.alerts_read import get_alert
from alerting_core.storage.transitions import AlertNotFoundError
from alerting_core.streams import BatchFailures, StreamMessage
from pydantic import BaseModel
from redis.asyncio import Redis

from plugins.actions import ActionPlugin, UnknownActionTypeError, get_action_plugin

from .approvals import ApprovalNotifier, OutboxApprovalNotifier
from .metrics import ACTION_RUNS, RUNBOOK_JOBS
from .store import PgStore, RunbookStore, latest, lock_alert

log = get_logger(__name__)

PluginFactory = Callable[[str], ActionPlugin]
DeadLetter = Callable[[list[StreamMessage], str], Awaitable[None]]
# Slack on top of an action's own timeout before the runner gives up on the call.
PLUGIN_TIMEOUT_MARGIN_SECONDS = 5.0
LOCK_TIMEOUT = "120s"


class RunbookNotLoadedError(RuntimeError):
    """The runbook is not in the registry (yet); the job must be retried, not acked."""


_HELD = (
    ActionRunStatus.pending_approval,
    ActionRunStatus.approved,
    ActionRunStatus.rejected,
    ActionRunStatus.running,
)


def _is_satisfied(run_if: RunIf, previous: ActionRunStatus | None) -> bool:
    if run_if is RunIf.previous_failed:
        return previous is ActionRunStatus.failed
    if run_if is RunIf.previous_succeeded:
        return previous is ActionRunStatus.succeeded
    return True


class RunbookWalker:
    """Walks rendered steps for one alert. Collects SSE events; the caller publishes them
    after the surrounding transaction commits."""

    def __init__(
        self,
        store: RunbookStore,
        notifier: ApprovalNotifier,
        alert: Alert,
        rendered: RenderedRunbook,
        actions: Mapping[str, ActionConfig],
        plugin_factory: PluginFactory = get_action_plugin,
    ) -> None:
        self._store = store
        self._notifier = notifier
        self._alert = alert
        self._rendered = rendered
        self._actions = actions
        self._plugin_factory = plugin_factory
        self.events: list[BaseModel] = []

    # -- events -----------------------------------------------------------------------------

    async def _audit(self, verb: AuditVerb, detail: dict[str, Any], outcome: str = "ok") -> None:
        detail = {"runbook_id": self._rendered.runbook_id, **detail}
        entry = await self._store.append_audit(self._alert.id, verb, detail, outcome)
        self.events.append(AuditAppendedEvent(at=datetime.now(UTC), entry=entry))

    def _changed(self, run: ActionRun) -> None:
        self.events.append(ActionRunUpdatedEvent(at=datetime.now(UTC), action_run=run))

    # -- entry points -----------------------------------------------------------------------

    async def start(self) -> None:
        """start_runbook: audit once, then walk from the first step."""
        runbook_id = self._rendered.runbook_id
        if not await self._store.has_audit(self._alert.id, AuditVerb.runbook_started, runbook_id):
            await self._audit(AuditVerb.runbook_started, {"title": self._rendered.title})
        await self._walk(after_index=-1, previous=None)

    async def execute_approved(self, run: ActionRun) -> None:
        """execute_action_run: run the approved step, then continue after it."""
        step = next((s for s in self._rendered.steps if s.index == run.step_index), None)
        if step is None:
            log.warning(
                "runbook_step_missing", extra={"alert_id": run.alert_id, "step": run.step_index}
            )
            error = f"step {run.step_index} no longer exists in runbook {run.runbook_id}"
            failed = await self._store.update_run(
                run.id, ActionRunStatus.failed, run.attempt, error=error
            )
            self._changed(failed)
            await self._audit(
                AuditVerb.action_run_failed,
                {
                    "step_index": run.step_index,
                    "action_id": run.action_id,
                    "attempt": run.attempt,
                    "action_run_id": run.id,
                    "detail": error,
                },
                outcome="error",
            )
            return
        final = await self._execute(step, run)
        await self._walk(after_index=step.index, previous=final.status)

    # -- the walk ---------------------------------------------------------------------------

    async def _walk(self, after_index: int, previous: ActionRunStatus | None) -> None:
        for step in self._rendered.steps:
            if step.index <= after_index:
                continue
            if step.kind is StepKind.text or step.action is None:
                continue
            # Manual steps run from the UI later; only an approval gate is handled here.
            if not (step.is_automatic or step.requires_approval):
                continue
            runs = await self._store.runs_for_step(
                self._alert.id, self._rendered.runbook_id, step.index
            )
            last = latest(runs)
            if last is not None:
                if last.status is ActionRunStatus.succeeded:
                    previous = ActionRunStatus.succeeded
                    continue
                if last.status is ActionRunStatus.failed and last.attempt >= step.max_attempts:
                    previous = ActionRunStatus.failed
                    continue
                if last.status is ActionRunStatus.skipped:
                    continue
                if last.status in _HELD:
                    return  # waiting for a decision or being executed: nothing more here
            elif not _is_satisfied(step.run_if, previous):
                run = await self._store.create_run(
                    self._alert.id,
                    self._rendered.runbook_id,
                    step.index,
                    step.action,
                    step.params,
                    ActionRunStatus.skipped,
                )
                self._changed(run)
                await self._audit(
                    AuditVerb.action_run_skipped,
                    {
                        "step_index": step.index,
                        "action_id": step.action,
                        "run_if": step.run_if.value,
                        "action_run_id": run.id,
                    },
                )
                continue
            elif step.requires_approval:
                await self._request_approval(step)
                return
            final = await self._execute(step, None, last)
            previous = final.status

    async def _request_approval(self, step: RenderedRunbookStep) -> None:
        assert step.action is not None
        run = await self._store.create_run(
            self._alert.id,
            self._rendered.runbook_id,
            step.index,
            step.action,
            step.params,
            ActionRunStatus.pending_approval,
        )
        approval = await self._store.create_approval(run, self._alert.team, step.text)
        await self._notifier.notify(self._alert, approval)
        self._changed(run)
        self.events.append(ApprovalRequestedEvent(at=datetime.now(UTC), approval_request=approval))
        await self._audit(
            AuditVerb.approval_requested,
            {
                "step_index": step.index,
                "action_id": step.action,
                "action_run_id": run.id,
                "approval_request_id": approval.id,
            },
            outcome="pending",
        )

    # -- execution --------------------------------------------------------------------------

    async def _execute(
        self, step: RenderedRunbookStep, approved: ActionRun | None, last: ActionRun | None = None
    ) -> ActionRun:
        """Run attempts until one succeeds or `max_attempts` is used; returns the final run.

        `approved` is the existing approved row, reused for the first attempt; `last` is a
        failed earlier attempt (max_attempts was raised since), after which numbering continues.
        """
        assert step.action is not None
        attempt = approved.attempt if approved else (last.attempt + 1 if last else 1)
        existing = approved
        while True:
            if existing is not None:
                run = await self._store.update_run(existing.id, ActionRunStatus.running, attempt)
            else:
                run = await self._store.create_run(
                    self._alert.id,
                    self._rendered.runbook_id,
                    step.index,
                    step.action,
                    step.params,
                    ActionRunStatus.running,
                    attempt,
                )
            self._changed(run)
            detail = {
                "step_index": step.index,
                "action_id": step.action,
                "attempt": attempt,
                "action_run_id": run.id,
            }
            await self._audit(AuditVerb.action_run_started, detail)
            is_success, text, data = await self._call_plugin(step)
            status = ActionRunStatus.succeeded if is_success else ActionRunStatus.failed
            run = await self._store.update_run(
                run.id,
                status,
                attempt,
                result={"detail": text, "data": data},
                error=None if is_success else text,
            )
            self._changed(run)
            await self._audit(
                AuditVerb.action_run_succeeded if is_success else AuditVerb.action_run_failed,
                {**detail, "detail": text},
                outcome="ok" if is_success else "error",
            )
            if is_success or attempt >= step.max_attempts:
                return run
            attempt += 1
            existing = None

    async def _call_plugin(self, step: RenderedRunbookStep) -> tuple[bool, str, dict[str, Any]]:
        """Never raises for plugin problems: they become a failed result."""
        assert step.action is not None
        config = self._actions.get(step.action)
        if config is None:
            return False, f"unknown action {step.action!r}", {}
        try:
            plugin = self._plugin_factory(config.type)
            timeout = parse_duration(config.timeout) + PLUGIN_TIMEOUT_MARGIN_SECONDS
            result = await asyncio.wait_for(plugin.execute(step.params, config), timeout)
        except TimeoutError:
            return False, f"timed out after {config.timeout}", {}
        except UnknownActionTypeError:
            return False, f"no plugin for action type {config.type!r}", {}
        except Exception as error:  # noqa: BLE001 - a plugin bug must not crash the job
            log.exception(
                "action_plugin_raised",
                extra={"alert_id": self._alert.id, "action_id": step.action},
            )
            return False, f"{type(error).__name__}: {error}", {}
        return result.is_success, result.detail, result.data


class RunbookRunner:
    """Handles `runbook-jobs` entries: one transaction per job, advisory-locked per alert."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        redis: Redis,
        registry: ConfigRegistry,
        settings: Settings,
        plugin_factory: PluginFactory = get_action_plugin,
        dead_letter: DeadLetter | None = None,
    ) -> None:
        # Set after construction too (the consumer needs the handler first).
        self.dead_letter = dead_letter
        self._pool = pool
        self._redis = redis
        self._registry = registry
        self._settings = settings
        self._plugin_factory = plugin_factory

    async def handle_batch(self, messages: list[StreamMessage]) -> BatchFailures:
        """Entries that raise stay pending (retried, then dead-lettered); bad ones are acked."""
        failures: dict[str, str] = {}
        for message in messages:
            try:
                job = RunbookJob.model_validate(orjson.loads(message.fields[b"job"]))
            except (KeyError, ValueError):
                # orjson's decode error and pydantic's ValidationError are ValueErrors.
                log.exception("runbook_job_unparsable", extra={"entry_id": message.id})
                if self.dead_letter is not None:
                    # Copied to runbook-jobs-dlq and acked there; a failure leaves it pending.
                    try:
                        await self.dead_letter([message], "unparsable runbook job")
                    except Exception as error:  # noqa: BLE001 - retry the entry instead
                        failures[message.id] = f"{type(error).__name__}: {error}"
                RUNBOOK_JOBS.labels("unknown", "invalid").inc()
                continue
            try:
                outcome = await self.handle_job(job)
            except Exception as error:  # noqa: BLE001 - leave the entry pending for a retry
                log.exception(
                    "runbook_job_failed",
                    extra={"alert_id": job.alert_id, "job_type": job.job_type},
                )
                RUNBOOK_JOBS.labels(job.job_type, "failed").inc()
                failures[message.id] = f"{type(error).__name__}: {error}"
            else:
                RUNBOOK_JOBS.labels(job.job_type, outcome).inc()
        return failures

    async def handle_job(self, job: RunbookJob) -> str:
        """Run one job in a transaction; returns "handled" or "skipped". SSE follows the commit."""
        # Before the lock: a runbook that is not loaded yet fails the entry so it is retried.
        runbook = self._registry.get("runbook", job.runbook_id)
        if not isinstance(runbook, Runbook):
            log.warning(
                "runbook_job_runbook_missing",
                extra={"alert_id": job.alert_id, "runbook_id": job.runbook_id},
            )
            raise RunbookNotLoadedError(f"runbook {job.runbook_id!r} is not loaded")
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
                await lock_alert(connection, job.alert_id)
                outcome, team, events = await self._process(connection, job, runbook)
            # Committed: only now may anyone observe the changes.
            for event in events:
                if isinstance(event, ActionRunUpdatedEvent):
                    ACTION_RUNS.labels(event.action_run.status.value).inc()
                await publish_team_event(self._redis, team, event)
        return outcome

    async def _process(
        self, connection: asyncpg.Connection, job: RunbookJob, runbook: Runbook
    ) -> tuple[str, str, list[BaseModel]]:
        extra = {"alert_id": job.alert_id, "job_type": job.job_type, "runbook_id": job.runbook_id}
        try:
            alert = await get_alert(connection, job.alert_id)
        except AlertNotFoundError:
            log.warning("runbook_job_alert_missing", extra=extra)
            return "skipped", "", []
        store = PgStore(connection)
        run: ActionRun | None = None
        if job.job_type == "execute_action_run":
            run = (
                await store.get_run(job.action_run_id, for_update=True)
                if job.action_run_id
                else None
            )
            if run is None or run.alert_id != alert.id:
                log.warning("runbook_job_action_run_missing", extra=extra)
                return "skipped", alert.team, []
            if run.runbook_id != job.runbook_id:
                log.warning("runbook_job_runbook_mismatch", extra={**extra, "run": run.runbook_id})
                return "skipped", alert.team, []
            if run.status is not ActionRunStatus.approved:
                log.info("runbook_job_not_approved", extra={**extra, "status": run.status.value})
                return "skipped", alert.team, []
        actions = self._registry.actions()
        rendered = render_runbook(runbook, alert, actions)
        notifier = OutboxApprovalNotifier(
            connection,
            rules=self._registry.rules(),
            teams=self._registry.teams(),
            recipients=self._registry.recipients(),
            channels=self._registry.channels(),
            public_base_url=self._settings.public_base_url,
            clock=lambda: datetime.now(UTC),
        )
        walker = RunbookWalker(store, notifier, alert, rendered, actions, self._plugin_factory)
        if run is not None:
            await walker.execute_approved(run)
        else:
            await walker.start()
        return "handled", alert.team, walker.events
