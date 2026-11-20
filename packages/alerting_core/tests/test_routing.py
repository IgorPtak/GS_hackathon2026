"""Routing: recipients, channel preferences, working hours, ui-once, throttle (real Redis DB 10)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from alerting_contracts.alerts import Alert
from alerting_contracts.config import ChannelConfig, ChannelType, Recipient, Rule, Team
from alerting_core.routing import DeliveryTarget, check_throttle, resolve_deliveries
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

DAY = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)  # 10:00 Europe/Warsaw (CEST)
NIGHT = datetime(2026, 7, 1, 21, 0, tzinfo=UTC)  # 23:00 Europe/Warsaw

ANNA = Recipient.model_validate(
    {
        "id": "anna",
        "display_name": "Anna",
        "teams": ["rates"],
        "contacts": {"email": "anna@example.com", "sms": "+48600000000", "phone": "+48600000000"},
        "channel_preferences": [
            {
                "when": {"severities": ["error", "critical"], "sources": ["rates-oms"]},
                "channels": ["sms", "phone"],
                "working_hours": "08:00-20:00",
                "timezone": "Europe/Warsaw",
                "otherwise": ["email"],
            }
        ],
    }
)
TEAMS = {"rates": Team(id="rates", display_name="Rates", on_call=["anna"])}
CHANNELS = {
    channel_id: ChannelConfig(id=channel_id, type=ChannelType(channel_id))
    for channel_id in ("ui", "email", "sms", "phone", "webhook")
}


def make_rule(**overrides: Any) -> Rule:
    data: dict[str, Any] = {
        "id": "r1",
        "team": "rates",
        "when": {"field": "payload.x", "op": "exists"},
        "route": {"channels": ["ui", "email"]},
        "present": {"title": "t"},
    }
    data.update(overrides)
    return Rule.model_validate(data)


def make_alert(severity: str = "error") -> Alert:
    return Alert.model_validate(
        {
            "id": "a1",
            "rule_id": "r1",
            "team": "rates",
            "schema_profile_id": "p",
            "source_id": "s",
            "fingerprint": "f",
            "severity": severity,
            "title": "t",
            "first_seen": DAY,
            "last_seen": DAY,
            "last_event": {},
            "updated_at": DAY,
        }
    )


def resolve(
    rule: Rule,
    *,
    now: datetime = DAY,
    severity: str = "error",
    source: str | None = "rates-oms",
    recipients: dict[str, Recipient] | None = None,
    channels: dict[str, ChannelConfig] | None = None,
    teams: dict[str, Team] | None = None,
) -> list[DeliveryTarget]:
    return resolve_deliveries(
        rule,
        make_alert(severity),
        teams=teams or TEAMS,
        recipients=recipients if recipients is not None else {"anna": ANNA},
        channels=channels or CHANNELS,
        now=now,
        source=source,
    )


def pairs(targets: list[DeliveryTarget]) -> list[tuple[str | None, str]]:
    return [(t.recipient_id, t.channel_id) for t in targets]


def test_anna_error_by_day_gets_sms_and_phone_plus_ui() -> None:
    assert pairs(resolve(make_rule())) == [(None, "ui"), ("anna", "sms"), ("anna", "phone")]


def test_anna_error_at_night_gets_email() -> None:
    assert pairs(resolve(make_rule(), now=NIGHT)) == [(None, "ui"), ("anna", "email")]


def test_non_matching_severity_uses_route_channels() -> None:
    assert pairs(resolve(make_rule(), severity="warning")) == [(None, "ui"), ("anna", "email")]


def test_non_matching_source_uses_route_channels() -> None:
    assert pairs(resolve(make_rule(), source="other")) == [(None, "ui"), ("anna", "email")]


def test_window_start_inclusive_end_exclusive() -> None:
    start = datetime(2026, 7, 1, 6, 0, tzinfo=UTC)  # 08:00 Warsaw
    end = datetime(2026, 7, 1, 18, 0, tzinfo=UTC)  # 20:00 Warsaw
    assert ("anna", "sms") in pairs(resolve(make_rule(), now=start))
    assert pairs(resolve(make_rule(), now=end)) == [(None, "ui"), ("anna", "email")]


def test_midnight_wrapping_window() -> None:
    night_owl = ANNA.model_copy(
        update={
            "channel_preferences": [
                ANNA.channel_preferences[0].model_copy(update={"working_hours": "22:00-06:00"}),
            ]
        }
    )
    at_23 = resolve(make_rule(), now=NIGHT, recipients={"anna": night_owl})
    at_10 = resolve(make_rule(), now=DAY, recipients={"anna": night_owl})
    assert ("anna", "sms") in pairs(at_23)
    assert pairs(at_10) == [(None, "ui"), ("anna", "email")]


def test_empty_otherwise_yields_no_recipient_channels() -> None:
    quiet = ANNA.model_copy(
        update={
            "channel_preferences": [
                ANNA.channel_preferences[0].model_copy(update={"otherwise": []})
            ]
        }
    )
    assert pairs(resolve(make_rule(), now=NIGHT, recipients={"anna": quiet})) == [(None, "ui")]


def test_ui_emitted_once_with_no_recipient() -> None:
    bob = Recipient(id="bob", display_name="Bob", contacts={"email": "b@example.com"})
    teams = {"rates": Team(id="rates", display_name="Rates", on_call=["anna", "bob"])}
    targets = resolve(
        make_rule(), severity="info", recipients={"anna": ANNA, "bob": bob}, teams=teams
    )
    assert [t for t in pairs(targets) if t[1] == "ui"] == [(None, "ui")]
    assert pairs(targets) == [(None, "ui"), ("anna", "email"), ("bob", "email")]


def test_ui_in_preference_channels_is_not_per_recipient() -> None:
    pref = ANNA.channel_preferences[0].model_copy(update={"channels": ["ui", "sms"]})
    anna = ANNA.model_copy(update={"channel_preferences": [pref]})
    rule = make_rule(route={"channels": ["email"]})
    assert pairs(resolve(rule, recipients={"anna": anna})) == [(None, "ui"), ("anna", "sms")]


def test_disabled_channel_is_skipped() -> None:
    channels = {**CHANNELS, "sms": CHANNELS["sms"].model_copy(update={"enabled": False})}
    assert pairs(resolve(make_rule(), channels=channels)) == [(None, "ui"), ("anna", "phone")]


def test_unknown_channel_is_skipped() -> None:
    channels = {key: value for key, value in CHANNELS.items() if key != "phone"}
    assert pairs(resolve(make_rule(), channels=channels)) == [(None, "ui"), ("anna", "sms")]


def test_missing_contact_is_skipped() -> None:
    no_phone = ANNA.model_copy(
        update={"contacts": ANNA.contacts.model_copy(update={"phone": None})}
    )
    assert pairs(resolve(make_rule(), recipients={"anna": no_phone})) == [
        (None, "ui"),
        ("anna", "sms"),
    ]


def test_unknown_recipient_is_skipped() -> None:
    rule = make_rule(route={"channels": ["email"], "recipients": ["ghost", "anna"]})
    assert pairs(resolve(rule, severity="info")) == [("anna", "email")]


def test_recipient_listed_twice_is_deduplicated() -> None:
    rule = make_rule(route={"channels": ["email"], "recipients": ["anna"]})
    assert pairs(resolve(rule, severity="info")) == [("anna", "email")]


def test_route_teams_override_rule_team() -> None:
    teams = {**TEAMS, "ops": Team(id="ops", display_name="Ops", on_call=["bob"])}
    bob = Recipient(id="bob", display_name="Bob", contacts={"email": "b@example.com"})
    rule = make_rule(route={"teams": ["ops"], "channels": ["email"]})
    assert pairs(resolve(rule, recipients={"anna": ANNA, "bob": bob}, teams=teams)) == [
        ("bob", "email")
    ]


def with_window(window: str, timezone: str = "Europe/Warsaw") -> Recipient:
    pref = ANNA.channel_preferences[0].model_copy(
        update={"working_hours": window, "timezone": timezone}
    )
    return ANNA.model_copy(update={"channel_preferences": [pref]})


def is_working_hours(now: datetime, window: str = "08:00-20:00", tz: str = "Europe/Warsaw") -> bool:
    targets = resolve(make_rule(), now=now, recipients={"anna": with_window(window, tz)})
    return ("anna", "sms") in pairs(targets)


@pytest.mark.parametrize("timezone", ["", "../x", "Nope/Zone"])
def test_invalid_timezone_falls_back_to_warsaw(timezone: str) -> None:
    assert is_working_hours(DAY, tz=timezone)  # 10:00 Warsaw
    assert not is_working_hours(NIGHT, tz=timezone)  # 23:00 Warsaw


def test_dst_changes_the_local_hour() -> None:
    # 07:00 UTC is 08:00 CET before 2026-03-29 and 09:00 CEST after; 06:00 UTC flips the other way.
    assert is_working_hours(datetime(2026, 3, 28, 7, 0, tzinfo=UTC))
    assert not is_working_hours(datetime(2026, 3, 28, 6, 59, tzinfo=UTC))
    assert is_working_hours(datetime(2026, 3, 30, 6, 0, tzinfo=UTC))
    assert not is_working_hours(datetime(2026, 3, 30, 5, 59, tzinfo=UTC))
    # Autumn: 2026-10-25 clocks go back; 19:00 UTC is 20:00 CET (outside), 18:59 is inside.
    assert is_working_hours(datetime(2026, 10, 24, 17, 59, tzinfo=UTC))
    assert not is_working_hours(datetime(2026, 10, 24, 18, 0, tzinfo=UTC))
    assert is_working_hours(datetime(2026, 10, 26, 18, 59, tzinfo=UTC))
    assert not is_working_hours(datetime(2026, 10, 26, 19, 0, tzinfo=UTC))


def test_midnight_wrap_boundaries() -> None:
    assert not is_working_hours(datetime(2026, 1, 15, 5, 0, tzinfo=UTC), "22:00-06:00")  # 06:00
    assert is_working_hours(datetime(2026, 1, 15, 4, 59, tzinfo=UTC), "22:00-06:00")
    assert is_working_hours(datetime(2026, 1, 15, 21, 0, tzinfo=UTC), "22:00-06:00")  # 22:00
    assert not is_working_hours(datetime(2026, 1, 15, 20, 59, tzinfo=UTC), "22:00-06:00")


def test_other_timezone_changes_result_for_same_instant() -> None:
    assert is_working_hours(DAY, tz="Europe/Warsaw")  # 10:00
    assert not is_working_hours(DAY, tz="America/New_York")  # 04:00


def test_equal_start_and_end_never_matches() -> None:
    assert not is_working_hours(DAY, "10:00-10:00")


def test_naive_now_is_treated_as_utc() -> None:
    assert is_working_hours(datetime(2026, 7, 1, 8, 0))  # 10:00 Warsaw
    assert not is_working_hours(datetime(2026, 7, 1, 21, 0))


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url("redis://localhost:6379/10")
    try:
        await client.ping()
    except Exception:
        pytest.skip("Redis on localhost:6379 is not running (docker compose up -d redis)")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


async def test_throttle_without_policy_allows_everything(redis: Redis) -> None:
    targets = resolve(make_rule())
    assert await check_throttle(redis, make_rule(), targets, DAY) == (targets, [])


async def test_throttle_allows_max_then_suppresses_and_resets(redis: Redis) -> None:
    rule = make_rule(throttle={"max_deliveries": 2, "per": "1h"})
    targets = resolve(rule)  # ui + anna sms + anna phone: one count per alert
    for _ in range(2):
        allowed, suppressed = await check_throttle(redis, rule, targets, DAY)
        assert allowed == targets
        assert suppressed == []

    allowed, suppressed = await check_throttle(redis, rule, targets, DAY)
    assert pairs(allowed) == [(None, "ui")]  # ui is never throttled
    assert pairs(suppressed) == [("anna", "sms"), ("anna", "phone")]

    next_period = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
    allowed, suppressed = await check_throttle(redis, rule, targets, next_period)
    assert allowed == targets
    assert suppressed == []


async def test_throttle_key_has_ttl(redis: Redis) -> None:
    rule = make_rule(throttle={"max_deliveries": 1, "per": "60s"})
    await check_throttle(redis, rule, resolve(rule), DAY)
    keys = [key async for key in redis.scan_iter("throttle:r1:anna:*")]
    assert len(keys) == 1
    assert 0 < await redis.ttl(keys[0]) <= 60


async def test_throttle_fails_open_when_redis_is_down() -> None:
    rule = make_rule(throttle={"max_deliveries": 1, "per": "1h"})
    broken = MagicMock()
    broken.pipeline.side_effect = RedisConnectionError("down")
    targets = resolve(rule)
    assert await check_throttle(broken, rule, targets, DAY, alert_id="a1") == (targets, [])
