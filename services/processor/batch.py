"""One `events` batch: evaluate, dedup, then one Postgres transaction for every new alert.

Order per batch (contracts/storage.md, dedup row):
  1. evaluate every event (pure, no I/O) and group matches by (rule_id, fingerprint);
  2. claim `dedup:<rule>:<fingerprint>` per group with a pre-generated alert id (one pipeline);
  3. decide create or fold per group (reads only), then route and throttle the creates;
  4. in ONE transaction: insert the new alerts (`ON CONFLICT (id) DO NOTHING`, sorted by id so
     replicas lock in the same order) and, for each alert actually inserted, its audit entry and
     outbox rows (deliveries + runbook job); upsert unknown-schema samples;
  5. after commit: re-arm keys, count folds, publish SSE, hand resolution events to A-18.
A crash after 4 but before XACK redelivers the batch: every id is derived from the dedup key
(or deterministically from the resolved alert it follows), so redelivery folds and never creates
a second alert or delivery. Folds are counted again on redelivery (at-least-once counting).
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import asyncpg
from alerting_contracts.alerts import Alert
from alerting_contracts.events import EventEnvelope
from alerting_contracts.sse import AlertCreatedEvent, AuditAppendedEvent
from alerting_core.config.registry import ConfigRegistry, ConfigSnapshot
from alerting_core.dedup import (
    DedupClaim,
    claim_dedup_keys,
    dedup_count_key,
    rearm_dedup_keys,
    record_folds,
)
from alerting_core.durations import parse_duration_ms
from alerting_core.grouping import GroupEvent
from alerting_core.ids import new_uuid7
from alerting_core.logging import get_logger
from alerting_core.metrics import ALERTS_CREATED, EVENTS_PROCESSED
from alerting_core.outbox import OutboxRow, enqueue_outbox_rows
from alerting_core.publishing import publish_team_event
from alerting_core.routing import DeliveryTarget
from alerting_core.settings import Settings
from alerting_core.storage.alerts_write import (
    AuditRow,
    insert_alerts,
    insert_audit_entries,
    upsert_unknown_samples,
)
from alerting_core.streams import StreamMessage
from pydantic import ValidationError
from redis.asyncio import Redis

from .auto_resolution import current_resolutions
from .deliveries import build_side_effects, throttle_targets
from .evaluation import EventOutcome, RuleSet, evaluate_event
from .folds import FoldTracker
from .groups import BufferedEvent, buffer_group_events
from .metrics import EVENT_TO_ALERT_SECONDS, EVENTS_BY_OUTCOME
from .plan import BatchPlan, Fold, MatchGroup, decide, group_matches
from .silences import push_alert_silences
from .unknown_shapes import collect_unknown_samples, publish_new_samples

log = get_logger(__name__)

ResolutionHook = Callable[[list[EventOutcome]], Awaitable[None]]
DeadLetter = Callable[[list[StreamMessage], str], Awaitable[None]]

# Replicas lock rows in the same (sorted) order, so deadlocks are not expected; if one still
# happens the whole step is safe to repeat because every id is derived from the dedup keys.
_RETRYABLE = (asyncpg.DeadlockDetectedError, asyncpg.SerializationError)
_PERSIST_ATTEMPTS = 3


async def _log_resolutions(outcomes: list[EventOutcome]) -> None:
    log.info("resolution_events_received", extra={"count": len(outcomes)})


class EventProcessor:
    """Batch handler for `StreamConsumer`; set `dead_letter` to the consumer's method."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        redis: Redis,
        registry: ConfigRegistry,
        settings: Settings,
        folds: FoldTracker,
        resolution_hook: ResolutionHook | None = None,
    ) -> None:
        self._pool = pool
        self._redis = redis
        self._registry = registry
        self._settings = settings
        self._folds = folds
        self._resolution_hook = resolution_hook or _log_resolutions
        self._rule_set = RuleSet(registry.snapshot)
        self.dead_letter: DeadLetter | None = None
        registry.on_reload.append(self._rebuild_rule_set)

    def _rebuild_rule_set(self, snapshot: ConfigSnapshot) -> None:
        self._rule_set = RuleSet(snapshot)

    async def handle_batch(self, messages: list[StreamMessage]) -> dict[str, str]:
        """Process one batch; returns per-entry failures (left pending for a retry)."""
        rule_set = self._rule_set  # one snapshot for the whole batch, even across a reload
        outcomes: list[EventOutcome] = []
        invalid: list[StreamMessage] = []
        failures: dict[str, str] = {}
        for message in messages:
            try:
                envelope = EventEnvelope.model_validate_json(message.fields[b"envelope"])
            except (KeyError, ValidationError, ValueError) as error:
                log.warning(
                    "event_envelope_invalid", extra={"entry_id": message.id, "error": str(error)}
                )
                invalid.append(message)
                continue
            try:
                outcomes.append(evaluate_event(rule_set, envelope))
            except Exception as error:  # a bug for one event must not block the batch
                log.exception("event_evaluation_failed", extra={"entry_id": message.id})
                failures[message.id] = f"{type(error).__name__}: {error}"
        await self._persist_with_retry(rule_set.snapshot, outcomes)
        # A crash between buffering and the ack re-buffers the batch: group counts are
        # at-least-once, like dedup fold counts.
        await buffer_group_events(self._redis, _buffered_events(outcomes), int(time.time() * 1000))
        # Only after the batch is safely written, so a retried batch never dead-letters twice.
        if invalid:
            EVENTS_BY_OUTCOME.labels("invalid").inc(len(invalid))
            if self.dead_letter is not None:
                await self.dead_letter(invalid, "invalid_envelope")
        await self._run_resolution_hook(outcomes)
        EVENTS_BY_OUTCOME.labels("processed").inc(len(outcomes))
        EVENTS_PROCESSED.inc(len(outcomes))
        return failures

    async def _run_resolution_hook(self, outcomes: list[EventOutcome]) -> None:
        resolutions = current_resolutions(outcomes)
        if not resolutions:
            return
        try:
            await self._resolution_hook(resolutions)
        except Exception:
            # Failing the batch here would redeliver it and double-count its folds.
            log.exception("resolution_hook_failed", extra={"count": len(resolutions)})

    async def _persist_with_retry(
        self, snapshot: ConfigSnapshot, outcomes: list[EventOutcome]
    ) -> None:
        for attempt in range(1, _PERSIST_ATTEMPTS + 1):
            try:
                await self._persist(snapshot, outcomes)
                return
            except _RETRYABLE:
                if attempt == _PERSIST_ATTEMPTS:
                    raise
                log.warning("processor_persist_retry", extra={"attempt": attempt})

    async def _persist(self, snapshot: ConfigSnapshot, outcomes: list[EventOutcome]) -> None:
        groups = group_matches(outcomes)
        samples = collect_unknown_samples(outcomes)
        if not groups and not samples:
            return
        claims = [_claim_for(group) for group in groups]
        owners = [result.alert_id for result in await claim_dedup_keys(self._redis, claims)]
        plan = BatchPlan(now=datetime.now(UTC))
        async with self._pool.acquire() as connection:
            await decide(connection, plan, groups, claims, owners)
            routed = await asyncio.gather(
                *(
                    self._throttle(snapshot, create.group, create.alert, plan.now)
                    for create in plan.creates
                )
            )
            async with connection.transaction():
                inserted = await insert_alerts(connection, [c.alert for c in plan.creates])
                outbox_rows: list[OutboxRow] = []
                audit_rows: list[AuditRow] = []
                for create, (allowed, suppressed) in zip(plan.creates, routed, strict=True):
                    if create.alert.id not in inserted:
                        # A replica inserted it first (we waited on its commit): a fold.
                        plan.folds.append(Fold(create.group, create.claim, create.alert.id))
                        continue
                    plan.created.append(create.alert)
                    _, first = create.group.events[0]
                    effects = build_side_effects(
                        create.group.rule,
                        create.alert,
                        allowed,
                        suppressed,
                        public_base_url=self._settings.public_base_url,
                        event_sent_at=first.envelope.sent_at or first.envelope.received_at,
                    )
                    outbox_rows.extend(effects.outbox_rows)
                    audit_rows.extend(effects.audit_rows)
                await enqueue_outbox_rows(connection, outbox_rows)
                plan.audit = await insert_audit_entries(connection, audit_rows)
                plan.new_samples = await upsert_unknown_samples(connection, samples)
        await self._after_commit(plan)

    async def _throttle(
        self, snapshot: ConfigSnapshot, group: MatchGroup, alert: Alert, now: datetime
    ) -> tuple[list[DeliveryTarget], list[DeliveryTarget]]:
        _, first = group.events[0]
        return await throttle_targets(
            self._redis, snapshot, group.rule, alert, first.normalized.source, now
        )

    async def _after_commit(self, plan: BatchPlan) -> None:
        committed_at = datetime.now(UTC)
        await rearm_dedup_keys(self._redis, plan.rearms)
        await record_folds(self._redis, [(f.claim, len(f.group.events)) for f in plan.folds])
        for fold in plan.folds:
            _, last = fold.group.events[-1]
            count_key = dedup_count_key(fold.claim.rule_id, fold.claim.fingerprint)
            self._folds.add(
                fold.alert_id, count_key, last.envelope.received_at, last.envelope.payload
            )
        ALERTS_CREATED.inc(len(plan.created))
        created_ids = {alert.id for alert in plan.created}
        for create in plan.creates:
            if create.alert.id in created_ids:
                _, first = create.group.events[0]
                latency = (committed_at - first.envelope.received_at).total_seconds()
                EVENT_TO_ALERT_SECONDS.observe(max(latency, 0.0))
                log.info(
                    "alert_created",
                    extra={"alert_id": create.alert.id, "rule_id": create.alert.rule_id},
                )
        teams = {alert.id: alert.team for alert in plan.created}
        publishes = [
            publish_team_event(self._redis, a.team, AlertCreatedEvent(at=plan.now, alert=a))
            for a in plan.created
        ] + [
            publish_team_event(
                self._redis, teams[e.alert_id], AuditAppendedEvent(at=plan.now, entry=e)
            )
            for e in plan.audit
        ]
        await asyncio.gather(*publishes)
        await publish_new_samples(self._redis, plan.new_samples, plan.now)
        await self._push_silences(plan)

    async def _push_silences(self, plan: BatchPlan) -> None:
        """Best-effort: a missed deadline is re-pushed by the alert's next event."""
        rules = {c.group.rule.id: c.group.rule for c in plan.creates}
        alerts = [(a.id, rules[a.rule_id]) for a in plan.created]
        alerts += [(f.alert_id, f.group.rule) for f in plan.folds]
        try:
            await push_alert_silences(self._redis, alerts, int(time.time() * 1000))
        except Exception:
            log.exception("silence_deadline_push_failed", extra={"count": len(alerts)})


def _buffered_events(outcomes: list[EventOutcome]) -> list[BufferedEvent]:
    items = []
    for outcome in outcomes:
        envelope = outcome.envelope
        for match in outcome.matches:
            if match.group_key is None:
                continue
            event = GroupEvent(
                fingerprint=match.fingerprint,
                title=match.title,
                body=match.body,
                severity=match.severity,
                fields=match.fields,
                received_at=envelope.received_at,
                sent_at=envelope.sent_at,
                source_id=envelope.source_id,
                schema_profile_id=outcome.profile.id,
                source=outcome.normalized.source,
                payload=envelope.payload,
            )
            items.append(BufferedEvent(match.rule, match.group_key, event))
    return items


def _claim_for(group: MatchGroup) -> DedupClaim:
    window_ms = parse_duration_ms(group.rule.dedup.window)
    return DedupClaim(group.rule.id, group.fingerprint, window_ms, new_uuid7())
