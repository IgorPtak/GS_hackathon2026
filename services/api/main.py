"""HTTP API for the UI (track B, port 8000)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from alerting_core.config import ConfigRegistry
from alerting_core.connections import create_database_pool, create_redis_client
from alerting_core.logging import configure_logging, get_logger
from alerting_core.metrics import render_metrics
from alerting_core.settings import Settings, get_settings
from fastapi import FastAPI, Response
from redis.exceptions import RedisError

from .config_source import DirectoryConfigSource, RegistryConfigSource
from .errors import install_error_handlers
from .routers import (
    alerts,
    approvals,
    config,
    fix_proposals,
    ops,
    phone_simulator,
    rules,
    runbooks,
    schema_profiles,
    stream,
)

log = get_logger(__name__)

ROUTERS = (
    alerts,
    runbooks,
    fix_proposals,
    config,
    rules,
    schema_profiles,
    approvals,
    phone_simulator,
    stream,
    ops,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; pool, Redis and config source live in the lifespan (app.state).

    A Postgres that is down at startup does not stop the api: `state.pool` stays None and
    routes that need it answer 503 (the pool has no consumers yet).
    """
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging("api", resolved.log_level)
        app.state.settings = resolved
        app.state.registry = None
        app.state.redis = create_redis_client(resolved)  # connects lazily
        try:
            app.state.pool = await create_database_pool(resolved)
        except (OSError, asyncpg.PostgresError) as error:
            log.error("database_unavailable", extra={"error": str(error)})
            app.state.pool = None
        app.state.config_source = DirectoryConfigSource(resolved.config_dir)
        if app.state.pool is not None:
            registry = ConfigRegistry()
            try:
                await registry.start(app.state.pool, app.state.redis)
            except (
                RuntimeError,
                OSError,
                asyncpg.PostgresError,
                RedisError,
                TimeoutError,
            ) as error:
                log.error("config_source_fallback", extra={"error": str(error)})
            else:
                app.state.registry = registry
                app.state.config_source = RegistryConfigSource(
                    registry, fallback=DirectoryConfigSource(resolved.config_dir)
                )
        else:
            log.warning("config_source_fallback", extra={"reason": "database_unavailable"})
        log.info("api_started")
        yield
        if app.state.registry is not None:
            await app.state.registry.stop()
        await app.state.redis.aclose()
        if app.state.pool is not None:
            await app.state.pool.close()

    app = FastAPI(title="Alerting API", lifespan=lifespan)
    install_error_handlers(app)
    for module in ROUTERS:
        app.include_router(module.router)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        """Prometheus exposition."""
        body, content_type = render_metrics()
        return Response(body, media_type=content_type)

    return app


app = create_app()
