# loadtest

Event generator and load-test scenarios.

Owner: track A. Tasks: A-05, A-21. See `docs/IMPLEMENTATION_PLAN.md`.

## Event generator (`generator.py`)

Sends a mix of the fixture events to ingest with open-loop pacing (send times are computed from the
start, not from responses), N async httpx workers with keep-alive, and an `X-Sent-At` header.

```bash
uv run python loadtest/generator.py --rate 200 --duration 10 --mix rates:1,settlements:1,pricing:1
uv run python loadtest/generator.py --rate 1000 --duration 60 --batch-size 20 --duplicate-ratio 0.2
uv run python loadtest/generator.py --dry-run --seed 1     # print sample payloads only
```

| Flag | Meaning |
|---|---|
| `--rate`, `--duration` | target msg/s and seconds (total = rate x duration) |
| `--mix` | weights, `rates:1,settlements:1,pricing:1` (to `rates-oms`, `settlements-engine`, pricing log) |
| `--duplicate-ratio` | re-send an exact earlier payload without an Idempotency-Key (dedup counts it) |
| `--unknown-ratio` | share of unknown-shape events sent to `generic-webhook` |
| `--batch-size` | above 1 uses `/api/v1/ingest/{source_id}/batch` per source |
| `--concurrency` | async workers and connections (default 32) |
| `--log-file` | pricing lines are appended here (default `data/logs/pricing_engine.log`) |
| `--pricing-via-http` | post pricing as parsed JSON to `generic-webhook` instead of the file |
| `--progress`, `--seed`, `--base-url` | progress interval (s), reproducibility, ingest URL |

Pricing lines go to the file tailed by the `pricing-log` source, so they only reach `events` if
ingest runs with that file mounted. Output includes sent, accepted, errors by status, achieved msg/s
and p50/p99 HTTP latency; the exit code is non-zero when more than 1% of requests fail.
