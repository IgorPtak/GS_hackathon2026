"""Rule preview: what would this draft rule have done with recent events?

A pure, deterministic simulation (no Redis, no DB, no clock except `now`). It mirrors the
processor: resolution events never open alerts, `dedup.fingerprint` overrides the profile
fingerprint, one dedup window per (rule, fingerprint) measured on `received_at`. A rule with a
`group` policy produces one summary per group window instead (same helpers as the flusher).
The Redis throttle is simulated in memory with the same per-recipient, per-period counters.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter

from alerting_contracts.alerts import Alert
from alerting_contracts.api import PreviewAlert, PreviewDeliveryCount, RulePreview
from alerting_contracts.config import (
    ChannelConfig,
    Recipient,
    Rule,
    SchemaProfile,
    Team,
)
from alerting_contracts.events import EventEnvelope

from ..config.registry import ConfigSnapshot
from ..durations import parse_duration_ms
from ..events import ProfileMatcher, compute_fingerprint
from ..grouping import GroupEvent, group_key, summarize_group
from ..ids import derived_uuid7
from ..routing import DeliveryTarget, resolve_deliveries
from ..templating import render_presentation
from .conditions import compile_condition
from .field_paths import build_context

MAX_SAMPLE_ALERTS = 20


@dataclass(slots=True)
class _OpenDedup:
    """The open dedup window of one fingerprint."""

    started_ms: int
    count: int = 1


@dataclass(slots=True)
class _OpenGroup:
    started_ms: int
    events: list[GroupEvent] = field(default_factory=list)


@dataclass(slots=True)
class _Simulation:
    """Mutable state of one preview run; never shared between runs."""

    rule: Rule
    teams: dict[str, Team]
    recipients: dict[str, Recipient]
    channels: dict[str, ChannelConfig]
    now: datetime
    window_ms: int
    throttle_period_s: int
    # Preview alerts, kept as the final (count updated) form; deliveries counted on creation.
    alerts: list[PreviewAlert] = field(default_factory=list)
    deliveries: Counter[tuple[str | None, str]] = field(default_factory=Counter)
    throttle_counts: Counter[tuple[str, int]] = field(default_factory=Counter)
    dedup: dict[str, tuple[_OpenDedup, PreviewAlert]] = field(default_factory=dict)
    groups: dict[str, _OpenGroup] = field(default_factory=dict)

    def route(self, alert: Alert, source: str | None, moment: datetime) -> None:
        """Count the deliveries of one created alert after the simulated throttle."""
        targets = resolve_deliveries(
            self.rule,
            alert,
            teams=self.teams,
            recipients=self.recipients,
            channels=self.channels,
            now=moment,
            source=source,
        )
        for target in self._after_throttle(targets, moment):
            self.deliveries[(target.recipient_id, target.channel_id)] += 1

    def _after_throttle(
        self, targets: list[DeliveryTarget], moment: datetime
    ) -> list[DeliveryTarget]:
        """Same semantics as `check_throttle`: one count per recipient per alert, `ui` exempt."""
        policy = self.rule.throttle
        if policy is None:
            return targets
        period_start = int(moment.timestamp() // self.throttle_period_s * self.throttle_period_s)
        recipient_ids = list(
            dict.fromkeys(t.recipient_id for t in targets if t.recipient_id is not None)
        )
        over_limit = set()
        for recipient_id in recipient_ids:
            key = (recipient_id, period_start)
            self.throttle_counts[key] += 1
            if self.throttle_counts[key] > policy.max_deliveries:
                over_limit.add(recipient_id)
        return [t for t in targets if t.recipient_id not in over_limit]


def _as_utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def _epoch_ms(moment: datetime) -> int:
    return int(_as_utc(moment).timestamp() * 1000)


def _to_preview(alert: Alert, count: int, member_count: int = 0) -> PreviewAlert:
    return PreviewAlert(
        title=alert.title,
        severity=alert.severity,
        fingerprint=alert.fingerprint,
        group_key=alert.group_key,
        is_group_summary=alert.is_group_summary,
        member_count=member_count,
        count=count,
        first_seen=alert.first_seen,
    )


def _alert_for(
    rule: Rule, event: GroupEvent, started_ms: int, now: datetime, count: int = 1
) -> Alert:
    return Alert(
        id=derived_uuid7(f"preview:{rule.id}:{event.fingerprint}", started_ms),
        rule_id=rule.id,
        team=rule.team,
        schema_profile_id=event.schema_profile_id,
        source_id=event.source_id,
        fingerprint=event.fingerprint,
        severity=event.severity,
        title=event.title,
        body=event.body,
        fields=event.fields,
        color=rule.present.color,
        count=count,
        first_seen=event.received_at,
        last_seen=event.received_at,
        runbook_id=rule.runbook,
        last_event=event.payload,
        updated_at=now,
    )


def _close_group(sim: _Simulation, key: str, window: _OpenGroup) -> None:
    deadline = datetime.fromtimestamp((window.started_ms + sim.window_ms) / 1000, UTC)
    alert_id = derived_uuid7(f"preview:{sim.rule.id}:{key}", window.started_ms)
    alert = summarize_group(sim.rule, key, window.events, alert_id, sim.now)
    sim.alerts.append(_to_preview(alert, alert.count, len(alert.group_members)))
    sim.route(alert, window.events[-1].source, deadline)


def _fold_group_event(sim: _Simulation, key: str, event: GroupEvent, at_ms: int) -> None:
    window = sim.groups.get(key)
    if window is not None and at_ms - window.started_ms > sim.window_ms:
        _close_group(sim, key, window)
        window = None
    if window is None:
        window = sim.groups[key] = _OpenGroup(at_ms)
    window.events.append(event)


def _fold_dedup_event(sim: _Simulation, event: GroupEvent, at_ms: int) -> None:
    open_window = sim.dedup.get(event.fingerprint)
    if open_window is not None and at_ms - open_window[0].started_ms <= sim.window_ms:
        window, preview = open_window
        window.count += 1
        preview.count = window.count
        return
    alert = _alert_for(sim.rule, event, at_ms, sim.now)
    preview = _to_preview(alert, 1)
    sim.alerts.append(preview)
    sim.dedup[event.fingerprint] = (_OpenDedup(at_ms), preview)
    sim.route(alert, event.source, event.received_at)


def preview_rule(
    rule: Rule,
    envelopes: list[EventEnvelope],
    snapshot: ConfigSnapshot,
    *,
    window_start: datetime,
    window_end: datetime,
    now: datetime | None = None,
    skipped_events: int = 0,
    max_events: int | None = None,
) -> RulePreview:
    """Simulate `rule` over `envelopes` (any order; sorted by `received_at` here).

    `skipped_events` (invalid stream entries) and `max_events` (the cap used to read them) only
    feed warnings. Raises ValueError when the rule's condition cannot be compiled.
    """
    started = perf_counter()
    now = now or datetime.now(UTC)
    try:
        matches = compile_condition(rule.when)
    except (ValueError, TypeError) as error:
        raise ValueError(f"rule {rule.id} has an invalid condition: {error}") from error

    profiles: dict[str, SchemaProfile] = dict(snapshot.of_kind("schema_profile"))
    matcher = ProfileMatcher(list(profiles.values()))
    sim = _Simulation(
        rule=rule,
        teams=dict(snapshot.of_kind("team")),
        recipients=dict(snapshot.of_kind("recipient")),
        channels=dict(snapshot.of_kind("channel")),
        now=now,
        window_ms=parse_duration_ms(rule.group.window if rule.group else rule.dedup.window),
        throttle_period_s=(
            max(1, parse_duration_ms(rule.throttle.per) // 1000) if rule.throttle else 1
        ),
    )

    matched = 0
    for envelope in sorted(envelopes, key=lambda item: item.received_at):
        payload = envelope.payload
        profile, _ = matcher.select_with_flag(payload)
        normalized = matcher.normalize(envelope, profile)
        if normalized.is_resolution:  # resolutions close alerts; they never open one
            continue
        context = build_context(payload, normalized.model_dump(mode="json"))
        if not matches(context):
            continue
        matched += 1
        fingerprint = (
            compute_fingerprint(context, rule.dedup.fingerprint)
            if rule.dedup.fingerprint
            else normalized.fingerprint
        )
        title, body, fields = render_presentation(rule.present, context)
        event = GroupEvent(
            fingerprint=fingerprint,
            title=title,
            body=body,
            severity=rule.severity or normalized.severity,
            fields=fields,
            received_at=envelope.received_at,
            sent_at=envelope.sent_at,
            source_id=envelope.source_id,
            schema_profile_id=profile.id,
            source=normalized.source,
            payload=payload,
        )
        at_ms = _epoch_ms(envelope.received_at)
        if rule.group is not None:
            _fold_group_event(sim, group_key(rule, context), event, at_ms)
        else:
            _fold_dedup_event(sim, event, at_ms)

    for key, window in sim.groups.items():
        _close_group(sim, key, window)

    warnings: list[str] = []
    if not rule.enabled:
        warnings.append("The rule is disabled; this preview shows what it would do once enabled.")
    if skipped_events:
        warnings.append(f"{skipped_events} invalid event(s) in the stream were skipped.")
    if max_events is not None and len(envelopes) >= max_events:
        warnings.append(f"Only the first {max_events} events were scanned (max_events cap).")
    if matched == 0:
        warnings.append("The rule matched none of the scanned events.")

    newest_first = sorted(sim.alerts, key=lambda alert: alert.first_seen, reverse=True)
    delivery_counts = [
        PreviewDeliveryCount(recipient_id=recipient_id, channel_id=channel_id, count=count)
        for (recipient_id, channel_id), count in sorted(
            sim.deliveries.items(), key=lambda item: (item[0][0] or "", item[0][1])
        )
    ]
    return RulePreview(
        window_start=window_start,
        window_end=window_end,
        events_scanned=len(envelopes),
        events_matched=matched,
        alerts_created=len(sim.alerts),
        deliveries=delivery_counts,
        sample_alerts=newest_first[:MAX_SAMPLE_ALERTS],
        duration_ms=int((perf_counter() - started) * 1000),
        warnings=warnings,
    )


__all__ = ["MAX_SAMPLE_ALERTS", "preview_rule"]
