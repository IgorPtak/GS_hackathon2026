# services/api

HTTP API for the UI: alerts, rules, preview, schema profiles, runbooks, approvals, fix proposals, SSE, metrics.

Owner: track B. Tasks: B-01, B-02, B-03, B-12, B-14, B-16, B-18, B-19, B-22, B-25. See `docs/IMPLEMENTATION_PLAN.md`.

## Run locally

```
CONFIG_DIR=config uv run uvicorn services.api.main:app --reload
```

Redis and Postgres are optional for `/healthz` and `/api/v1/config`: Redis connects lazily, and a
Postgres that is down at startup is logged and `app.state.pool` stays `None` (routes using
`PoolDep` answer 503). `/api/v1/events/recent` needs Redis.

## Add a route

1. Find the path and tag in `contracts/openapi.yaml`; put the handler in `routers/<tag>.py`
   (one module per tag) using the exact path and method.
2. Return or accept contract models from `alerting_contracts`; get Redis, the pool or the config
   source through `dependencies.py` (`RedisDep`, `PoolDep`, `ConfigSourceDep`) so tests can override them.
3. Raise `HTTPException` for errors; handlers in `errors.py` turn it into an `ErrorResponse`.
4. `tests/test_api.py::test_routes_exist_in_openapi_spec` fails if a route is not in the spec.

## Config, alerts and stream

- `/api/v1/config` reads the A-03 `ConfigRegistry` (started in the lifespan). If Postgres is
  unreachable at startup the api logs `config_source_fallback` and serves YAML straight from
  `CONFIG_DIR` (`DirectoryConfigSource`).
- `/api/v1/alerts*`: list (`team` required), detail, acknowledge, resolve. Errors are
  `ErrorResponse` (`not_found` 404, `invalid_transition` 409, `bad_request` 400 for a bad cursor).
  The routes publish `alert.updated` + `audit.appended` after a successful transition (storage
  does not publish).
- `/api/v1/stream?team=`: SSE for `alerts.team.<team>` and `broadcast`; `: ping` every 15 s.
