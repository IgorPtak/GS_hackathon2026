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
from alerting_core.publishing import publish_alert_change
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

router = APIRouter(tags=["alerts"])

AlertId = Annotated[str, Path(description="Alert id (uuid)")]


def _not_found(alert_id: str) -> ApiError:
    return ApiError(404, "not_found", f"alert {alert_id} not found")


@router.get("/api/v1/alerts")
async def list_alerts_route(
    pool: PoolDep,
    team: Annotated[str, Query()],
    status: Annotated[AlertStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> AlertPage:
    """One page of a team's alerts, newest activity first."""
    try:
        return await list_alerts(
            pool, team, [status] if status else None, limit=limit, cursor=cursor
        )
    except InvalidCursorError as error:
        raise ApiError(400, "bad_request", str(error)) from error


@router.get("/api/v1/alerts/{alert_id}")
async def get_alert_route(alert_id: AlertId, pool: PoolDep) -> AlertDetail:
    """Alert with audit, deliveries, action runs and approvals."""
    try:
        detail = await get_alert_detail(pool, alert_id)
    except AlertNotFoundError as error:
        raise _not_found(alert_id) from error
    # B-07 plugs in here: detail.rendered_runbook = render_runbook(...)
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
