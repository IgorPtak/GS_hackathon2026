# Task brief — Flexible Alerting & Notification Service

> **RECONSTRUCTED PLACEHOLDER — replace with the official brief verbatim.**
> The official `docs/task.md` was not in the repository when the implementation plan was written.
> This file was rebuilt from the requirement-mapping table, demo script and appendix references in
> `docs/plan.md`. Requirement IDs (`R-…`, `J-…`) are ours and are used for traceability in
> `docs/IMPLEMENTATION_PLAN.md`. When the official brief arrives:
> 1. paste it below the line at the end of this file,
> 2. diff its sections 2.1–2.6, judging criteria and appendices against the lists here,
> 3. replace `contracts/fixtures/` with the official Appendix A events and Appendix B runbooks
>    (commit `feat(contracts): replace reconstructed fixtures with official appendix`),
> 4. add a task to the plan for every requirement that is not yet traced.

## Requirements (reconstructed from `docs/plan.md`, section "Requirement mapping")

### 2.1 Ingest
- **R-2.1a** At least two source types.
- **R-2.1b** Events from different teams have different schemas; onboarding a schema needs little or no code.

### 2.2 Rules
- **R-2.2a** Filters on any event field, combined with AND/OR.
- **R-2.2b** Routing and presentation configured per rule.
- **R-2.2c** Rules can be changed at runtime without a restart.

### 2.3 Notification
- **R-2.3a** Channels: email, SMS, phone call, UI.
- **R-2.3b** Per-recipient channel preferences, working hours and on-call.
- **R-2.3c** Delivery is reliable: retries, no lost notifications when a channel fails.

### 2.4 User interface
- **R-2.4a** Live feed of alerts.
- **R-2.4b** Acknowledge and resolve alerts.
- **R-2.4c** Create and edit rules.
- **R-2.4d** Manage channel preferences.
- **R-2.4e** From any alert, propose a fix to the rule or runbook; the proposal goes to the rule owner.

### 2.5 Noise reduction
- **R-2.5a** Deduplication of identical events.
- **R-2.5b** Throttling and grouping of related events.
- **R-2.5c** Grouped/deduplicated alerts are visible as such in the UI (collapsed, with drill-down).

### 2.6 Runbooks
- **R-2.6a** Runbooks in multiple formats, filled with values from the alert.
- **R-2.6b** Runbook presentation adapted per channel.
- **R-2.6c** Runbook actions can be executed; risky actions require human approval.
- **R-2.6d** Every action and decision is audited on the alert.
- **R-2.6e** Alerts auto-close when the source reports resolution (or after silence).
- **R-2.6f** *(optional)* Runbooks are updated automatically from what responders actually did.

### 4. Use of AI
- **R-4a** Describe how AI assistants were used; no production data or secrets sent to cloud tools.

### Submission
- **R-S1** Video (≈5 min) is the main basis of judging.
- **R-S2** Repository link; README with the commands to run the demo.
- **R-S3** README lists everything that is mocked.

## Judging criteria (reconstructed from the demo-script table in `docs/plan.md`)

| ID | Criterion |
|---|---|
| J-1 | Presentation |
| J-2 | UX / usability |
| J-3 | Flexibility (new sources, schemas, rules, channels without code) |
| J-4 | Runbooks |
| J-5 | Innovation |
| J-6 | Reliability (no lost alerts) |
| J-7 | Throughput and scalability (measured) |

## Appendix A — sample events (reconstructed)

See `contracts/fixtures/events/`:
1. Team Rates — `trade.rejected` JSON webhook event (`rates_trade_rejected.json`).
2. Team Settlements — `WORKFLOW_FAILED` JSON webhook event (`settlements_workflow_failed.json`).
3. Team Pricing — log line from a file (`pricing_engine.log`, parsed form in `pricing_price_stale.json`).

## Appendix B — sample runbooks (reconstructed)

See `contracts/fixtures/runbooks/`:
1. `trade-limit-breach.md` — Markdown.
2. `workflow-failed.yaml` — YAML with steps and an approval-gated escalation.
3. `pricing-stale-feed.txt` — free text.

---

<!-- Paste the official brief below this line. -->
