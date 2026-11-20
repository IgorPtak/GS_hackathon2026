# services/outbox_relay

Moves unrelayed `outbox` rows to `deliveries` / `runbook-jobs` with FOR UPDATE SKIP LOCKED.

Owner: track A. Tasks: A-11. See `docs/IMPLEMENTATION_PLAN.md`.
