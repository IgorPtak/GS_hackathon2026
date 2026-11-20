# services/delivery

Consumes `deliveries`; channel plugins, retries, DLQ, fallback, circuit breaker.

Owner: track A. Tasks: A-13. See `docs/IMPLEMENTATION_PLAN.md`.

## Outages and replay

- A channel that is unreachable (`ChannelUnavailableError`: connection refused, DNS, timeout,
  5xx) or behind an open circuit keeps retrying at up to `retry.max_backoff` without using up
  `retry.max_attempts`, until the delivery is `MAX_OUTAGE_SECONDS` (10 min) old. Only then it is
  dead-lettered and its `fallback_channel_id` takes over. Other errors count attempts as usual.
- Replay dead-lettered jobs after fixing the cause:
  `uv run python scripts/replay_dead_letters.py --delivery-id 9` (or `--all`, `--dry-run`).
  The `delivery-done:<id>` key keeps a replay idempotent.
