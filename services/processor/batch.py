"""One `events` batch: evaluate, dedup, then one Postgres transaction for every new alert.

Order per batch (contracts/storage.md, dedup row):
  1. evaluate every event (pure, no I/O) and group matches by (rule_id, fingerprint);
  2. claim `dedup:<rule>:<fingerprint>` per group with a pre-generated alert id (one pipeline);
  3. in ONE transaction: look up the owning alerts, insert the missing ones
     (`ON CONFLICT (id) DO NOTHING`), and for each alert actually inserted write its audit entry
     and outbox rows (deliveries + runbook job); upsert unknown-schema samples;
  4. after commit: re-arm keys, count folds, publish SSE, hand resolution events to A-18.
A crash after 3 but before XACK redelivers the batch: the key and the alert exist, so the
events only fold (count + n) and no second alert or delivery is created.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import asyncpg
from alerting_contracts.alerts import Alert, AlertStatus, AuditEntry
from alerting_contracts.api import UnknownSchemaSample
from alerting_contracts.config import Rule
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
from alerting_core.ids import new_uuid7
from alerting_core.logging import get_logger
from alerting_core.outbox import OutboxRow, enqueue_outbox_rows
from alerting_core.publishing import publish_team_event
from alerting_core.settings import Settings
from alerting_core.storage.alerts_write import (
    AuditRow,
    fetch_alert_statuses,
    find_open_alerts,
    insert_alerts,
    insert_audit_entries,
    upsert_unknown_samples,
)
from alerting_core.streams import StreamMessage
from pydantic import ValidationError
from redis.asyncio import Redis

from .deliveries import AlertSideEffects, plan_alert_side_effects
from .evaluation import EventOutcome, RuleMatch, RuleSet, evaluate_event
from .folds import FoldTracker
from .metrics import ALERTS_CREATED, EVENT_TO_ALERT_SECONDS, EVENTS_PROCESSED
from .unknown_shapes import collect_unknown_samples, publish_new_samples

log = get_logger(__name__)

ResolutionHook = Callable[[list[EventOutcome]], Awaitable[None]]
DeadLetter = Callable[[list[StreamMessage], str], Awaitable[None]]


@dataclass(slots=True)
class MatchGroup:
    """All events of one batch that matched one rule with one fingerprint, in stream order."""

    rule: Rule
    fingerprint: str
    events: list[tuple[RuleMatch, EventOutcome]] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return self.rule.id, self.fingerprint


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
        rule_set, snapshot = self._rule_set, self._registry.snapshot
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
        if invalid:
            EVENTS_PROCESSED.labels("invalid").inc(len(invalid))
            if self.dead_letter is not None:
                await self.dead_letter(invalid, "invalid_envelope")
        await self._persist(snapshot, outcomes)
        resolutions = [o for o in outcomes if o.normalized.is_resolution]
        if resolutions:
            await self._resolution_hook(resolutions)
        EVENTS_PROCESSED.labels("processed").inc(len(outcomes))
        return failures

    async def _persist(self, snapshot: ConfigSnapshot, outcomes: list[EventOutcome]) -> None:
        groups = _group_matches(outcomes)
        samples = collect_unknown_samples(outcomes)
        if not groups and not samples:
            return
        claims = [
            DedupClaim(
                g.rule.id, g.fingerprint, parse_duration_ms(g.rule.dedup.window), new_uuid7()
            )
            for g in groups
        ]
        owners = [result.alert_id for result in await claim_dedup_keys(self._redis, claims)]
        plan = BatchPlan(now=datetime.now(UTC))
        async with self._pool.acquire() as connection, connection.transaction():
            await _decide(connection, plan, groups, claims, owners)
            inserted = await insert_alerts(connection, [c.alert for c in plan.creates])
            outbox_rows: list[OutboxRow] = []
            audit_rows: list[AuditRow] = []
            for create in plan.creates:
                if create.alert.id not in inserted:
                    # Another processor inserted it first (we waited on its commit): a fold.
                    plan.folds.append(Fold(create.group, create.claim, create.alert.id))
                    continue
                plan.created.append(create.alert)
                effects = await self._side_effects(snapshot, create, plan.now)
                outbox_rows.extend(effects.outbox_rows)
                audit_rows.extend(effects.audit_rows)
            await enqueue_outbox_rows(connection, outbox_rows)
            plan.audit = await insert_audit_entries(connection, audit_rows)
            plan.new_samples = await upsert_unknown_samples(connection, samples)
        await self._after_commit(plan)

    async def _side_effects(
        self, snapshot: ConfigSnapshot, create: "Create", now: datetime
    ) -> AlertSideEffects:
        _, first = create.group.events[0]
        return await plan_alert_side_effects(
            self._redis,
            snapshot,
            create.group.rule,
            create.alert,
            source=first.normalized.source,
            public_base_url=self._settings.public_base_url,
            event_sent_at=first.envelope.sent_at or first.envelope.received_at,
            now=now,
        )

    async def _after_commit(self, plan: "BatchPlan") -> None:
        await rearm_dedup_keys(self._redis, plan.rearms)
        await record_folds(self._redis, [(f.claim, len(f.group.events)) for f in plan.folds])
        for fold in plan.folds:
            _, last = fold.group.events[-1]
            count_key = dedup_count_key(fold.claim.rule_id, fold.claim.fingerprint)
            self._folds.add(
                fold.alert_id, count_key, last.envelope.received_at, last.envelope.payload
            )
        ALERTS_CREATED.inc(len(plan.created))
        teams = {alert.id: alert.team for alert in plan.created}
        for create in plan.creates:
            if create.alert in plan.created:
                _, first = create.group.events[0]
                latency = (plan.now - first.envelope.received_at).total_seconds()
                EVENT_TO_ALERT_SECONDS.observe(max(latency, 0.0))
        for alert in plan.created:
            event = AlertCreatedEvent(at=plan.now, alert=alert)
            await publish_team_event(self._redis, alert.team, event)
            log.info("alert_created", extra={"alert_id": alert.id, "rule_id": alert.rule_id})
        for entry in plan.audit:
            appended = AuditAppendedEvent(at=plan.now, entry=entry)
            await publish_team_event(self._redis, teams[entry.alert_id], appended)
        await publish_new_samples(self._redis, plan.new_samples, plan.now)


@dataclass(slots=True)
class Create:
    group: MatchGroup
    claim: DedupClaim
    alert: Alert


@dataclass(slots=True)
class Fold:
    group: MatchGroup
    claim: DedupClaim
    alert_id: str


@dataclass(slots=True)
class BatchPlan:
    """What one batch decided; filled inside the transaction, acted on after commit."""

    now: datetime
    creates: list[Create] = field(default_factory=list)
    folds: list[Fold] = field(default_factory=list)
    rearms: list[tuple[DedupClaim, str]] = field(default_factory=list)
    created: list[Alert] = field(default_factory=list)
    audit: list[AuditEntry] = field(default_factory=list)
    new_samples: list[UnknownSchemaSample] = field(default_factory=list)


async def _decide(
    connection: asyncpg.Connection,
    plan: BatchPlan,
    groups: list[MatchGroup],
    claims: list[DedupClaim],
    owners: list[str],
) -> None:
    """Create or fold per group, following the dedup rules in contracts/storage.md."""
    statuses = await fetch_alert_statuses(connection, owners)
    missing = [g.key for g, owner in zip(groups, owners, strict=True) if owner not in statuses]
    open_alerts = await find_open_alerts(connection, missing)
    for group, claim, owner in zip(groups, claims, owners, strict=True):
        status = statuses.get(owner)
        if status is not None and status != AlertStatus.resolved:
            plan.folds.append(Fold(group, claim, owner))
        elif status is None and group.key in open_alerts:
            # Window expired while the alert is still open: fold into it and re-arm the key.
            plan.folds.append(Fold(group, claim, open_alerts[group.key]))
            plan.rearms.append((claim, open_alerts[group.key]))
        elif status is None:
            plan.creates.append(Create(group, claim, _build_alert(group, owner, plan.now)))
        else:
            # The windowed alert was resolved: the next occurrence opens a new alert.
            alert_id = new_uuid7()
            plan.creates.append(Create(group, claim, _build_alert(group, alert_id, plan.now)))
            plan.rearms.append((claim, alert_id))


def _group_matches(outcomes: list[EventOutcome]) -> list[MatchGroup]:
    groups: dict[tuple[str, str], MatchGroup] = {}
    for outcome in outcomes:
        for match in outcome.matches:
            key = (match.rule.id, match.fingerprint)
            group = groups.get(key)
            if group is None:
                group = groups[key] = MatchGroup(match.rule, match.fingerprint)
            group.events.append((match, outcome))
    return list(groups.values())


def _build_alert(group: MatchGroup, alert_id: str, now: datetime) -> Alert:
    """The first event of the batch titles the alert; the rest are already counted in."""
    match, first = group.events[0]
    _, last = group.events[-1]
    return Alert(
        id=alert_id,
        rule_id=group.rule.id,
        team=group.rule.team,
        schema_profile_id=first.profile.id,
        source_id=first.envelope.source_id,
        fingerprint=group.fingerprint,
        severity=match.severity,
        title=match.title,
        body=match.body,
        fields=match.fields,
        color=group.rule.present.color,
        count=len(group.events),
        first_seen=first.envelope.received_at,
        last_seen=last.envelope.received_at,
        runbook_id=group.rule.runbook,
        last_event=last.envelope.payload,
        updated_at=now,
    )
