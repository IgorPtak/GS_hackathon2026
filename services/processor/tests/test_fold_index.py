"""`dedup-count-index` lets orphan adoption find idle counters without SCAN."""

from alerting_core.dedup import (
    DEDUP_COUNT_INDEX,
    DedupClaim,
    find_idle_fold_counters,
    record_folds,
    take_fold_counts,
)


def claim(fingerprint: str) -> DedupClaim:
    return DedupClaim(
        rule_id="rule-a", fingerprint=fingerprint, window_ms=60_000, candidate_alert_id="a1"
    )


async def test_idle_counters_are_listed_and_taken_ones_leave_the_index(redis) -> None:
    await record_folds(redis, [(claim("f1"), 2), (claim("f2"), 3)])

    assert await find_idle_fold_counters(redis, idle_ms=60_000) == []  # written just now
    idle = await find_idle_fold_counters(redis, idle_ms=0)
    assert sorted(idle) == ["dedup-count:rule-a:f1", "dedup-count:rule-a:f2"]

    await take_fold_counts(redis, ["dedup-count:rule-a:f1"])  # flushed by a live tracker
    assert await find_idle_fold_counters(redis, idle_ms=0) == ["dedup-count:rule-a:f2"]
    assert await redis.zscore(DEDUP_COUNT_INDEX, "dedup-count:rule-a:f1") is None
