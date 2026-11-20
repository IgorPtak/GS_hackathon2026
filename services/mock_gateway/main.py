"""Mock gateway (track A, port 8090): SMS/phone gateway, webhook receiver and action targets.

In-memory state on app.state; run with a single uvicorn worker (it is a mock).
"""

import itertools
import os
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from alerting_core.logging import configure_logging, get_logger
from alerting_core.metrics import render_metrics
from alerting_core.settings import Settings, get_settings
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import Gauge
from pydantic import BaseModel, ValidationError

log = get_logger(__name__)

MAX_REQUESTS = 10_000
OUTAGE_CHANNELS = ("sms", "phone", "webhooks")

MOCK_GATEWAY_UP = Gauge("mock_gateway_up", "0 while a simulated outage is active, else 1")
MOCK_GATEWAY_UP.set(1)


class MessageIn(BaseModel):
    """Body of POST /sms and POST /phone."""

    to: str
    text: str
    delivery_id: str | None = None


class OutageIn(BaseModel):
    """Body of POST /admin/outage; `channels` null means all of sms, phone and webhooks."""

    is_down: bool
    channels: list[str] | None = None


class HealthIn(BaseModel):
    """Body of POST /admin/services/{name}/health."""

    is_healthy: bool


class GatewayState:
    """Everything the mock remembers."""

    def __init__(self, retry_failures: int) -> None:
        self.requests: deque[dict[str, Any]] = deque(maxlen=MAX_REQUESTS)
        self.down_channels: set[str] = set()
        self.unhealthy_services: set[str] = set()
        self.retry_failures = retry_failures
        self.retry_calls: dict[str, int] = {}
        self.message_ids = itertools.count(1)
        self.ticket_ids = itertools.count(1)

    def set_outage(self, is_down: bool, channels: list[str] | None) -> None:
        """Switch outage on or off for the given channels (None = all) and update the gauge."""
        targets = set(OUTAGE_CHANNELS) if channels is None else set(channels)
        if is_down:
            self.down_channels |= targets
        else:
            self.down_channels -= targets
        MOCK_GATEWAY_UP.set(0 if self.down_channels else 1)


async def read_body(request: Request) -> Any:
    """Decode a JSON body; anything else is kept as text so webhooks never fail to log."""
    raw = await request.body()
    if not raw:
        return None
    try:
        return await request.json()
    except ValueError:
        return raw.decode("utf-8", errors="replace")


def reply(
    request: Request, body: Any, status: int, payload: Any, *, rejected: bool = False
) -> JSONResponse:
    """Record the request, emit one `gateway_request` log line and build the JSON response."""
    entry = {
        "received_at": datetime.now(UTC).isoformat(),
        "method": request.method,
        "path": request.url.path,
        "status": status,
        "rejected": rejected,
        "body": body,
    }
    request.app.state.gateway.requests.append(entry)
    log.info(
        "gateway_request",
        extra={"path": entry["path"], "status": status, "rejected": rejected},
    )
    return JSONResponse(payload, status_code=status)


async def handle_message(request: Request, channel: str) -> JSONResponse:
    """Shared body of POST /sms and POST /phone."""
    state: GatewayState = request.app.state.gateway
    body = await read_body(request)
    if channel in state.down_channels:
        return reply(request, body, 503, {"error": "gateway_down"}, rejected=True)
    try:
        message = MessageIn.model_validate(body)
    except ValidationError as error:
        return reply(request, body, 422, {"error": "validation_failed", "message": str(error)})
    message_id = f"{channel}-{next(state.message_ids)}"
    log.info(
        "gateway_message_stored",
        extra={"channel": channel, "message_id": message_id, "delivery_id": message.delivery_id},
    )
    return reply(request, body, 200, {"message_id": message_id})


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; state lives on app.state."""
    resolved = settings or get_settings()
    retry_failures = int(os.environ.get("MOCK_GATEWAY_RETRY_FAILURES", "2"))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging("mock-gateway", resolved.log_level)
        log.info("mock_gateway_started", extra={"retry_failures": retry_failures})
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.gateway = GatewayState(retry_failures)
    MOCK_GATEWAY_UP.set(1)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Liveness probe; always 200, the container is fine during a simulated outage."""
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics() -> Response:
        """Prometheus exposition."""
        body, content_type = render_metrics()
        return Response(body, media_type=content_type)

    @app.post("/sms")
    async def send_sms(request: Request) -> JSONResponse:
        """Store an SMS and return its message id (503 during an outage)."""
        return await handle_message(request, "sms")

    @app.post("/phone")
    async def place_call(request: Request) -> JSONResponse:
        """Store a phone call and return its message id (503 during an outage)."""
        return await handle_message(request, "phone")

    @app.post("/webhooks/{name}")
    async def receive_webhook(request: Request, name: str) -> JSONResponse:
        """Log a webhook payload (503 while webhooks are down)."""
        state: GatewayState = request.app.state.gateway
        body = await read_body(request)
        if "webhooks" in state.down_channels:
            return reply(request, body, 503, {"error": "gateway_down"}, rejected=True)
        return reply(request, body, 200, {"received": True, "name": name})

    @app.post("/tickets")
    async def open_ticket(request: Request) -> JSONResponse:
        """Create a mock ticket."""
        body = await read_body(request)
        ticket_id = f"TCK-{next(request.app.state.gateway.ticket_ids)}"
        return reply(request, body, 200, {"ticket_id": ticket_id})

    @app.post("/workflows/{workflow_id}/retry")
    async def retry_workflow(request: Request, workflow_id: str) -> JSONResponse:
        """Fail the first N calls per workflow with 502, then succeed."""
        state: GatewayState = request.app.state.gateway
        body = await read_body(request)
        calls = state.retry_calls.get(workflow_id, 0) + 1
        state.retry_calls[workflow_id] = calls
        if calls <= state.retry_failures:
            return reply(request, body, 502, {"error": "upstream_failed", "attempt": calls})
        return reply(request, body, 200, {"status": "retried"})

    @app.get("/services/{name}/health")
    async def service_health(request: Request, name: str) -> JSONResponse:
        """Healthy (200) or unhealthy (503), as configured through the admin endpoint."""
        state: GatewayState = request.app.state.gateway
        if name in state.unhealthy_services:
            return reply(request, None, 503, {"status": "unhealthy"})
        return reply(request, None, 200, {"status": "healthy"})

    @app.post("/services/{name}/restart")
    async def restart_service(request: Request, name: str) -> JSONResponse:
        """Mark the service healthy again."""
        body = await read_body(request)
        request.app.state.gateway.unhealthy_services.discard(name)
        return reply(request, body, 200, {"restarted": True})

    @app.post("/admin/services/{name}/health")
    async def set_service_health(name: str, body: HealthIn, request: Request) -> dict[str, Any]:
        """Toggle a service between healthy and unhealthy."""
        state: GatewayState = request.app.state.gateway
        if body.is_healthy:
            state.unhealthy_services.discard(name)
        else:
            state.unhealthy_services.add(name)
        log.info("gateway_service_health_set", extra={"name": name, "is_healthy": body.is_healthy})
        return {"name": name, "is_healthy": body.is_healthy}

    @app.get("/admin/outage")
    async def get_outage(request: Request) -> dict[str, Any]:
        """Current outage state."""
        down = sorted(request.app.state.gateway.down_channels)
        return {"is_down": bool(down), "channels": down}

    @app.post("/admin/outage")
    async def set_outage(body: OutageIn, request: Request) -> dict[str, Any]:
        """Switch a simulated outage on or off."""
        state: GatewayState = request.app.state.gateway
        state.set_outage(body.is_down, body.channels)
        log.info("gateway_outage_set", extra={"is_down": body.is_down, "channels": body.channels})
        down = sorted(state.down_channels)
        return {"is_down": bool(down), "channels": down}

    @app.get("/requests")
    async def list_requests(
        request: Request, path_prefix: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Received requests, newest last, optionally filtered by path prefix."""
        items = [
            r
            for r in request.app.state.gateway.requests
            if path_prefix is None or r["path"].startswith(path_prefix)
        ]
        return items[-limit:] if limit > 0 else []

    @app.delete("/requests")
    async def clear_requests(request: Request) -> dict[str, bool]:
        """Forget everything received and reset retry counters (demo and test resets)."""
        state: GatewayState = request.app.state.gateway
        state.requests.clear()
        state.retry_calls.clear()
        return {"cleared": True}

    return app


app = create_app()
