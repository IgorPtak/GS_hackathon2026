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
