# services/outbox_relay

Moves unrelayed `outbox` rows to `deliveries` / `runbook-jobs` with FOR UPDATE SKIP LOCKED.

