# services/processor

Consumes `events`: schema profile → rules → dedup/grouping → alert + outbox in one transaction.

Owner: track A. Tasks: A-09, A-16, A-18. See `docs/IMPLEMENTATION_PLAN.md`.

## Delivery semantics and known limits

- **Alerts: exactly once.** Alert ids come from the dedup key (`SET NX` with a pre-generated
  id) or, after a resolve, deterministically from the resolved alert, so redeliveries and
  replicas collide on `ON CONFLICT (id)`; outbox rows are written only by the inserting
  transaction.
- **Counts: at least once.** A batch redelivered after commit but before `XACK` folds its
  events again. Folds sit in Redis (`dedup-count:*`) until the 1 s flush; a SIGKILL leaves them
  there until the same key folds again (TTL: window + 60 s).
- **Throttle** counters are bumped before the transaction; an insert lost to a replica makes a
  throttle marginally stricter, never drops an alert.
- A batch that keeps failing (e.g. Postgres down for > ~2.5 min) is dead-lettered to
  `events-dlq` by `StreamConsumer` after 5 deliveries.
