"""Outbox relay worker: serves /healthz and /metrics on port 9102 and runs the relay loop."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from alerting_core.connections import create_database_pool, create_redis_client
from alerting_core.logging import configure_logging
from alerting_core.metrics import render_metrics
from alerting_core.settings import Settings, get_settings
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from .relay import run_relay


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; the relay loop runs as a background task for the app's lifetime."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or get_settings()
        configure_logging("outbox-relay", resolved.log_level)
        pool = await create_database_pool(resolved)
        redis = create_redis_client(resolved)
        stop = asyncio.Event()
        task = asyncio.create_task(run_relay(pool, redis, stop))
        app.state.relay_task = task
        yield
        stop.set()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
        await redis.aclose()
        await pool.close()

    app = FastAPI(lifespan=lifespan)

    @app.get("/healthz", response_model=None)
    async def healthz() -> dict[str, str] | JSONResponse:
        """Liveness probe: 503 once the relay loop has died, so `compose ps` shows it unhealthy."""
        task: asyncio.Task[None] | None = getattr(app.state, "relay_task", None)
        if task is not None and task.done():
            return JSONResponse({"status": "relay_stopped"}, status_code=503)
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics() -> Response:
        """Prometheus exposition."""
        body, content_type = render_metrics()
        return Response(body, media_type=content_type)

    return app


app = create_app()
