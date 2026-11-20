"""Pure group-window helpers shared by the processor flusher and the rule preview."""

from datetime import UTC, datetime, timedelta

import pytest
from alerting_contracts.config import Rule
from alerting_core.grouping import (
    GroupEvent,
    group_alert_id,
    group_key,
    group_member,
    split_group_member,
    summarize_group,
)
from alerting_core.rules import build_context

T0 = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def pricing_rule() -> Rule:
    return Rule.model_validate(
        {
            "id": "pricing-stale-feed",
            "team": "pricing",
            "when": {"field": "normalized.type", "op": "eq", "value": "price.stale"},
            "present": {"title": "Stale {{instrument}}", "color": "yellow"},
            "group": {"by": ["instrument", "venue"], "window": "10s"},
        }
    )


def event(fingerprint: str, seconds: int, severity: str = "warning") -> GroupEvent:
    return GroupEvent(
        fingerprint=fingerprint,
        title=f"Stale {fingerprint}",
        severity=severity,
        received_at=T0 + timedelta(seconds=seconds),
        source_id="pricing-log",
        schema_profile_id="pricing-log",
        payload={"instrument": "XS1", "n": seconds},
    )


def test_group_key_reads_group_by_values_and_tolerates_missing() -> None:
    rule = pricing_rule()
    full = group_key(rule, build_context({"instrument": "XS1", "venue": 7}, {}))
    partial = group_key(rule, build_context({"instrument": "XS1"}, {}))

    assert full != partial
    assert full.startswith("XS1") and "7" in full


def test_member_round_trip_keeps_colons_in_the_key() -> None:
    assert split_group_member(group_member("pricing-stale-feed", "a:b")) == (
        "pricing-stale-feed",
        "a:b",
    )


def test_summary_aggregates_members_by_fingerprint() -> None:
    events = [event("a", 3), event("b", 1, "critical"), event("a", 2)]

    alert = summarize_group(pricing_rule(), "XS1", events, group_alert_id("k", 1), T0)

    assert alert.is_group_summary and alert.group_key == "XS1"
    assert alert.count == 3
    assert [(m.fingerprint, m.count) for m in alert.group_members] == [("a", 2), ("b", 1)]
    assert alert.severity == "critical"
    assert alert.first_seen == T0 + timedelta(seconds=1)
    assert alert.last_event == {"instrument": "XS1", "n": 3}


def test_group_alert_id_is_deterministic_per_window() -> None:
    assert group_alert_id("k", 1) == group_alert_id("k", 1)
    assert group_alert_id("k", 1) != group_alert_id("k2", 1)


def test_empty_group_is_rejected() -> None:
    with pytest.raises(ValueError):
        summarize_group(pricing_rule(), "XS1", [], group_alert_id("k", 1), T0)
