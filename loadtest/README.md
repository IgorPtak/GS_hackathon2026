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

## Scenarios (`scenarios.py`, task A-21)

Measures end-to-end behaviour against the running compose stack (ingest on `localhost:8001`,
Postgres on `localhost:5432`, Redis on `localhost:6379`; override with `INGEST_URL`,
`LOADTEST_DATABASE_URL`, `LOADTEST_REDIS_URL`). Every event is unique (`run_id` + sequence), matched
only by `config/rules/loadtest-events.yaml` (team `platform`, channels `ui` + `sms`), so each event
gives exactly 1 alert and 2 deliveries. The script saves that rule itself, so it works from any checkout.

```bash
uv run python loadtest/scenarios.py steady [--rate 200] [--duration 60]
uv run python loadtest/scenarios.py saturation [--replicas 1,2,4] [--rates 250,500,1000,2000] [--duration 20]
uv run python loadtest/scenarios.py dup-storm [--total 5000]
uv run python loadtest/scenarios.py gateway-down [--down-after 10] [--down-for 60]
uv run python loadtest/scenarios.py kill-processor [--kill-after 20]
```

Each run writes `loadtest/results/<name>-<timestamp>.json` and exits non-zero if `lost != 0`. Every
scenario restores the stack in a `finally` block (processor=1, delivery=1, mock-gateway started).
Method and results: `docs/load-test-results.md`.
Modules: `scenario_send.py` (events, sender, lag sampler), `scenario_measure.py` (Postgres
measurement), `scenario_stack.py` (docker scale/kill/restore, hardware).

## Generator inside the compose network

From the host, Docker Desktop port forwarding caps the generator around 420–460 msg/s and the
queueing shows up as seconds of latency. Run steady load from inside the network instead:

    docker run --rm --network alerting_default --user "$(id -u):$(id -g)" -v "$PWD":/work -w /work \
      -e INGEST_URL=http://ingest:8001 \
      -e LOADTEST_DATABASE_URL=postgresql://alerting:change-me-local-only@postgres:5432/alerting \
      -e LOADTEST_REDIS_URL=redis://redis:6379/0 \
      alerting-python:dev python loadtest/scenarios.py steady --rate 500 --duration 30

There is no docker CLI in that container, so scenarios that scale, stop or kill services
(saturation, gateway-down, kill-processor) still run on the host.

## CPU time per event (`cpu_bench.py`)

When the stack is near capacity, throughput varies across runs; measuring cgroup `cpu.stat`
(`usage_usec`) per accepted event below saturation compares optimizations cleanly:

    uv run python loadtest/cpu_bench.py --rate 500 --duration 30 --runs 3

It drives `scenarios.py steady --sync-stdin` inside the compose network, snapshots
`/sys/fs/cgroup/cpu.stat` on every pipeline container before and after the run, annotates each
`steady-*.json` with `cpu_per_event`, and writes a median summary to
`loadtest/results/cpu-bench-<timestamp>.json`.

## Postgres restart under load (`postgres_restart_test.sh`)

Verifies zero lost alerts when Postgres restarts mid-stream under load:

    ./loadtest/postgres_restart_test.sh

Runs an in-network `scenarios.py steady` pass at 100 msg/s for 60 s, restarts
`alerting-postgres-1` (`docker restart`) at `t = 15 s`, waits for settlement, prints the summary,
and exits non-zero if `steady` exits non-zero, the run did not settle, or `lost != 0`.

## Backend profiling (`profile_backends.py`)

Profiles Redis and Postgres work per accepted event around an in-network `scenarios.py steady`
run (`--sync-stdin`, default 250 msg/s for 30 s):

    uv run python loadtest/profile_backends.py

Before and after the load window it snapshots `redis-cli INFO commandstats`, Postgres
`pg_stat_statements` and `pg_stat_user_tables`. `compose.yaml` preloads the library; the profiler
runs `CREATE EXTENSION IF NOT EXISTS pg_stat_statements` itself before the first snapshot (no
migration), and falls back with a note in the report if it is unavailable. Prints top-15 per-command
(`calls/event`, `usec/event`) and per-query (`calls/event`, total and mean ms) tables and writes
`loadtest/results/backend-profile-<timestamp>.json`.

## Scale matrix and soak test (`soak_and_scale.py`)

Runs multi-replica scaling comparisons or sustained-load memory and lag checks from the host:

    uv run python loadtest/soak_and_scale.py --mode scale --rate 500 --duration 20
    uv run python loadtest/soak_and_scale.py --mode soak --rate 250 --duration 120

- `--mode scale`: steps through `(processor, delivery)` replica pairs (default `1:1,1:2,2:2,2:4`)
  with in-network `steady` runs and always restores `processor=1, delivery=2` in `finally`.
- `--mode soak`: runs a longer in-network `steady` pass while sampling container cgroup
  `memory.current`, `cpu.stat`, and Redis stream lag every 15 s, reporting memory min/max/growth
  (MB), CPU%, max lag, p50/p99, and `lost`.

Writes JSON results to `loadtest/results/scale-<timestamp>.json` or
`loadtest/results/soak-<timestamp>.json`.
