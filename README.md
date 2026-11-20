# Flexible Alerting & Notification Service

Teams change alerts without fear and without code, and the AI runs locally.

> Status: planning complete, implementation starting. See `docs/IMPLEMENTATION_PLAN.md`.

## Quickstart

```bash
git clone <repo> && cd <repo>
cp .env.example .env
docker compose up
```

TODO (D-01): UI, Grafana and Mailpit URLs; demo commands.

## What is mocked

TODO (D-01): fill in from the running system.

| Real-world part | In this demo | To make it real |
|---|---|---|
| Email provider | Mailpit (real SMTP, nothing leaves the machine) | Change SMTP settings in `config/channels/email.yaml` |
| SMS and phone provider | Mock gateway + "Phone" tab (phone simulator), reply `APPROVE <code>` | One new channel plugin (e.g. Twilio) |
| Runbook action targets (`retry_workflow`, `restart_service`, `open_ticket`) | Mock gateway that logs calls and can "fix" the problem | Point the action config at real endpoints |
| Slack / Teams / PagerDuty | Generic webhook channel to a local receiver | Set the webhook URL in YAML |
| Event producers | Synthetic generator + Prometheus/Alertmanager on our own metrics | Point sources at real systems |

## Load-test results

TODO (A-21, D-01).

## How we used AI

TODO (D-01): AI assistants for code, tests and docs; no production data or secrets in cloud tools; demo data is synthetic; the product's LLM runs locally in Ollama.
