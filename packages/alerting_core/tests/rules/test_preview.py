"""Rule preview: pure simulation of dedup, grouping, routing and throttling."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from alerting_contracts.config import (
    ChannelConfig,
    Recipient,
    Rule,
    SchemaProfile,
    Team,
)
from alerting_contracts.events import EventEnvelope
from alerting_core.config.registry import ConfigSnapshot
from alerting_core.rules.preview import preview_rule

T0 = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

PROFILE = SchemaProfile.model_validate(
    {
        "id": "pricing-log",
        "priority": 10,
        "match": {"field": "service", "op": "eq", "value": "pricing-engine"},
        "fields": {
            "type": {"const": "pricing.log"},
            "source": {"const": "pricing-log"},
            "severity": {"path": "level", "value_map": {"ERROR": "error"}, "default": "info"},
            "entity": "instrument",
        },
        "fingerprint": ["instrument", "feed"],
        "resolution": {"field": "msg", "op": "eq", "value": "Price recovered"},
    }
)


def snapshot(recipients: list[dict[str, Any]] | None = None) -> ConfigSnapshot:
    recipients = recipients or [
        {"id": "kasia", "display_name": "Kasia", "contacts": {"email": "k@example.com"}},
        {"id": "adam", "display_name": "Adam", "contacts": {"email": "a@example.com"}},
    ]
    return ConfigSnapshot(
        documents={
            "schema_profile": {PROFILE.id: PROFILE},
            "team": {
                "pricing": Team(
                    id="pricing", display_name="Pricing", on_call=[r["id"] for r in recipients]
                )
            },
            "recipient": {r["id"]: Recipient.model_validate(r) for r in recipients},
            "channel": {
                "ui": ChannelConfig(id="ui", type="ui"),
                "email": ChannelConfig(id="email", type="email"),
            },
        }
    )


def make_rule(**overrides: Any) -> Rule:
    data: dict[str, Any] = {
        "id": "pricing-stale-feed",
        "team": "pricing",
        "when": {"field": "msg", "op": "regex", "value": "^Price stale"},
        "present": {"title": "Stale {{instrument}}"},
        "dedup": {"window": "60s"},
    }
    data.update(overrides)
    return Rule.model_validate(data)


def envelope(
    index: int, seconds: float, instrument: str = "XS1", msg: str = "Price stale"
) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"E{index:08d}",
        source_id="pricing-log",
        source_type="log_tail",
        received_at=T0 + timedelta(seconds=seconds),
        payload={
            "service": "pricing-engine",
            "level": "ERROR",
            "instrument": instrument,
            "feed": "bloomberg",
            "msg": msg,
        },
    )


def run(rule: Rule, envelopes: list[EventEnvelope], **kwargs: Any):  # noqa: ANN202
    return preview_rule(
        rule,
        envelopes,
        kwargs.pop("snap", None) or snapshot(),
        window_start=T0,
        window_end=T0 + timedelta(hours=1),
        now=T0,
        **kwargs,
    )


def test_identical_events_fold_into_one_alert_with_count() -> None:
    preview = run(make_rule(), [envelope(i, i * 0.1) for i in range(100)])

    assert preview.events_scanned == 100
    assert preview.events_matched == 100
    assert preview.alerts_created == 1
    assert preview.sample_alerts[0].count == 100
    assert preview.sample_alerts[0].title == "Stale XS1"


def test_events_two_windows_apart_open_two_alerts() -> None:
    preview = run(make_rule(), [envelope(1, 0), envelope(2, 10), envelope(3, 130)])

    assert preview.alerts_created == 2
    newest, oldest = preview.sample_alerts
    assert (newest.count, oldest.count) == (1, 2)  # newest first


def test_dedup_fingerprint_override_merges_different_feeds() -> None:
    rule = make_rule(dedup={"window": "60s", "fingerprint": ["instrument"]})
    other_feed = envelope(2, 1)
    other_feed.payload["feed"] = "reuters"

    assert run(make_rule(), [envelope(1, 0), other_feed]).alerts_created == 2
    assert run(rule, [envelope(1, 0), other_feed]).alerts_created == 1


def test_resolution_events_never_open_alerts() -> None:
    rule = make_rule(when={"field": "service", "op": "eq", "value": "pricing-engine"})
    preview = run(rule, [envelope(1, 0, msg="Price recovered")])

    assert preview.alerts_created == 0
    assert preview.events_matched == 0


def test_group_rule_produces_one_summary_per_instrument_window() -> None:
    rule = make_rule(group={"by": ["instrument"], "window": "10s"})
    events = [envelope(i, (i % 100) * 0.1, f"INS{i % 5}") for i in range(1000)]
    preview = run(rule, events)

    assert preview.alerts_created == 5
    assert all(alert.is_group_summary for alert in preview.sample_alerts)
    assert all(alert.count == 200 for alert in preview.sample_alerts)
    assert all(alert.member_count == 1 for alert in preview.sample_alerts)
    assert all(alert.group_key for alert in preview.sample_alerts)


def test_group_window_closes_and_a_later_event_opens_a_new_summary() -> None:
    rule = make_rule(group={"by": ["instrument"], "window": "10s"})
    preview = run(rule, [envelope(1, 0), envelope(2, 5), envelope(3, 30)])

    assert preview.alerts_created == 2


def test_deliveries_are_counted_per_recipient_and_channel() -> None:
    events = [envelope(1, 0, "A"), envelope(2, 1, "B"), envelope(3, 2, "C")]
    preview = run(make_rule(), events)

    counts = {(d.recipient_id, d.channel_id): d.count for d in preview.deliveries}
    assert counts == {(None, "ui"): 3, ("adam", "email"): 3, ("kasia", "email"): 3}


def test_throttle_reduces_deliveries_per_recipient_but_not_ui() -> None:
    rule = make_rule(throttle={"max_deliveries": 2, "per": "10m"})
    events = [envelope(i, i, f"INS{i}") for i in range(5)]
    preview = run(rule, events)

    counts = {(d.recipient_id, d.channel_id): d.count for d in preview.deliveries}
    assert preview.alerts_created == 5
    assert counts == {(None, "ui"): 5, ("adam", "email"): 2, ("kasia", "email"): 2}


def test_throttle_period_resets() -> None:
    rule = make_rule(throttle={"max_deliveries": 1, "per": "1m"})
    # Alerts at 0 s and 1 s share a minute bucket only when the bucket does not roll over.
    events = [envelope(1, 0, "A"), envelope(2, 1, "B"), envelope(3, 120, "C")]
    preview = run(rule, events)

    counts = {(d.recipient_id, d.channel_id): d.count for d in preview.deliveries}
    assert counts[("kasia", "email")] == 2


def test_sample_alerts_are_capped_at_20_newest_first() -> None:
    events = [envelope(i, i, f"INS{i}") for i in range(30)]
    preview = run(make_rule(), events)

    assert preview.alerts_created == 30
    assert len(preview.sample_alerts) == 20
    seen = [alert.first_seen for alert in preview.sample_alerts]
    assert seen == sorted(seen, reverse=True)


def test_disabled_rule_is_previewed_with_a_warning() -> None:
    preview = run(make_rule(enabled=False), [envelope(1, 0)])

    assert preview.alerts_created == 1
    assert any("disabled" in warning for warning in preview.warnings)


def test_warnings_for_zero_matches_skipped_and_cap() -> None:
    preview = run(make_rule(), [envelope(1, 0, msg="ok")], skipped_events=3, max_events=1)

    assert preview.events_matched == 0
    joined = " | ".join(preview.warnings)
    assert "3 invalid" in joined and "max_events" in joined and "none" in joined


def test_uncompilable_condition_raises_value_error() -> None:
    rule = make_rule(when={"field": "msg", "op": "regex", "value": "(a+)+" + "b" * 600})

    with pytest.raises(ValueError, match="pricing-stale-feed"):
        run(rule, [envelope(1, 0)])


def test_preview_is_deterministic_ignoring_duration() -> None:
    rule = make_rule(group={"by": ["instrument"], "window": "10s"})
    events = [envelope(i, i * 0.3, f"INS{i % 7}") for i in range(300)]
    first = run(rule, events).model_dump(exclude={"duration_ms"})
    second = run(rule, list(reversed(events))).model_dump(exclude={"duration_ms"})

    assert first == second


@pytest.mark.slow
def test_fifty_thousand_events_preview_in_under_three_seconds() -> None:
    rule = make_rule(
        when={
            "all": [
                {"field": "level", "op": "in", "value": ["ERROR", "CRITICAL"]},
                {"field": "msg", "op": "regex", "value": "^Price stale"},
                {"field": "normalized.severity", "op": "eq", "value": "error"},
            ]
        },
        group={"by": ["instrument"], "window": "10s"},
    )
    events = [envelope(i, i * 0.05, f"INS{i % 50}") for i in range(50_000)]

    preview = run(rule, events)

    print(f"preview of 50k events: {preview.duration_ms} ms")
    assert preview.events_matched == 50_000
    assert preview.duration_ms < 3000
