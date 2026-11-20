"""HTTP API for the UI (track B, port 8000)."""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from alerting_core.config import ConfigRegistry
from alerting_core.connections import create_database_pool, create_redis_client
from alerting_core.llm import LlmClient, LlmConfig, LlmHostNotAllowedError
from alerting_core.logging import configure_logging, get_logger
from alerting_core.metrics import render_metrics
from alerting_core.runbooks import register_runbook_kind
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
    metrics,
    ops,
    phone_simulator,
    recipients,
    rules,
    runbooks,
    schema_profiles,
    stream,
)

log = get_logger(__name__)

# How often a request may retry connecting to Postgres while it is down.
DATABASE_RETRY_SECONDS = 5.0

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
    metrics,
    recipients,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; pool, Redis and config source live in the lifespan (app.state).

    A Postgres that is down at startup does not stop the api: `state.pool` stays None, routes
    that need it answer 503, and get_pool retries the connection at most every few seconds.
    """
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging("api", resolved.log_level)
        app.state.settings = resolved
        app.state.registry = None
        app.state.redis = create_redis_client(resolved)  # connects lazily
        app.state.pool = None
        app.state.config_source = DirectoryConfigSource(resolved.config_dir)
        app.state.database_lock = asyncio.Lock()
        app.state.next_database_attempt = 0.0
        try:
            app.state.llm = LlmClient(LlmConfig.from_settings(resolved))
        except LlmHostNotAllowedError as error:
            log.warning("llm_disabled", extra={"reason": str(error)})
            app.state.llm = None
        register_runbook_kind()  # before ConfigRegistry.start so the kind is loaded

        async def connect_database() -> asyncpg.Pool | None:
            """Create the pool and the ConfigRegistry; retried lazily by get_pool when down."""
            async with app.state.database_lock:
                if app.state.pool is not None:
                    return app.state.pool
                if time.monotonic() < app.state.next_database_attempt:
                    return None
                app.state.next_database_attempt = time.monotonic() + DATABASE_RETRY_SECONDS
                try:
                    pool = await create_database_pool(resolved)
                except (OSError, asyncpg.PostgresError) as error:
                    log.error("database_unavailable", extra={"error": str(error)})
                    log.warning("config_source_fallback", extra={"reason": "database_unavailable"})
                    return None
                app.state.pool = pool
                registry = ConfigRegistry()
                try:
                    await registry.start(pool, app.state.redis)
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
                log.info("database_connected")
                return pool

        app.state.connect_database = connect_database
        await connect_database()
        log.info("api_started")
        yield
        if app.state.registry is not None:
            await app.state.registry.stop()
        await app.state.redis.aclose()
        # LlmClient opens a short-lived httpx client per call: nothing to close.
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
