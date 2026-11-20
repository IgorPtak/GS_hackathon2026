"""Routes tagged `alerts` in contracts/openapi.yaml (B-03).

Storage functions do not publish; the route publishes `alert.updated` + `audit.appended`
once after each successful transition.
"""

from typing import Annotated

from alerting_contracts.alerts import Alert, AlertStatus, ResolutionReason
from alerting_contracts.api import (
    AlertAcknowledgeRequest,
    AlertDetail,
    AlertPage,
    AlertResolveRequest,
)
from alerting_core.logging import get_logger
from alerting_core.publishing import publish_alert_change
from alerting_core.runbooks.rendering import render_runbook
from alerting_core.storage import (
    AlertNotFoundError,
    InvalidCursorError,
    InvalidTransitionError,
    acknowledge_alert,
    get_alert_detail,
    list_alerts,
    resolve_alert,
)
from fastapi import APIRouter, Path, Query

from ..dependencies import PoolDep, RedisDep
from ..errors import ApiError
from .runbooks import CatalogDep

log = get_logger(__name__)

router = APIRouter(tags=["alerts"])

AlertId = Annotated[str, Path(description="Alert id (uuid)")]


def _not_found(alert_id: str) -> ApiError:
    return ApiError(404, "not_found", f"alert {alert_id} not found")


@router.get("/api/v1/alerts")
async def list_alerts_route(
    pool: PoolDep,
    team: Annotated[str | None, Query()] = None,
    status: Annotated[AlertStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> AlertPage:
    """One page of alerts (optionally one team's), newest activity first."""
    try:
        return await list_alerts(
            pool, team, [status] if status else None, limit=limit, cursor=cursor
        )
    except InvalidCursorError as error:
        raise ApiError(400, "bad_request", str(error)) from error


@router.get("/api/v1/alerts/{alert_id}")
async def get_alert_route(alert_id: AlertId, pool: PoolDep, catalog: CatalogDep) -> AlertDetail:
    """Alert with audit, deliveries, action runs and approvals."""
    try:
        detail = await get_alert_detail(pool, alert_id)
    except AlertNotFoundError as error:
        raise _not_found(alert_id) from error
    runbook_id = detail.alert.runbook_id
    if runbook_id is not None:
        try:
            runbook = catalog.get(runbook_id)
            if runbook is not None:
                detail.rendered_runbook = render_runbook(runbook, detail.alert, catalog.actions())
        except Exception as error:  # noqa: BLE001 - the detail call must survive any render failure
            log.error(
                "runbook_render_failed",
                extra={"alert_id": alert_id, "runbook_id": runbook_id, "error": repr(error)},
            )
            detail.rendered_runbook = None
    return detail


@router.post("/api/v1/alerts/{alert_id}/acknowledge")
async def acknowledge_alert_route(
    alert_id: AlertId, body: AlertAcknowledgeRequest, pool: PoolDep, redis: RedisDep
) -> Alert:
    """open -> acknowledged."""
    try:
        async with pool.acquire() as connection:
            alert, audit = await acknowledge_alert(connection, alert_id, body.actor)
    except AlertNotFoundError as error:
        raise _not_found(alert_id) from error
    except InvalidTransitionError as error:
        raise ApiError(409, "invalid_transition", str(error)) from error
    await publish_alert_change(redis, alert, [audit])
    return alert


@router.post("/api/v1/alerts/{alert_id}/resolve")
async def resolve_alert_route(
    alert_id: AlertId, body: AlertResolveRequest, pool: PoolDep, redis: RedisDep
) -> Alert:
    """open or acknowledged -> resolved (reason manual)."""
    try:
        async with pool.acquire() as connection:
            alert, audit = await resolve_alert(
                connection, alert_id, body.actor, ResolutionReason.manual, body.comment
            )
    except AlertNotFoundError as error:
        raise _not_found(alert_id) from error
    except InvalidTransitionError as error:
        raise ApiError(409, "invalid_transition", str(error)) from error
    await publish_alert_change(redis, alert, [audit])
    return alert
