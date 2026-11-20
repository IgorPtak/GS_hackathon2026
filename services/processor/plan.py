"""Create-or-fold decisions for one batch, following the dedup rules in contracts/storage.md.

Every decision is reproducible: a redelivered batch, or a replica holding the same dedup key,
arrives at the same alert ids, so `INSERT … ON CONFLICT (id) DO NOTHING` absorbs duplicates.
"""

from dataclasses import dataclass, field
from datetime import datetime

import asyncpg
from alerting_contracts.alerts import Alert, AlertStatus, AuditEntry
from alerting_contracts.api import UnknownSchemaSample
from alerting_contracts.config import Rule
from alerting_core.dedup import DedupClaim
from alerting_core.ids import derived_uuid7, new_uuid7
from alerting_core.logging import get_logger
from alerting_core.storage.alerts_write import AlertState, fetch_alert_states, find_open_alerts

from .evaluation import EventOutcome, RuleMatch

_log = get_logger(__name__)

# How many resolved generations of one (rule, fingerprint) are followed before giving up and
# opening an alert with a fresh id; each hop is one query per batch, and hops > 1 only occur
# when a re-arm was lost twice.
MAX_SUCCESSOR_HOPS = 3


@dataclass(slots=True)
class MatchGroup:
    """All events of one batch that matched one rule with one fingerprint, in stream order."""

    rule: Rule
    fingerprint: str
    events: list[tuple[RuleMatch, EventOutcome]] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return self.rule.id, self.fingerprint


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
    """What one batch decided; acted on inside the transaction and after commit."""

    now: datetime
    creates: list[Create] = field(default_factory=list)
    folds: list[Fold] = field(default_factory=list)
    rearms: list[tuple[DedupClaim, str]] = field(default_factory=list)
    created: list[Alert] = field(default_factory=list)
    audit: list[AuditEntry] = field(default_factory=list)
    new_samples: list[UnknownSchemaSample] = field(default_factory=list)


def group_matches(outcomes: list[EventOutcome]) -> list[MatchGroup]:
    groups: dict[tuple[str, str], MatchGroup] = {}
    for outcome in outcomes:
        for match in outcome.matches:
            if match.group_key is not None:
                continue  # grouped rules go to group windows, not dedup (decision 5)
            key = (match.rule.id, match.fingerprint)
            group = groups.get(key)
            if group is None:
                group = groups[key] = MatchGroup(match.rule, match.fingerprint)
            group.events.append((match, outcome))
    return list(groups.values())


def successor_alert_id(resolved_id: str, state: AlertState) -> str:
    """Same id on every replica and redelivery for the alert that follows a resolved one."""
    resolved_ms = int(state.resolved_at.timestamp() * 1000) if state.resolved_at else 0
    return derived_uuid7(f"{resolved_id}:successor", resolved_ms)


async def _follow_successors(
    connection: asyncpg.Connection, owners: list[str]
) -> tuple[list[str], dict[str, AlertState]]:
    """Walk resolved owners to their successors; returns the current id per group and states."""
    current = list(owners)
    states = await fetch_alert_states(connection, current)
    for _ in range(MAX_SUCCESSOR_HOPS):
        next_ids = {
            index: successor_alert_id(alert_id, states[alert_id])
            for index, alert_id in enumerate(current)
            if alert_id in states and states[alert_id].status == AlertStatus.resolved
        }
        if not next_ids:
            break
        unseen = [alert_id for alert_id in next_ids.values() if alert_id not in states]
        states.update(await fetch_alert_states(connection, unseen))
        for index, alert_id in next_ids.items():
            current[index] = alert_id
    return current, states


async def decide(
    connection: asyncpg.Connection,
    plan: BatchPlan,
    groups: list[MatchGroup],
    claims: list[DedupClaim],
    owners: list[str],
) -> None:
    """Fill `plan` with one create or fold (plus re-arm) per group; reads only, no locks."""
    current, states = await _follow_successors(connection, owners)
    unknown_owner_keys = [
        group.key
        for group, owner, alert_id in zip(groups, owners, current, strict=True)
        if alert_id == owner and owner not in states
    ]
    open_alerts = await find_open_alerts(connection, unknown_owner_keys)
    for group, claim, owner, alert_id in zip(groups, claims, owners, current, strict=True):
        state = states.get(alert_id)
        if state is not None and state.status != AlertStatus.resolved:
            plan.folds.append(Fold(group, claim, alert_id))
            if alert_id != owner:
                plan.rearms.append((claim, alert_id))
        elif state is None and alert_id == owner and group.key in open_alerts:
            # Window expired while the alert is still open: fold into it and re-arm the key.
            plan.folds.append(Fold(group, claim, open_alerts[group.key]))
            plan.rearms.append((claim, open_alerts[group.key]))
        elif state is None:
            # New alert: the key's own id, or the deterministic successor of a resolved one.
            plan.creates.append(Create(group, claim, build_alert(group, alert_id, plan.now)))
            if alert_id != owner:
                plan.rearms.append((claim, alert_id))
        else:
            # Still resolved after MAX_SUCCESSOR_HOPS (re-arm lost repeatedly): fresh id, rare.
            fresh_id = new_uuid7()
            _log.warning(
                "alert_successor_chain_exhausted",
                extra={"rule_id": group.rule.id, "alert_id": alert_id, "successor_id": fresh_id},
            )
            plan.creates.append(Create(group, claim, build_alert(group, fresh_id, plan.now)))
            plan.rearms.append((claim, fresh_id))


def build_alert(group: MatchGroup, alert_id: str, now: datetime) -> Alert:
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
