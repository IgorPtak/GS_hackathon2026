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
