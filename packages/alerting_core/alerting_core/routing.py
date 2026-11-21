"""Resolve which (recipient, channel) pairs get a delivery for a new alert, and apply throttling.

Pure functions over plain mappings so routing does not depend on the config registry.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from alerting_contracts.alerts import Alert
from alerting_contracts.config import (
    ChannelConfig,
    ChannelPreference,
    ChannelType,
    Recipient,
    Rule,
    Team,
)
from redis.asyncio import Redis
from redis.exceptions import RedisError

from alerting_core.durations import parse_duration
from alerting_core.logging import get_logger

log = get_logger(__name__)

# Channel types that need a recipient contact; webhook and ui need none.
DEFAULT_TIMEZONE = "Europe/Warsaw"
_CONTACT_FIELD = {ChannelType.email: "email", ChannelType.sms: "sms", ChannelType.phone: "phone"}


@dataclass(frozen=True)
class DeliveryTarget:
    """One delivery to create. `recipient_id` is None for the shared `ui` channel."""

    recipient_id: str | None
    channel_id: str
    channel_type: ChannelType


def _recipient_ids(rule: Rule, teams: Mapping[str, Team]) -> list[str]:
    ids: list[str] = []
    for team_id in rule.route.teams or [rule.team]:
        team = teams.get(team_id)
        if team is None:
            log.warning("routing_unknown_team", extra={"rule_id": rule.id, "team_id": team_id})
            continue
        ids.extend(team.on_call)
    ids.extend(rule.route.recipients)
    return list(dict.fromkeys(ids))


def _as_utc(moment: datetime) -> datetime:
    """A naive datetime is treated as UTC."""
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def _is_within(window: str, moment: datetime, timezone: str, rule_id: str, alert_id: str) -> bool:
    """Start inclusive, end exclusive; a window with start > end wraps midnight.

    A window with start == end never matches. An invalid timezone never raises: it falls back
    to Europe/Warsaw (the contract default), or UTC when that is missing too, and logs
    `routing_timezone_invalid`.
    """
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        log.warning(
            "routing_timezone_invalid",
            extra={"rule_id": rule_id, "alert_id": alert_id, "timezone": timezone},
        )
        try:
            zone = ZoneInfo(DEFAULT_TIMEZONE)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            zone = UTC  # no tz database installed at all
    start_text, end_text = window.split("-")
    start, end = time.fromisoformat(start_text), time.fromisoformat(end_text)
    local = _as_utc(moment).astimezone(zone).time().replace(tzinfo=None)
    if start == end:
        return False
    if start < end:
        return start <= local < end
    return local >= start or local < end


def _matching_preference(
    recipient: Recipient, alert: Alert, source: str | None
) -> ChannelPreference | None:
    for preference in recipient.channel_preferences:
        severities = preference.when.severities
        sources = preference.when.sources
        if severities and alert.severity not in severities:
            continue
        if sources and source not in sources:
            continue
        return preference
    return None


def _channel_ids_for(
    rule: Rule, recipient: Recipient, alert: Alert, source: str | None, now: datetime
) -> list[str]:
    """First matching preference wins. Outside its working hours `otherwise` is used; an empty
    `otherwise` means no channels from that preference (the recipient is not paged off-hours)."""
    preference = _matching_preference(recipient, alert, source)
    if preference is None:
        return rule.route.channels
    if preference.working_hours is None or _is_within(
        preference.working_hours, now, preference.timezone, rule.id, alert.id
    ):
        return preference.channels
    return preference.otherwise


def resolve_deliveries(
    rule: Rule,
    alert: Alert,
    *,
    teams: Mapping[str, Team],
    recipients: Mapping[str, Recipient],
    channels: Mapping[str, ChannelConfig],
    now: datetime,
    source: str | None = None,
) -> list[DeliveryTarget]:
    """Return the de-duplicated, stably ordered delivery targets for `alert`.

    `source` is the alert's normalized source, matched against `PreferenceMatch.sources`.
    The `ui` channel is emitted once with `recipient_id=None`.
    """
    targets: dict[DeliveryTarget, None] = {}

    def usable(channel_id: str, recipient_id: str | None) -> ChannelConfig | None:
        channel = channels.get(channel_id)
        if channel is None or not channel.enabled:
            extra = {
                "rule_id": rule.id,
                "alert_id": alert.id,
                "channel_id": channel_id,
                "recipient_id": recipient_id,
            }
            if channel is None:
                log.warning("routing_channel_unknown", extra=extra)
            else:
                log.info("routing_channel_disabled", extra=extra)
            return None
        return channel

    # ui is shared, so it is resolved from the rule's channels once, before any recipient.
    for channel_id in rule.route.channels:
        channel = usable(channel_id, None)
        if channel is not None and channel.type is ChannelType.ui:
            targets[DeliveryTarget(None, channel_id, channel.type)] = None

    for recipient_id in _recipient_ids(rule, teams):
        recipient = recipients.get(recipient_id)
        if recipient is None:
            log.warning(
                "routing_unknown_recipient",
                extra={"rule_id": rule.id, "recipient_id": recipient_id},
            )
            continue
        for channel_id in _channel_ids_for(rule, recipient, alert, source, now):
            channel = usable(channel_id, recipient_id)
            if channel is None:
                continue
            if channel.type is ChannelType.ui:
                targets[DeliveryTarget(None, channel_id, channel.type)] = None
                continue
            contact_field = _CONTACT_FIELD.get(channel.type)
            if contact_field is not None and not getattr(recipient.contacts, contact_field):
                log.info(
                    "routing_contact_missing",
                    extra={
                        "rule_id": rule.id,
                        "alert_id": alert.id,
                        "recipient_id": recipient_id,
                        "channel_id": channel_id,
                    },
                )
                continue
            targets[DeliveryTarget(recipient_id, channel_id, channel.type)] = None
    return list(targets)


async def check_throttle(
    redis: Redis,
    rule: Rule,
    targets: Iterable[DeliveryTarget],
    now: datetime,
    alert_id: str | None = None,
) -> tuple[list[DeliveryTarget], list[DeliveryTarget]]:
    """Split `targets` into (allowed, suppressed) by the rule's per-recipient throttle.

    One alert counts once per recipient regardless of how many channels it uses. `ui` targets
    are never throttled. A recipient over the limit has all of its targets suppressed.
    The caller (A-09) audits suppressed targets as `delivery_suppressed`. Fails open: if Redis
    is unavailable every target is allowed (an alert is never lost to a throttle outage).
    """
    target_list = list(targets)
    policy = rule.throttle
    if policy is None:
        return target_list, []

    period = max(1, int(parse_duration(policy.per)))
    period_start = int(_as_utc(now).timestamp() // period * period)
    recipient_ids = list(
        dict.fromkeys(t.recipient_id for t in target_list if t.recipient_id is not None)
    )
    if not recipient_ids:
        return target_list, []

    try:
        pipe = redis.pipeline(transaction=True)
        for recipient_id in recipient_ids:
            key = f"throttle:{rule.id}:{recipient_id}:{period_start}"
            pipe.incr(key)
            pipe.expire(key, period, nx=True)
        results = await pipe.execute()
    except RedisError:
        log.warning(
            "routing_throttle_unavailable",
            extra={"rule_id": rule.id, "alert_id": alert_id},
            exc_info=True,
        )
        return target_list, []
    over_limit = {
        recipient_id
        for index, recipient_id in enumerate(recipient_ids)
        if int(results[index * 2]) > policy.max_deliveries
    }

    allowed = [t for t in target_list if t.recipient_id not in over_limit]
    suppressed = [t for t in target_list if t.recipient_id in over_limit]
    return allowed, suppressed
