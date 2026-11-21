# Load-test results

First measurement (task A-21), 2026-11-20. Scenarios: `loadtest/scenarios.py` (see `loadtest/README.md`).
Raw data: `loadtest/results/*.json` (one file per run, every step with counters, latency, lag samples).

## Measurement design

- **Unique events.** Each event is a JSON body with `loadtest: true`, `run_id`, `seq`, `evt` (= `run_id-seq`)
  and `sent_ms` (host wall clock at build time). It goes to `POST /api/v1/ingest/generic-webhook`
  (ingest reads `config/sources/` only at startup, so a new source would need an ingest restart).
  The rule `loadtest-events` (`config/rules/loadtest-events.yaml`, team `platform`, channels `ui` + `sms`,
  `dedup.fingerprint: [evt]`) matches only load events. Each event gives exactly 1 alert and 2 deliveries
  (`ui` team-wide, `sms` to the platform on-call). The script saves this rule through the config save path.
- **Dup storm** is the exception: 5000 events share one `evt`, so the result must be 1 alert with count 5000.
- **sent** = events in HTTP requests; **accepted** = events answered 202; **processed** = alerts (and the sum of
  `alerts.count` for folds) of this `run_id` in Postgres; **delivered** = `deliveries` rows with status
  `delivered` for the run's alerts, primary rows only (`is_fallback = false`), one per alert and channel.
- **lost** = expected deliveries (2 x alerts) - delivered - covered by fallback, measured after waiting until every
  delivery row is terminal (timeout 90-180 s, reported as `is_settled`). It must be 0. `lost_strict_without_fallback`
  ignores fallbacks.
- **Fallbacks.** A primary row that ends `dead_lettered` is *covered* when the same alert has a fallback row
  (`is_fallback = true`) in status `delivered` (sms falls back to email, see `config/channels/sms.yaml`). Fallback
  rows are never counted as extra deliveries and fallbacks do not fall back again.
- **Latency** = `deliveries.delivered_at` - `sent_ms` of the event, for primary delivered rows, p50/p95/p99/max
  computed in Postgres (`percentile_cont`), also per channel type. The Postgres clock is compared with the host
  clock before each run and the difference is subtracted (Docker VM drift). The alert stores the last event of a fold,
  so latency is not reported for the dup storm. `prometheus_e2e_p99_s` (`alert_e2e_latency_seconds`, 5 min window)
  is stored when Prometheus answers on `localhost:9090`; it covers all traffic in the window, so it is only a cross-check.
- **Throughput.** Ingest msg/s = accepted / (first send to last response). Processed msg/s = alerts / (first to last
  `first_seen`). Lag is sampled every 250 ms from `XINFO GROUPS` (`events`/`processors`,
  `deliveries`/`delivery-workers`); `events_drained_after_s` = time from the last response until `events` has lag 0
  and no pending entries.
- **Max sustainable msg/s** = highest step where the events lag is 0 within 5 s after the step ends, p99 < 2 s,
  lost = 0 and no HTTP errors. Saturation stops climbing at the first failed step per replica count.
- The generator is open loop (send times come from the start time). Concurrency is 16 connections; batches of 10 are
  used from 1000 msg/s upward (not reached in this session).

## Hardware

Apple M4, 10 cores, 16 GB RAM, macOS 27.0.1 (arm64). Docker 29.9.2 (Docker Desktop VM: 10 CPUs, 7.7 GB RAM).
Everything (generator, stack, Postgres) shares this machine. Replicas unless stated: ingest 2 uvicorn workers,
processor 1, outbox-relay 1, delivery 1, mock-gateway 1.

## Results

| Scenario | Target msg/s | Processor / delivery | Sent | Delivered | Lost | p50 | p95 | p99 | max | Achieved ingest msg/s | File |
|---|---|---|---|---|---|---|---|---|---|---|---|
| steady 60 s | 200 | 1 / 1 | 12000 | 24000 / 24000 | **0** | 373 ms | 530 ms | 572 ms | 687 ms | 200.0 | `steady-20261120T205720.json` |
| dup-storm | 1000 (5000 events) | 1 / 1 | 5000 | 2 / 2 (1 alert, count 5000) | **0** | n/a | n/a | n/a | n/a | 688 | `dup-storm-20261120T205829.json` |
| gateway-down (mock-gateway stopped at t=10 s for 60 s) | 100 | 1 / 1 | 9000 | 18000 / 18000 | **0** | 1327 ms | 63.2 s | 69.4 s | 83.0 s | 100.0 | `gateway-down-20261120T205840.json` |
| kill-processor (`docker kill` at t=20 s) | 200 | 2 / 1 | 12000 | 24000 / 24000 | **0** | 405 ms | 673 ms | 1131 ms | 1468 ms | 200.0 | `kill-processor-20261120T210017.json` |

Saturation (20 s per step; delivery=1). A step is *sustainable* when `events` drained within 5 s, p99 < 2 s and lost = 0.

| Processors | 250 msg/s | 500 msg/s (target) | Max sustainable |
|---|---|---|---|
| 1 | drained, p99 1276 ms, sustainable | achieved 400/s, drained, p99 9323 ms, **not sustainable** | 250 |
| 2 | drained, p99 858 ms, sustainable | achieved 428/s, drained, p99 6057 ms, not sustainable | 250 |
| 4 | drained, p99 621 ms, sustainable | achieved 422/s, drained, p99 4823 ms, not sustainable | 250 |
| 2, delivery 4 (`saturation-20261120T210437.json`) | n/a | achieved 375/s, drained, p99 7052 ms, not sustainable | below 500 |

All saturation steps: sent = accepted = alerts, delivered = expected, lost = 0. Raw file for the table:
`saturation-20261120T210131.json`. The first run was never above 500 msg/s because the first failing step ends the climb.

## Observations

- **Zero lost alerts** in every scenario, including a 60 s sms gateway outage and a killed processor.
- **Gateway outage:** no sms job was dead-lettered. Jobs wait on the circuit breaker (cap `MAX_CIRCUIT_WAIT_SECONDS`
  = 600 s in `services/delivery/worker.py`) and all 9000 were delivered after the gateway came back, so the fallback
  path (email) was **not exercised**; `covered_by_fallback` is 0. Reaching it needs an outage above ten minutes or a job
  failing 6 attempts with the circuit closed. The `ui` channel was delayed too: `ui` p99 was about 10 s during the
  outage (head-of-line blocking in the single delivery worker while sms jobs wait), versus 0.3 s p50.
- **Backlog sits behind the processor.** At 500 msg/s the `events` lag stays small (max 36 entries, 0 with 4
  processors) while the `deliveries` lag reaches 3347 (delivery=1). With delivery=4 the `deliveries` lag drops
  to 430 but p99 stays about 7 s, and processed msg/s equals the achieved ingest rate. So latency builds between the
  processor commit and the delivery worker (outbox + relay, one relay instance), not in rule evaluation. This is
  an inference from stream lags; `outbox` rows with `relayed_at is null` were not sampled during the runs.
- **Ingest ceiling near 400-430 msg/s** with 16 unbatched connections (target 500 gave 375-428 msg/s, dup-storm
  target 1000 gave 688 msg/s; ingest http p50 15-20 ms, p99 about 210-260 ms at 500). It is not separated here
  whether the generator or ingest (2 workers) is the limit.
- **Kill-processor:** with a replica killed mid-run the events were all processed. The p99 was 1.1 s, max 1.5 s. An
  earlier run (discarded, lag sampler bug) showed max 34 s, which matches `XAUTOCLAIM` after 30 s idle when the
  killed consumer held pending entries; the final run's kill fell between reads.
- **Dup storm:** 5000 identical events gave 1 alert, `count` 5000, 2 deliveries.
- Settings that affect repeat runs: run ids are unique, so runs do not interfere; Mailpit receives mail only from
  fallbacks (none in these runs). The loadtest rule stays saved in `config_documents` after the run.

## Reproduce

```bash
docker compose up -d --build
uv run python loadtest/scenarios.py steady --duration 60
uv run python loadtest/scenarios.py dup-storm
uv run python loadtest/scenarios.py gateway-down
uv run python loadtest/scenarios.py kill-processor
uv run python loadtest/scenarios.py saturation          # about 8 minutes
```

## A-24 bottleneck measurement

Measured 2026-11-20 against the shared `alerting` stack (`processor=1`, `delivery=1`, `ingest` 2 uvicorn workers) using `uv run python loadtest/scenarios.py saturation --replicas 1 --rates 350,400,500`, plus a 500 msg/s repeat with `outbox-relay=2`. Raw data: `loadtest/results/a24-samples-20261120T212353.csv` (parallel sampling of unrelayed `outbox` rows, Redis `XINFO GROUPS` lag, and `docker stats --no-stream` CPU%, ~2 s effective cadence due to `docker stats` 1 s measurement window), `loadtest/results/saturation-20261120T212402.json` (`outbox-relay=1`), and `loadtest/results/saturation-20261120T212527.json` (`outbox-relay=2`).

### Relay configuration (`services/outbox_relay/`)

`services/outbox_relay/main.py` starts `run_relay(pool, redis, stop)` with defaults from `services/outbox_relay/relay.py`:

- `batch_size = 500` (`relay_batch` / `run_relay` default)
- `interval_seconds = 0.5` (500 ms poll sleep whenever `relayed < batch_size`; loops immediately only after a full batch of `>= 500` rows)
- `BATCH_TIMEOUT_SECONDS = 10.0`, `max_backoff_seconds = 5.0`

### Per-rate metrics

CPU% values below are active-window `avg / max` from `docker stats --no-stream` (100% = one core; `outbox-relay=2` sums both replicas). `Max deliveries lag` shows the 250 ms JSON sampler max (1-step CSV max in parentheses). All runs had `lost = 0` and `events_drained_after_s <= 0.20 s`.

| Target msg/s (relay replicas) | Achieved ingest msg/s | p50 | p99 | Max unrelayed outbox | Max deliveries lag | outbox-relay CPU% | processor CPU% | delivery CPU% | postgres CPU% | ingest CPU% |
|---|---|---|---|---|---|---|---|---|---|---|
| 350 (`relay=1`) | 350.0 | 469 ms | 719 ms | 358 | 367 (367) | 3.5 / 8.4 | 29.7 / 46.4 | 63.8 / 96.3 | 35.5 / 58.1 | 13.4 / 21.2 |
| 400 (`relay=1`) | 400.0 | 514 ms | 685 ms | 336 | 397 (361) | 3.3 / 10.8 | 38.6 / 47.5 | 74.6 / 88.5 | 61.4 / 126.3 | 18.4 / 29.4 |
| 500 (`relay=1`) | 485.7 | 1823 ms | 3495 ms | 494 | 2605 (2531) | 4.4 / 9.8 | 40.8 / 52.2 | **94.7 / 104.8** | 62.4 / 73.1 | 25.0 / 36.8 |
| 500 (`relay=2`) | 464.9 | 2146 ms | 3442 ms | 342 | 1593 (943) | 5.8 / 10.4 | 44.5 / 57.3 | **96.6 / 102.1** | 70.6 / 103.9 | 26.3 / 38.6 |

### Per-stage latency decomposition (Postgres timestamps)

Joining `deliveries`, `outbox`, and `alerts` (`NOT is_fallback`) breaks down `delivered_at - sent_ms` into three stages, including the earlier A-21 `processor=2, delivery=4` run (`sat-p2-r500-c0e9cb47`):

| Run | Config | `sent_ms` -> `alerts.first_seen` (p50 / p99) | `outbox.relayed_at - created_at` (p50 / p99 / max) | `delivered_at - relayed_at` (p50 / p99) | Total e2e p99 |
|---|---|---|---|---|---|
| `sat-p1-r350-54f84f1a` | `p=1 d=1 r=1` @ 350 | 0.3 / 3.7 ms | 255.5 / 512.8 / 563.7 ms | 208.7 / 621.7 ms | 718.6 ms |
| `sat-p1-r400-d3aa5c58` | `p=1 d=1 r=1` @ 400 | 0.3 / 11.2 ms | 256.5 / 512.5 / 558.2 ms | 247.5 / 580.7 ms | 684.8 ms |
| `sat-p1-r500-917ce83c` | `p=1 d=1 r=1` @ 500 | 356.9 / 1054.9 ms | 255.3 / 512.0 / 568.3 ms | 847.8 / 3178.7 ms | 3495.4 ms |
| `sat-p1-r500-0797e540` | `p=1 d=1 r=2` @ 500 | 1430.0 / 2014.7 ms | 201.8 / 491.2 / 510.0 ms | 544.0 / 1587.2 ms | 3442.1 ms |
| `sat-p2-r500-c0e9cb47` (A-21) | `p=2 d=4 r=1` @ 500 | **2890.9 / 6635.7 ms** | 200.2 / 522.1 / 588.3 ms | 140.8 / 424.3 ms | 7052.2 ms |

### Conclusion

1. **The single `delivery` worker saturates first** (at ~430–460 msg/s = ~860–920 deliveries/s), **not `outbox-relay`**.
   - At 500 msg/s (`relay=1`), `delivery` CPU is pinned at **94.7% avg / 104.8% max** (100% of one asyncio core), `deliveries` stream lag climbs monotonically to **2605**, and `delivered_at - relayed_at` reaches **3179 ms p99**.
   - Meanwhile `outbox-relay` CPU stays at **3.3–5.8% avg (<= 10.8% max)**, unrelayed `outbox` rows never build an unbounded queue (max **494**, strictly bounded by `rate * 2 deliveries * 0.5 s < batch_size`), and `outbox.relayed_at - created_at` stays flat at **~255 ms p50 / ~512 ms p99** across every rate from 350 to 500 msg/s.
   - Scaling `outbox-relay` to 2 replicas at 500 msg/s does **not** relieve saturation: `delivery` stays pinned at **96.6% avg / 102.1% max** and e2e p99 remains **3442 ms** (vs 3495 ms with `relay=1`).
2. **Why `delivery=4` still saw ~7 s p99 in A-21:** Postgres timestamps show `delivery=4` *did* eliminate delivery backlog (`delivered_at - relayed_at` p99 dropped to **424 ms**) and outbox wait stayed flat (**522 ms p99**). Instead, **6636 ms of the 7052 ms p99** was spent *before* `alerts.first_seen`: `loadtest/scenario_send.py` stamps `sent_ms` in the open-loop producer before 16 unbatched HTTP connections send to `ingest` (2 workers). When achieved ingest throughput fell to 375.2 msg/s (vs 500 target over 20 s = 26.65 s actual send time), events waited up to ~6.6 s in the client/HTTP queue before reaching `ingest` (`ingest_http_ms` p99 267 ms). The same effect explains the `1055 ms` (`relay=1`, achieved 485.7/s) and `2015 ms` (`relay=2`, achieved 464.9/s) pre-alert latency at 500 msg/s.
3. **Actionable takeaways:**
   - **To raise throughput above ~400–450 msg/s:** scale `delivery` (and avoid single-connection/unbatched HTTP ingest saturation with batching or more `ingest` workers/concurrency).
   - **To reduce baseline latency (~500 ms floor at all rates):** lower `interval_seconds` in `services/outbox_relay/relay.py` (currently `0.5 s`, adding ~255 ms p50 / ~512 ms p99 even when idle/moderate); scaling relay replicas is unnecessary at these rates.
   - `processor` (41–45% avg CPU, `events` lag <= 20, drain <= 0.20 s) and `postgres` (61–71% avg across 10 VM vCPUs) still have headroom at 500 msg/s.

### A-24 fixes and re-measurement

Changes: `outbox-relay` polls every 50 ms instead of 500 ms; `delivery` runs 2 replicas by default (`deploy.replicas` in compose; the load tests restore delivery=2).

| Run | Target / achieved msg/s | p50 | p95 | p99 | Lost |
|---|---|---|---|---|---|
| steady 30 s, before (A-21, 200 msg/s) | 200 / 200 | 373 ms | — | 572 ms | 0 |
| steady 30 s, after (`steady-c51a8d37`) | 350 / 350 | **56 ms** | 111 ms | **163 ms** | 0 |
| steady 30 s, after (`steady-f20ae006`) | 500 / 463 | 1516 ms | — | 2575 ms | 0 |

- Relay wait (`outbox.relayed_at - created_at`) fell from ~255 ms to ~29 ms p50.
- With 2 delivery replicas at 350 msg/s each uses 33–41% CPU and the `deliveries` lag stays 0.
- At 500 msg/s the generator only reaches ~463 msg/s: the latency is spent before ingest (open-loop client queue on 16 connections and 2 ingest workers), not in the pipeline. Next lever: more ingest workers or batched ingest.
- Saturation runs right after the rebuild were noisy (p99 ~2.9 s at 350 msg/s) while another agent's compose stack (`agent-a8f146d5f18928360-*`) was running on the same machine; the steady runs above are the clean numbers.

Max sustainable rate (p99 < 2 s, lag drained): **≥ 350 msg/s, below ~460 msg/s** on this laptop; the limit is now ingest, not the pipeline.

## Redis crash (hard kill) under load

`loadtest/redis_kill_test.sh <log>`: steady 200 msg/s for 60 s, `docker kill` Redis at t = 20 s, start it 3 s later.

| Redis persistence | Stream after restart | Accepted / alerts | Deliveries | Lost | p99 |
|---|---|---|---|---|---|
| RDB snapshots only, no volume (last snapshot 39 s old) | rolled back 3 253 entries | 11 118 / 11 118 | 21 858 / 22 236 | **378** (stuck `pending`) | 1.8 s |
| AOF `everysec` on a named volume | kept growing | 11 312 / 11 312 | 22 624 / 22 624 | **0** | 3.0 s |

- Alerts survived even without AOF: the processor had already written them to Postgres; replayed stream entries were absorbed by dedup and `ON CONFLICT`.
- The loss was relayed-but-undelivered jobs: the outbox row said relayed, the `deliveries` entry vanished with the snapshot rollback.
- Events not accepted during the outage (~700–900) got an error, not a 202, so the source knows to retry.
- `everysec` can still lose up to ~1 s on a crash. The relay reconciler (`services/outbox_relay/reconcile.py`) closes that gap from Postgres: every 10 s it re-publishes deliveries still `pending` 30 s after relaying. Started after the RDB-only run above, it found exactly the 378 lost jobs and all 22 236 deliveries of that run ended `delivered`.

### Lost delivery jobs (deterministic)

`loadtest/lost_jobs_test.sh <log>`: steady 100 msg/s for 60 s; at t = 15 s delivery is stopped for 3 s and the `deliveries` stream is trimmed to 0, wiping 717 unread jobs.
Result (`steady-9b6d7c12`): 12 000 / 12 000 delivered, lost = 0, 755 re-published by the reconciler (717 wiped + jobs in flight at the stop, absorbed by `delivery-done`), p50 40 ms, p99 37.7 s = 30 s stale threshold + up to 10 s tick.

## Host vs in-network generator

Same stack (processor 1, delivery 2, AOF on), steady 30 s:

| Generator | Target | Achieved msg/s | p50 | p99 | Lost | File |
|---|---|---|---|---|---|---|
| host (Docker Desktop port forwarding) | 500 | 423 | 3 972 ms | 5 601 ms | 0 | `steady-20261120T225111.json` |
| inside compose network | 500 | 500 | **81 ms** | **482 ms** | 0 | `steady-20261120T225449.json` |
| inside compose network | 1000 | 670 | 8 800 ms | 17 388 ms | 0 | `steady-20261120T225530.json` |

The earlier "~460 msg/s limit" was the host-to-VM path, not the pipeline. The 1000 msg/s in-network run saw 1 HTTP 503 (`29 999 / 30 000` accepted, `59 998 / 59 998` delivered, `lost = 0`). At a 1000 msg/s target,
CPU at t = 20 s: postgres 130 %, each delivery replica 86 %, ingest 59 % (2 workers), processor 53 %,
mock-gateway 34 %, redis 32 %, outbox-relay 10 %.

## Per-request CPU savings (`sniffio` and `--no-access-log`)

`py-spy` profiles at 600 msg/s (`loadtest/results/profiles/{ingest,delivery}.svg`) pointed to two per-request overheads:

1. `httpcore` imports `sniffio` on every request; without `sniffio` installed, every failed import scanned `sys.path` (~8.5 % of `delivery` CPU). Added `sniffio` to `pyproject.toml`.
2. Uvicorn's per-request access log took ~9 % of `ingest` CPU. Added `--no-access-log` to `ingest` in `compose.yaml` and updated `alerting_core.logging.configure_logging` so it preserves an already-disabled `uvicorn.access` logger.

To verify these ~8–9 % savings without the ~30 % overload variance seen at 500–1000 msg/s (where Apple M4's 4 P-cores spill onto 6 E-cores and queues build), `loadtest/cpu_bench.py` reads cgroup `/sys/fs/cgroup/cpu.stat` (`usage_usec`) across 3 in-network `steady` runs at 250 msg/s × 30 s (~1.9 cores total, `max_deliveries_lag` 32–54 on the branch, total spread 5.4 %; `delivery` 5.5 %, `ingest` 7.1 %).

Same stack (`processor=1`, `delivery=2`, `ingest` 2 workers, AOF on, identical generator image), `main` (`40be0d1`, `cpu-bench-20261121T002255.json`) vs `perf/in-network-loadgen` (`cpu-bench-20261121T001239.json`):

| Service (replicas) | Changed? | `main` median (`µs/evt`) | Branch median (`µs/evt`) | Raw delta | Normalized vs `mock-gateway` |
|---|---|---|---|---|---|
| **`delivery` (2)** | yes (`sniffio`) | 3135.5 | 2510.1 | −625.4 (−19.9 %) | **−11.5 %** (`6.21× → 5.49×`) |
| **`ingest` (1)** | yes (`--no-access-log`) | 832.6 | 686.4 | −146.2 (−17.6 %) | **−8.7 %** (`1.65× → 1.50×`) |
| `processor` (1) | no (control) | 1484.0 | 1322.5 | −161.5 (−10.9 %) | −2.0 % (`2.91× → 2.85×`) |
| `mock-gateway` (1) | no (control) | 505.8 | 456.9 | −48.9 (−9.7 %) | 0.0 % (reference) |
| `outbox-relay` (1) | no (control) | 231.7 | 205.2 | −26.5 (−11.4 %) | −8.2 % (`0.48× → 0.44×`) |
| `postgres` (1) | no (control) | 2430.5 | 2001.7 | −428.8 (−17.6 %) | n/a (checkpoints/autovacuum) |
| `redis` (1) | no (control) | 950.5 | 869.3 | −81.2 (−8.5 %) | n/a (AOF in background) |
| **total (8)** | — | **9795.7** | **7950.2** | **−1845.5 (−18.8 %)** | — |

- **Control-group normalization:** untouched services (`mock-gateway`, `processor`, `outbox-relay`) shifted ~10 % between sessions from host clock/P-core/E-core scheduling (plus a background spike in `main` run 3 to `p99 = 1713 ms` and `4400.6 µs` on `delivery`, absorbed by the 3-run median). Comparing the median per-run `service / mock-gateway` ratio removes that drift (`delivery / mock-gateway` stays tight: `6.24, 6.20, 6.21` on `main` vs `5.49, 5.56, 5.49` on the branch), confirming **−11.5 %** on `delivery` and **−8.7 %** on `ingest`, closely matching `py-spy`.
- **Latency and reliability:** median `p50 / p99` fell from `53.2 / 382.5 ms` (`main`) to `47.6 / 180.1 ms` (branch), with `lost = 0` in all 6 runs (branch run 1 had 1 client `ReadError` with `7499 / 7500` accepted and `14 998 / 14 998` delivered, and 0 error logs in `ingest`).
- **Reproduce:** `uv run python loadtest/cpu_bench.py --rate 250 --duration 30 --runs 3`.

## Ported swarm work (A-34), per step

`loadtest/cpu_bench.py --rate 250 --duration 30 --runs 3` after rebuilding the stack from each commit (quiet machine, no parallel builds). `processor` is unchanged by every step, so values are normalized as `service / processor` (median µs per event) to remove host drift between sessions:

| Step | delivery | redis | postgres | total (8 services) | cpu_bench p99 |
|---|---|---|---|---|---|
| before port (`a73fe8b`) | 1.849 | 0.684 | 1.522 | 6.045 | 225 ms |
| 1–3: per-stage metrics, `pg_stat_statements`, quieter mock-gateway | 1.945 | 0.715 | 1.480 | 5.935 | 261 ms |
| 4: team events published in one pipeline | 1.845 | **0.459** | 1.618 | 5.790 | 193 ms |
| 5: claim/complete attempts in one Lua round trip, `FOR UPDATE` only for dead letters | **1.634** | 0.429 | **1.391** | **5.392** | 122 ms |

- Step 4 cuts Redis CPU per event by ~36 %; step 5 cuts delivery by ~11 % and Postgres by ~14 % against step 4; all steps together −11 % total CPU per event.
- `lost = 0` in every run. After step 5: `loadtest/postgres_restart_test.sh` (Postgres restarted at t = 15 s under 100 msg/s: 12 000 / 12 000 delivered) and `loadtest/lost_jobs_test.sh` (724 unread jobs wiped: lost 0).
- Single steady 500 msg/s runs swung p99 between 0.2 and 2.4 s across all four commits, so they are not used for comparison.
