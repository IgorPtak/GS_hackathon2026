"""Unit tests for backend profiling, delta calculations, and soak/scale summaries."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import profile_backends as pb  # noqa: E402
import soak_and_scale as sas  # noqa: E402


def test_parse_redis_commandstats_parses_subcommands_and_ignores_headers() -> None:
    raw = (
        "# Commandstats\r\n"
        "cmdstat_xadd:calls=120,usec=3600,usec_per_call=30.00,rejected_calls=0,failed_calls=0\r\n"
        "cmdstat_xinfo|groups:calls=10,usec=500,usec_per_call=50.00\r\n"
        "cmdstat_ping:calls=2,usec=4,usec_per_call=2.00\r\n\r\n"
    )
    parsed = pb.parse_redis_commandstats(raw)
    assert parsed["xadd"] == {"calls": 120, "usec": 3600, "rejected_calls": 0, "failed_calls": 0}
    assert parsed["xinfo|groups"] == {"calls": 10, "usec": 500}
    assert parsed["ping"] == {"calls": 2, "usec": 4}


def test_compute_redis_delta_sorts_truncates_and_validates() -> None:
    before = {
        "xadd": {"calls": 10, "usec": 100},
        "ping": {"calls": 5, "usec": 10},
        "get": {"calls": 20, "usec": 200},
    }
    after = {
        "xadd": {"calls": 1010, "usec": 50100},
        "ping": {"calls": 5, "usec": 10},
        "get": {"calls": 520, "usec": 10200},
        "evalsha": {"calls": 2000, "usec": 80000},
        **{f"cmd{i}": {"calls": i, "usec": i * 10} for i in range(1, 20)},
    }
    res = pb.compute_redis_delta(before, after, accepted=1000, top_n=15)
    assert len(res["commands"]) == 15
    assert res["commands"][0] == {
        "command": "evalsha",
        "calls": 2000,
        "usec": 80000,
        "calls_per_event": 2.0,
        "usec_per_event": 80.0,
        "usec_per_call": 40.0,
    }
    assert [c["command"] for c in res["commands"][:3]] == ["evalsha", "xadd", "get"]
    expected_calls = 2000 + 1000 + 500 + sum(range(1, 20))
    assert res["total_calls"] == expected_calls
    assert res["total_calls_per_event"] == round(expected_calls / 1000, 3)

    with pytest.raises(ValueError, match="accepted"):
        pb.compute_redis_delta(before, after, accepted=0)
    with pytest.raises(ValueError, match="negative commandstats delta"):
        pb.compute_redis_delta({"xadd": {"calls": 5000, "usec": 100}}, after, accepted=100)


def test_compute_pg_statements_delta() -> None:
    before = [
        {"queryid": "101", "query": "SELECT 1", "calls": 10, "total_exec_time": 5.0, "rows": 10},
        {"queryid": "102", "query": "SELECT idle", "calls": 3, "total_exec_time": 1.0, "rows": 3},
    ]
    after = [
        {
            "queryid": "101",
            "query": "SELECT 1",
            "calls": 510,
            "total_exec_time": 105.0,
            "rows": 510,
        },
        {"queryid": "102", "query": "SELECT idle", "calls": 3, "total_exec_time": 1.0, "rows": 3},
        {
            "queryid": "202",
            "query": "INSERT INTO alerts",
            "calls": 500,
            "total_exec_time": 250.0,
            "rows": 500,
        },
    ]
    rows = pb.compute_pg_statements_delta(before, after, accepted=500, top_n=15)
    assert [r["queryid"] for r in rows] == ["202", "101"]
    assert rows[0]["calls_per_event"] == 1.0
    assert rows[0]["total_ms"] == 250.0
    assert rows[0]["mean_ms"] == 0.5
    assert rows[0]["ms_per_event"] == 0.5
    assert rows[0]["rows_per_call"] == 1.0
    assert rows[1]["total_ms"] == 100.0
    assert rows[1]["mean_ms"] == 0.2

    with pytest.raises(ValueError, match="accepted"):
        pb.compute_pg_statements_delta(before, after, accepted=0)
    with pytest.raises(ValueError, match="negative pg_stat_statements"):
        pb.compute_pg_statements_delta(after, before, accepted=100)


def test_compute_pg_tables_delta() -> None:
    tbl_before = [
        {"relname": "alerts", "seq_scan": 1, "idx_scan": 10, "n_tup_ins": 5, "n_live_tup": 5},
        {"relname": "unused", "seq_scan": 2, "idx_scan": 0, "n_tup_ins": 0},
    ]
    tbl_after = [
        {
            "relname": "alerts",
            "seq_scan": 1,
            "idx_scan": 510,
            "n_tup_ins": 505,
            "n_live_tup": 505,
            "n_dead_tup": 2,
        },
        {"relname": "unused", "seq_scan": 2, "idx_scan": 0, "n_tup_ins": 0},
    ]
    tbl_delta = pb.compute_pg_tables_delta(tbl_before, tbl_after)
    assert len(tbl_delta) == 1
    assert tbl_delta[0]["table"] == "alerts"
    assert tbl_delta[0]["idx_scan"] == 500
    assert tbl_delta[0]["n_tup_ins"] == 500
    assert tbl_delta[0]["n_dead_tup"] == 2


def test_parse_scale_pairs_and_cgroup_sample() -> None:
    assert sas.parse_scale_pairs("1:1, 1:2, 2:4") == [(1, 1, 1, 1), (1, 2, 1, 1), (2, 4, 1, 1)]
    assert sas.parse_scale_pairs("2:2:2, 4:4:3:2") == [(2, 2, 2, 1), (4, 4, 3, 2)]
    for bad in ("", "1", "0:1", "1:0"):
        with pytest.raises(ValueError):
            sas.parse_scale_pairs(bad)

    parsed = sas.parse_cgroup_sample("104857600\n---\nusage_usec 2500000\nuser_usec 2000000\n")
    assert parsed == {"memory_bytes": 104857600, "usage_usec": 2500000}
    with pytest.raises(ValueError, match="separator"):
        sas.parse_cgroup_sample("104857600\nusage_usec 100\n")


def test_summarize_soak_samples_memory_trend_cpu_and_lag() -> None:
    assert sas.linear_slope([0.0], [1.0]) == 0.0
    assert sas.linear_slope([0.0, 1.0, 2.0], [10.0, 12.0, 14.0]) == pytest.approx(2.0)

    mib = 1024 * 1024
    mapping = {
        "alerting-ingest-1": "ingest",
        "alerting-delivery-1": "delivery",
        "alerting-delivery-2": "delivery",
    }

    def sample(
        t_s: float, im: int, ic: int, dm: tuple[int, int], dc: int, lg: tuple[int, int]
    ) -> dict:
        return {
            "t_s": t_s,
            "containers": {
                "alerting-ingest-1": {"memory_bytes": im * mib, "usage_usec": ic},
                "alerting-delivery-1": {"memory_bytes": dm[0] * mib, "usage_usec": dc},
                "alerting-delivery-2": {"memory_bytes": dm[1] * mib, "usage_usec": dc},
            },
            "lag": {
                "events_lag": lg[0],
                "events_pending": 1,
                "deliveries_lag": lg[1],
                "deliveries_pending": 5,
            },  # fmt: skip
        }

    samples = [
        sample(0.0, 100, 1_000_000, (150, 150), 2_000_000, (0, 0)),
        sample(30.0, 110, 7_000_000, (160, 170), 17_000_000, (12, 45)),
        sample(60.0, 104, 10_000_000, (160, 160), 23_000_000, (3, 10)),
    ]
    out = sas.summarize_soak_samples(samples, mapping)
    assert out["sample_count"] == 3 and out["duration_sampled_s"] == 60.0
    assert out["by_service"]["ingest"] == {
        "replicas": 1, "min_mb": 100.0, "max_mb": 110.0, "start_mb": 100.0, "end_mb": 104.0,
        "growth_mb": 4.0, "slope_mb_per_min": 4.0, "avg_cpu_pct": 15.0, "peak_cpu_pct": 20.0,
    }  # fmt: skip
    assert out["by_service"]["delivery"] == {
        "replicas": 2, "min_mb": 300.0, "max_mb": 330.0, "start_mb": 300.0, "end_mb": 320.0,
        "growth_mb": 20.0, "slope_mb_per_min": 20.0, "avg_cpu_pct": 70.0, "peak_cpu_pct": 100.0,
    }  # fmt: skip
    assert out["total"]["growth_mb"] == 24.0 and out["total"]["avg_cpu_pct"] == 85.0
    assert out["lag"]["max_events_lag"] == 12 and out["lag"]["max_deliveries_lag"] == 45

    with pytest.raises(ValueError, match="at least one"):
        sas.summarize_soak_samples([], mapping)
