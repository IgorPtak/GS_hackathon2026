# Fixtures

Synthetic sample events and runbooks, one per demo team. Used by unit tests,
`scripts/smoke_test.py`, the load generator and `docs/demo.md`.

| File | Team | Source | Expected rule / runbook |
|---|---|---|---|
| `events/rates_trade_rejected.json` | rates | `rates-oms` (webhook) | `rates-large-rejections` → runbook `trade-limit-breach` |
| `events/settlements_workflow_failed.json` | settlements | `settlements-engine` (webhook) | `settlements-workflow-failed` → runbook `workflow-failed` |
| `events/pricing_engine.log` | pricing | `pricing-log` (log_tail) | `pricing-stale-feed` (grouped per instrument) → runbook `pricing-stale-feed` |
| `events/pricing_price_stale.json` | pricing | — | parsed form of the first log line |
| `events/alertmanager_firing.json`, `alertmanager_resolved.json` | platform | `alertmanager` | `platform-alertmanager`, auto-resolve |
| `events/unknown_payments.json` | — | `generic-webhook` | none → unknown-schema inbox |
