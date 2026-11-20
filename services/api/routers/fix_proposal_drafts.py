"""POST /api/v1/alerts/{alert_id}/fix-proposals/draft (B-24): an LLM draft that is never saved."""

from typing import Annotated, Any

from alerting_contracts.proposals import FixProposalCreate
from alerting_core.logging import get_logger
from alerting_core.storage.alerts_read import get_alert
from alerting_core.storage.transitions import AlertNotFoundError
from fastapi import APIRouter, Path, Request

from .. import fix_proposals_store as store
from ..dependencies import PoolDep, RegistryDep
from ..errors import ApiError
from ..fix_proposal_draft import DraftInvalidError, DraftUnavailableError, draft_fix_proposal
from .fix_proposals import validate_create
from .runbooks import CatalogDep

router = APIRouter(tags=["fix-proposals"])
log = get_logger(__name__)


@router.post("/api/v1/alerts/{alert_id}/fix-proposals/draft", response_model=FixProposalCreate)
async def draft_fix_proposal_route(
    alert_id: Annotated[str, Path()],
    request: Request,
    pool: PoolDep,
    registry: RegistryDep,
    catalog: CatalogDep,
) -> Any:
    """LLM-drafted fix proposal for the alert; never saved. 503 when the LLM is unavailable."""
    if not store.is_uuid(alert_id):
        raise ApiError(404, "not_found", f"alert {alert_id} not found")
    try:
        async with pool.acquire() as connection:
            alert = await get_alert(connection, alert_id)
    except AlertNotFoundError as error:
        raise ApiError(404, "not_found", f"alert {alert_id} not found") from error
    rule = registry.rules().get(alert.rule_id) if registry is not None else None
    runbook = catalog.get(alert.runbook_id) if alert.runbook_id else None
    try:
        return await draft_fix_proposal(
            request.app.state.llm, alert, rule, runbook, catalog.actions(), validate_create
        )
    except DraftUnavailableError as error:
        raise ApiError(503, "llm_unavailable", f"LLM unavailable: {error}") from error
    except DraftInvalidError as error:
        log.warning("fix_draft_invalid", extra={"alert_id": alert_id, "error": str(error)})
        raise ApiError(
            503, "llm_invalid_output", f"LLM unavailable: draft was not valid ({error})"
        ) from error
