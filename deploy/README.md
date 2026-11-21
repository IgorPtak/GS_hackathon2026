# deploy

Dockerfile, nginx reverse proxy, Postgres migrations (shared), Prometheus, Grafana, Alertmanager config.

## `proxy` service (`deploy/nginx/nginx.conf`)

The `proxy` container (`nginx:1.27.5-alpine`) owns host ports `8000` and `8001` in `compose.yaml` so `api` and `ingest` can scale horizontally with `docker compose up -d --scale api=N --scale ingest=M` without port conflicts:

- **Fronts:** `:8000` → `api:8000` (`api_replicas`, `keepalive 32`) and `:8001` → `ingest:8001` (`ingest_replicas`, `keepalive 64`, `client_max_body_size 10m`).
- **Dynamic replica discovery:** uses Docker's embedded DNS (`resolver 127.0.0.11 valid=5s ipv6=off`) with shared upstream `zone` blocks and `server ... resolve`, so replicas added or removed via `--scale` enter or leave rotation within 5 s.
- **SSE support (`:8000`):** disables response buffering (`proxy_buffering off`) and sets `proxy_read_timeout 3600s` with HTTP/1.1 keepalive (`Connection ""`) so `/api/v1/stream` stays open and streams live alerts immediately.
- **Healthcheck:** internal HTTP server on port `8080` (`GET /healthz` → `200 ok`), polled every 5 s by Compose before `web` starts.
