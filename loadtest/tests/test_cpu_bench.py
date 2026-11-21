"""Unit tests for CPU-per-event measurement and in-network scenario guards."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import cpu_bench  # noqa: E402
import scenarios  # noqa: E402


def test_parse_cpu_stat_valid_and_missing_usage() -> None:
    parsed = cpu_bench.parse_cpu_stat(
        "usage_usec 123456\nuser_usec 100000\nsystem_usec 23456\nnr_periods 0\n"
    )
    assert parsed["usage_usec"] == 123456
    assert parsed["user_usec"] == 100000
    assert parsed["system_usec"] == 23456

    with pytest.raises(ValueError, match="usage_usec"):
        cpu_bench.parse_cpu_stat("user_usec 100\nsystem_usec 20\n")


def test_compute_cpu_per_event_aggregates_replicas_and_validates() -> None:
    before = {
        "alerting-ingest-1": {
            "usage_usec": 1_000_000,
            "user_usec": 800_000,
            "system_usec": 200_000,
        },
        "alerting-delivery-1": {
            "usage_usec": 2_000_000,
            "user_usec": 1_500_000,
            "system_usec": 500_000,
        },
        "alerting-delivery-2": {
            "usage_usec": 3_000_000,
            "user_usec": 2_200_000,
            "system_usec": 800_000,
        },
    }
    after = {
        "alerting-ingest-1": {
            "usage_usec": 2_500_000,
            "user_usec": 2_000_000,
            "system_usec": 500_000,
        },
        "alerting-delivery-1": {
            "usage_usec": 5_000_000,
            "user_usec": 3_900_000,
            "system_usec": 1_100_000,
        },
        "alerting-delivery-2": {
            "usage_usec": 7_000_000,
            "user_usec": 5_400_000,
            "system_usec": 1_600_000,
        },
    }
    mapping = {
        "alerting-ingest-1": "ingest",
        "alerting-delivery-1": "delivery",
        "alerting-delivery-2": "delivery",
    }
    out = cpu_bench.compute_cpu_per_event(before, after, mapping, accepted=1000, wall_s=10.0)
    assert out["total_delta_usec"] == 8_500_000
    assert out["total_usec_per_event"] == 8500.0
    assert out["by_service"]["ingest"] == {
        "replicas": 1,
        "delta_usec": 1_500_000,
        "usec_per_event": 1500.0,
        "avg_cpu_pct": 15.0,
    }
    assert out["by_service"]["delivery"] == {
        "replicas": 2,
        "delta_usec": 7_000_000,
        "usec_per_event": 7000.0,
        "avg_cpu_pct": 70.0,
    }
    assert out["by_container"]["alerting-delivery-1"]["usec_per_event"] == 3000.0
    assert out["by_container"]["alerting-delivery-2"]["usec_per_event"] == 4000.0

    with pytest.raises(ValueError, match="accepted"):
        cpu_bench.compute_cpu_per_event(before, after, mapping, accepted=0, wall_s=10.0)

    bad_after = {**after, "alerting-ingest-1": {"usage_usec": 500_000}}
    with pytest.raises(ValueError, match="negative usage_usec"):
        cpu_bench.compute_cpu_per_event(before, bad_after, mapping, accepted=1000, wall_s=10.0)


def test_summarize_runs_medians_and_lost_flag() -> None:
    def make_run(ingest_u: float, deliv_u: float, p50: float, p99: float, lost: int) -> dict:
        return {
            "lost": lost,
            "is_settled": True,
            "p50_ms": p50,
            "p99_ms": p99,
            "cpu_per_event": {
                "total_usec_per_event": ingest_u + deliv_u,
                "by_service": {
                    "ingest": {"usec_per_event": ingest_u, "avg_cpu_pct": ingest_u / 10},
                    "delivery": {"usec_per_event": deliv_u, "avg_cpu_pct": deliv_u / 10},
                },
            },
        }

    runs = [
        make_run(100.0, 220.0, 40.0, 120.0, 0),
        make_run(120.0, 200.0, 45.0, 150.0, 0),
        make_run(110.0, 210.0, 42.0, 130.0, 0),
    ]
    summary = cpu_bench.summarize_runs(runs, ("ingest", "delivery"))
    assert summary["by_service"]["ingest"]["median_usec_per_event"] == 110.0
    assert summary["by_service"]["delivery"]["median_usec_per_event"] == 210.0
    assert summary["total"]["median_usec_per_event"] == 320.0
    assert summary["median_p50_ms"] == 42.0
    assert summary["median_p99_ms"] == 130.0
    assert summary["all_zero_lost"] is True

    runs_with_loss = runs[:-1] + [make_run(110.0, 210.0, 42.0, 130.0, 1)]
    summary_with_loss = cpu_bench.summarize_runs(runs_with_loss, ("ingest", "delivery"))
    assert summary_with_loss["all_zero_lost"] is False


async def test_scenarios_positive_int_and_docker_guard(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert scenarios._positive_int("16") == 16
    for bad in ("0", "-1"):
        with pytest.raises(argparse.ArgumentTypeError):
            scenarios._positive_int(bad)

    monkeypatch.setattr(scenarios.stack, "has_docker", lambda: False)
    args = SimpleNamespace(
        scenario="gateway-down",
        rate=None,
        duration=None,
        base_url="http://ingest:8001",
        concurrency=16,
        sync_stdin=False,
    )
    rc = await scenarios.main_async(args)
    assert rc == 2
    assert "requires the docker CLI" in capsys.readouterr().err
