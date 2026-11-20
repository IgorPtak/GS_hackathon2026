"""Pure-logic unit tests for the automated demo rehearsal helpers (no live stack)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from demo_rehearsal_helpers import (  # noqa: E402
    FatalPollError,
    RehearsalError,
    SceneResult,
    build_batches,
    format_markdown_table,
    fresh_alertmanager_events,
    fresh_rates_event,
    fresh_settlements_event,
    make_stricter_rates_rule,
    parse_only_scenes,
    poll_until,
)


def test_fresh_rates_event_varies_fingerprint_and_trade_id() -> None:
    event_a, reason_a, trade_a = fresh_rates_event("aaaa1111", "email")
    event_b, reason_b, trade_b = fresh_rates_event("bbbb2222", "email")
    assert reason_a != reason_b
    assert trade_a != trade_b
    assert event_a["payload"]["reason"] == reason_a
    assert event_a["payload"]["tradeId"] == trade_a
    assert event_a["payload"]["desk"] == "rates"
    assert event_a["payload"]["notional"] == 25_000_000


def test_fresh_settlements_event_varies_workflow_id() -> None:
    event_a, wf_a = fresh_settlements_event("1111aaaa", "outage")
    event_b, wf_b = fresh_settlements_event("2222bbbb", "outage")
    assert wf_a != wf_b
    assert event_a["workflowId"] == wf_a
    assert event_a["eventType"] == "WORKFLOW_FAILED"


def test_fresh_alertmanager_events_share_instance_and_fingerprint_per_run() -> None:
    firing_a, resolved_a, instance_a = fresh_alertmanager_events("abcd1234")
    firing_b, resolved_b, instance_b = fresh_alertmanager_events("ef567890")
    assert instance_a != instance_b
    assert firing_a["alerts"][0]["labels"]["instance"] == instance_a
    assert resolved_a["alerts"][0]["labels"]["instance"] == instance_a
    assert firing_a["alerts"][0]["fingerprint"] == resolved_a["alerts"][0]["fingerprint"]
    assert firing_a["alerts"][0]["fingerprint"] != firing_b["alerts"][0]["fingerprint"]
    assert firing_a["status"] == "firing"
    assert resolved_a["status"] == "resolved"


def test_make_stricter_rates_rule_tightens_notional_without_mutating_input() -> None:
    rule = {
        "id": "rates-large-rejections",
        "when": {
            "all": [
                {"field": "payload.desk", "op": "eq", "value": "rates"},
                {"field": "payload.notional", "op": "gt", "value": 10_000_000},
            ]
        },
    }
    stricter = make_stricter_rates_rule(rule)
    assert rule["when"]["all"][1]["value"] == 10_000_000
    assert stricter["when"]["all"][1]["value"] >= 100_000_000


def test_build_batches_splits_evenly_and_with_remainder() -> None:
    sample = {"payload": {"reason": "DUP"}}
    batches = build_batches(sample, total=500, batch_size=100)
    assert [len(b) for b in batches] == [100, 100, 100, 100, 100]
    assert sum(len(b) for b in batches) == 500

    uneven = build_batches(sample, total=250, batch_size=100)
    assert [len(b) for b in uneven] == [100, 100, 50]
    assert build_batches(sample, total=0, batch_size=100) == []

    # Mutating one item does not mutate copies.
    batches[0][0]["payload"]["reason"] = "CHANGED"
    assert batches[0][1]["payload"]["reason"] == "DUP"


def test_build_batches_rejects_invalid_arguments() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        build_batches({}, total=-1, batch_size=10)
    with pytest.raises(ValueError, match="at least 1"):
        build_batches({}, total=5, batch_size=0)


def test_poll_until_returns_when_probe_succeeds() -> None:
    now = 0.0
    attempts = 0

    def clock() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        now += seconds

    def probe() -> str | None:
        nonlocal attempts
        attempts += 1
        return "ready" if attempts == 3 else None

    result = poll_until(
        probe, timeout=5.0, interval=0.5, reason="never ready", clock=clock, sleep=sleep
    )
    assert result == "ready"
    assert attempts == 3
    assert now == 1.0


def test_poll_until_times_out_with_reason_and_last_error() -> None:
    now = 0.0
    sleeps: list[float] = []

    def clock() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    def failing_probe() -> None:
        raise RehearsalError("still pending")

    with pytest.raises(RehearsalError, match=r"alert never arrived within 1\.2s.*still pending"):
        poll_until(
            failing_probe,
            timeout=1.2,
            interval=0.5,
            reason="alert never arrived",
            clock=clock,
            sleep=sleep,
        )
    assert sleeps == pytest.approx([0.5, 0.5, 0.2])


def test_poll_until_stops_immediately_on_fatal_error() -> None:
    calls = 0

    def fatal_probe() -> None:
        nonlocal calls
        calls += 1
        raise FatalPollError("duplicate alert created")

    with pytest.raises(FatalPollError, match="duplicate alert created"):
        poll_until(
            fatal_probe,
            timeout=10.0,
            interval=0.5,
            reason="unused",
            clock=lambda: 0.0,
            sleep=lambda _: None,
        )
    assert calls == 1


def test_format_markdown_table_renders_pass_fail_and_escapes_pipes() -> None:
    results = [
        SceneResult(name="health", passed=True, detail="all 200", duration=0.123),
        SceneResult(name="metrics_summary", passed=False, detail="404 | old image", duration=1.5),
    ]
    table = format_markdown_table(results)
    lines = table.splitlines()
    assert lines[0] == "| Scene | Status | Duration | Detail |"
    assert lines[1] == "| --- | --- | ---: | --- |"
    assert lines[2] == "| health | PASS | 0.12s | all 200 |"
    assert lines[3] == "| metrics_summary | FAIL | 1.50s | 404 \\| old image |"
    assert lines[-1] == "Result: 1/2 scenes passed."


def test_parse_only_scenes_validates_and_preserves_order() -> None:
    valid = ["health", "rule_preview", "dedup_500"]
    assert parse_only_scenes(None, valid) == valid
    assert parse_only_scenes("dedup_500,health", valid) == ["health", "dedup_500"]
    with pytest.raises(ValueError, match="unknown scene"):
        parse_only_scenes("health,nope", valid)


def test_anna_expects_email_only_outside_warsaw_working_hours() -> None:
    from datetime import UTC, datetime

    from demo_rehearsal import anna_expects_email

    assert anna_expects_email(datetime(2026, 11, 20, 12, 0, tzinfo=UTC)) is False  # 13:00 Warsaw
    assert anna_expects_email(datetime(2026, 11, 20, 21, 0, tzinfo=UTC)) is True  # 22:00 Warsaw
