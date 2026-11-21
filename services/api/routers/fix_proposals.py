"""Routes tagged `fix-proposals` in contracts/openapi.yaml (B-22).

A responder proposes a change to the rule or runbook behind an alert; the rule's owner team
accepts or rejects it. Accepting is idempotent (see below).
The LLM draft route (B-24) lives in `fix_proposal_drafts.py`.

Accept ordering (documented because `save_config_document` / `save_runbook` use their own
pool connection, so they cannot join the proposal's transaction): the proposal row is locked
`FOR UPDATE`, the rule/runbook is saved FIRST, then the row is marked accepted in the locked
transaction. A failed save marks nothing. A crash between the two leaves the proposal pending
with the new version saved; accepting again finds the identical document already stored and
reuses its version (no extra version), so a proposal is never "accepted" without its change saved.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Any

import asyncpg
from alerting_contracts.alerts import Alert, AuditVerb
from alerting_contracts.api import (
    ConfigValidationError,
    FixProposalDecisionRequest,
)
from alerting_contracts.config import ActionConfig, ApprovalPolicy, Rule
from alerting_contracts.proposals import (
    FixKind,
    FixProposal,
    FixProposalCreate,
    ProposalStatus,
)
from alerting_contracts.runbooks import Runbook
from alerting_contracts.sse import AuditAppendedEvent, FixProposalEvent
from alerting_core.config import save_config_document
from alerting_core.config.store import canonical_document
from alerting_core.logging import get_logger
from alerting_core.publishing import publish_team_event
from alerting_core.runbooks import save_runbook
from alerting_core.runbooks.approval_policy import check_steps, tighten_steps
from alerting_core.storage.alerts_read import get_alert
from alerting_core.storage.audit import append_audit
from alerting_core.storage.transitions import AlertNotFoundError
from fastapi import APIRouter, Path, Query
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from redis.asyncio import Redis

from .. import fix_proposals_store as store
from ..dependencies import PoolDep, RedisDep, RegistryDep
from ..errors import ApiError, error_response
from .runbooks import CatalogDep, RunbookCatalog

log = get_logger(__name__)

router = APIRouter(tags=["fix-proposals"])

_RULE_KINDS = {FixKind.threshold, FixKind.fields, FixKind.dedup_window}


class ProposalNotFoundError(LookupError):
    """No proposal with that id (API: 404)."""


class AlreadyDecidedError(ValueError):
    """The proposal is not pending any more (API: 409 already_decided)."""


class ProposalInvalidError(ValueError):
    """The proposal cannot be applied (API: 422); carries dot-path details."""

    def __init__(self, message: str, details: list[ConfigValidationError]) -> None:
        super().__init__(message)
        self.details = details


def _detail(path: str, message: str) -> ConfigValidationError:
    return ConfigValidationError(path=path, message=message)


# The only top-level rule fields each kind may change; everything else must stay as it is.
_ALLOWED_RULE_FIELDS: dict[FixKind, frozenset[str]] = {
    FixKind.threshold: frozenset({"when"}),
    FixKind.fields: frozenset({"present"}),
    FixKind.dedup_window: frozenset({"dedup", "group"}),
}


def _diff_paths(current: Any, proposed: Any, path: str) -> list[str]:
    """Dot paths of the differing leaves; lists and type changes count as one path."""
    if isinstance(current, dict) and isinstance(proposed, dict):
        return [
            found
            for key in sorted(current.keys() | proposed.keys())
            for found in _diff_paths(current.get(key), proposed.get(key), f"{path}.{key}")
        ]
    return [] if current == proposed else [path]


def _rule_scope_errors(kind: FixKind, current: Rule, proposed: Rule) -> list[ConfigValidationError]:
    """422 details for every rule field changed outside what `kind` may touch."""
    allowed = _ALLOWED_RULE_FIELDS[kind]
    before = current.model_dump(mode="json")
    after = proposed.model_dump(mode="json")
    return [
        _detail(path, f"kind {kind.value} may only change {', '.join(sorted(allowed))}")
        for name in sorted(before.keys() | after.keys())
        if name not in allowed
        for path in _diff_paths(before.get(name), after.get(name), f"proposed_rule.{name}")
    ]


def _step_errors(
    body: FixProposalCreate, actions: Mapping[str, ActionConfig]
) -> list[ConfigValidationError]:
    """Same rules as a saved runbook: known action, approval never loosened."""
    step = body.proposed_runbook_step
    if step is None:
        return []
    errors = [
        _detail(path.replace("steps.0", "proposed_runbook_step"), message)
        for path, message in check_steps([step], actions)
    ]
    action = actions.get(step.action) if step.action else None
    if (
        action is not None
        and action.approval is ApprovalPolicy.required
        and step.approval is ApprovalPolicy.none
    ):
        errors.append(
            _detail(
                "proposed_runbook_step.approval",
                f"action {action.id!r} requires approval; a step cannot loosen it",
            )
        )
    return errors


def validate_create(
    alert: Alert,
    body: FixProposalCreate,
    current_rule: Rule | None,
    actions: Mapping[str, ActionConfig],
) -> list[ConfigValidationError]:
    """Check the kind/payload pairing and scope; returns dot-path errors (empty = valid).

    A rule kind needs the current rule and may change only its own fields. A runbook step must
    name a known action and not loosen its approval. Both arguments are required so no caller
    can skip these checks.
    """
    errors: list[ConfigValidationError] = []
    if body.kind in _RULE_KINDS:
        if body.proposed_rule is None:
            errors.append(_detail("proposed_rule", f"required for kind {body.kind.value}"))
        elif body.proposed_rule.id != alert.rule_id:
            errors.append(
                _detail(
                    "proposed_rule.id",
                    f"expected {alert.rule_id!r}, got {body.proposed_rule.id!r}",
                )
            )
        elif current_rule is None:
            errors.append(_detail("proposed_rule.id", f"rule {alert.rule_id!r} not found"))
        elif body.proposed_rule.team != current_rule.team:
            errors.append(
                _detail(
                    "proposed_rule.team",
                    f"a proposal cannot change ownership: expected {current_rule.team!r}, "
                    f"got {body.proposed_rule.team!r}",
                )
            )
        else:
            errors.extend(_rule_scope_errors(body.kind, current_rule, body.proposed_rule))
        if body.proposed_runbook_step is not None:
            errors.append(
                _detail("proposed_runbook_step", f"not allowed for kind {body.kind.value}")
            )
    elif body.kind is FixKind.runbook_step:
        if body.proposed_runbook_step is None:
            errors.append(_detail("proposed_runbook_step", "required for kind runbook_step"))
        if alert.runbook_id is None:
            errors.append(_detail("kind", "the alert has no runbook to change"))
        if body.proposed_rule is not None:
            errors.append(_detail("proposed_rule", "not allowed for kind runbook_step"))
        errors.extend(_step_errors(body, actions))
    else:
        if body.proposed_rule is not None:
            errors.append(_detail("proposed_rule", "not allowed for kind other"))
        if body.proposed_runbook_step is not None:
            errors.append(_detail("proposed_runbook_step", "not allowed for kind other"))
    return errors


def _teams(*teams: str) -> list[str]:
    """Distinct teams, order kept."""
    return list(dict.fromkeys(teams))


async def _publish(redis: Redis, teams: list[str], proposal: FixProposal, audit: Any) -> None:
    now = datetime.now(UTC)
    for team in teams:
        await publish_team_event(redis, team, FixProposalEvent(at=now, fix_proposal=proposal))
        await publish_team_event(redis, team, AuditAppendedEvent(at=now, entry=audit))


async def create_proposal(
    pool: asyncpg.Pool,
    redis: Redis,
    alert_id: str,
    body: FixProposalCreate,
    current_rule_of: Any,
    actions: Mapping[str, ActionConfig],
) -> FixProposal:
    """Insert + audit in one transaction, then publish.

    Raises AlertNotFoundError or ProposalInvalidError.

    `current_rule_of(rule_id)` returns the rule from the registry, or None.
    """
    if not store.is_uuid(alert_id):
        raise AlertNotFoundError(alert_id)
    async with pool.acquire() as connection, connection.transaction():
        alert = await get_alert(connection, alert_id)
        current_rule = current_rule_of(alert.rule_id)
        errors = validate_create(alert, body, current_rule, actions)
        if errors:
            raise ProposalInvalidError("invalid fix proposal", errors)
        owner_team = current_rule.team if current_rule is not None else alert.team
        proposal = await store.insert_proposal(connection, alert, owner_team, body)
        audit = await append_audit(
            connection,
            alert.id,
            body.proposed_by,
            AuditVerb.fix_proposed,
            detail={
                "fix_proposal_id": proposal.id,
                "kind": body.kind.value,
                "rule_id": alert.rule_id,
                "owner_team": owner_team,
            },
        )
    await _publish(redis, _teams(owner_team, alert.team), proposal, audit)
    log.info("fix_proposed", extra={"fix_proposal_id": proposal.id, "owner_team": owner_team})
    return proposal


def insert_step(runbook: Runbook, proposal: FixProposal) -> Runbook:
    """Runbook with the proposed step inserted at its index; later steps shift, indexes 0..n-1."""
    step = proposal.proposed_runbook_step
    if step is None:
        raise ProposalInvalidError(
            "proposal has no runbook step", [_detail("proposed_runbook_step", "missing")]
        )
    steps = list(runbook.steps)
    steps.insert(min(step.index, len(steps)), step)
    renumbered = [s.model_copy(update={"index": i}) for i, s in enumerate(steps)]
    return runbook.model_copy(update={"steps": renumbered})


def step_already_applied(runbook: Runbook, proposal: FixProposal) -> bool:
    """True when the runbook already holds the proposed step where it would be inserted."""
    step = proposal.proposed_runbook_step
    if step is None or not runbook.steps:
        return False
    position = min(step.index, len(runbook.steps) - 1)
    wanted = step.model_copy(update={"index": position})
    return canonical_document(runbook.steps[position]) == canonical_document(wanted)


async def decide_proposal(
    pool: asyncpg.Pool,
    redis: Redis,
    proposal_id: str,
    body: FixProposalDecisionRequest,
    get_runbook: Any,
    actions: Mapping[str, ActionConfig],
) -> FixProposal:
    """Decide atomically (see module docstring for ordering), then publish after commit."""
    if not store.is_uuid(proposal_id):
        raise ProposalNotFoundError(proposal_id)
    accepted = body.decision == "accept"
    async with pool.acquire() as connection, connection.transaction():
        current = await store.lock_proposal(connection, proposal_id)
        if current is None:
            raise ProposalNotFoundError(proposal_id)
        if current.status is not ProposalStatus.pending:
            raise AlreadyDecidedError(proposal_id)
        applied: dict[str, Any] = {}
        if accepted:
            applied = await _apply(pool, redis, current, body, get_runbook, actions)
        updated = await store.mark_decided(
            connection,
            proposal_id,
            ProposalStatus.accepted if accepted else ProposalStatus.rejected,
            body.actor,
            body.comment,
        )
        audit = await append_audit(
            connection,
            current.alert_id,
            body.actor,
            AuditVerb.fix_decided,
            detail={
                "fix_proposal_id": proposal_id,
                "decision": body.decision,
                "comment": body.comment,
                **applied,
            },
        )
        try:
            alert_team: str | None = (await get_alert(connection, current.alert_id)).team
        except AlertNotFoundError:
            alert_team = None
    teams = _teams(updated.owner_team, *([alert_team] if alert_team else []))
    await _publish(redis, teams, updated, audit)
    log.info("fix_decided", extra={"fix_proposal_id": proposal_id, "decision": body.decision})
    return updated


def _rebuild_rule(current: Rule, proposal: FixProposal) -> Rule:
    """The current rule with only the proposal kind's allowed fields taken from the proposal."""
    proposed = proposal.proposed_rule
    assert proposed is not None
    merged = current.model_dump(mode="python")
    for name in _ALLOWED_RULE_FIELDS.get(proposal.kind, frozenset()):
        merged[name] = getattr(proposed, name)
    return Rule.model_validate(merged)


async def _apply(
    pool: asyncpg.Pool,
    redis: Redis,
    proposal: FixProposal,
    body: FixProposalDecisionRequest,
    get_runbook: Any,
    actions: Mapping[str, ActionConfig],
) -> dict[str, Any]:
    """Save the proposed rule or runbook step; returns audit detail. Raises on invalid."""
    try:
        if proposal.proposed_rule is not None:
            rule_id = proposal.proposed_rule.id
            stored = await store.get_rule_document(pool, rule_id)
            if stored is None:
                raise ProposalInvalidError(
                    "rule no longer exists",
                    [_detail("proposed_rule.id", f"rule {rule_id!r} not found")],
                )
            # Rebuilt from the rule as it is now, so edits made since the proposal was created
            # survive; only the fields of the proposal's kind come from the proposal.
            wanted = _rebuild_rule(Rule.model_validate(stored[0]), proposal)
            if stored[0] == canonical_document(wanted):
                version = stored[1]  # already applied (or crash before mark): no extra version
            else:
                version = await save_config_document(pool, redis, "rule", wanted, body.actor)
            return {"saved": "rule", "id": rule_id, "version": version}
        if proposal.proposed_runbook_step is not None:
            if proposal.runbook_id is None:
                raise ProposalInvalidError(
                    "proposal has no runbook", [_detail("runbook_id", "missing")]
                )
            runbook = get_runbook(proposal.runbook_id)
            if runbook is None:
                raise ProposalInvalidError(
                    "runbook no longer exists",
                    [_detail("runbook_id", f"runbook {proposal.runbook_id!r} not found")],
                )
            problems = _step_errors(
                FixProposalCreate(
                    kind=FixKind.runbook_step,
                    description=proposal.description,
                    proposed_runbook_step=proposal.proposed_runbook_step,
                    proposed_by=proposal.proposed_by,
                ),
                actions,
            )
            if problems:
                raise ProposalInvalidError("proposal cannot be applied", problems)
            tightened = tighten_steps([proposal.proposed_runbook_step], actions)[0]
            proposal = proposal.model_copy(update={"proposed_runbook_step": tightened})
            if step_already_applied(runbook, proposal):
                version = runbook.version  # already saved (crash before mark): no extra version
            else:
                version = await save_runbook(
                    pool, redis, insert_step(runbook, proposal), body.actor
                )
            return {"saved": "runbook", "id": proposal.runbook_id, "version": version}
    except ValidationError as error:
        raise ProposalInvalidError(
            "proposal cannot be applied",
            [_detail(".".join(str(p) for p in e["loc"]), e["msg"]) for e in error.errors()],
        ) from error
    except ValueError as error:
        if isinstance(error, ProposalInvalidError):
            raise
        raise ProposalInvalidError(
            "proposal cannot be applied", [_detail("", str(error))]
        ) from error
    return {}


def _invalid(error: ProposalInvalidError) -> JSONResponse:
    return error_response(422, "validation_failed", str(error), error.details)


@router.post("/api/v1/alerts/{alert_id}/fix-proposals", status_code=201, response_model=FixProposal)
async def create_fix_proposal_route(
    alert_id: Annotated[str, Path()],
    body: FixProposalCreate,
    pool: PoolDep,
    redis: RedisDep,
    registry: RegistryDep,
    catalog: CatalogDep,
) -> Any:
    """Propose a rule or runbook fix from an alert; goes to the rule's owner team."""

    def current_rule_of(rule_id: str) -> Rule | None:
        return registry.rules().get(rule_id) if registry is not None else None

    try:
        return await create_proposal(
            pool, redis, alert_id, body, current_rule_of, catalog.actions()
        )
    except AlertNotFoundError as error:
        raise ApiError(404, "not_found", f"alert {alert_id} not found") from error
    except ProposalInvalidError as error:
        return _invalid(error)


@router.get("/api/v1/fix-proposals")
async def list_fix_proposals_route(
    pool: PoolDep,
    team: Annotated[str | None, Query()] = None,
    status: Annotated[ProposalStatus | None, Query()] = None,
) -> list[FixProposal]:
    """Proposals, optionally of one owner team and/or status, newest first."""
    return await store.list_proposals(pool, team, status)


@router.post("/api/v1/fix-proposals/{proposal_id}/decision", response_model=FixProposal)
async def decide_fix_proposal_route(
    proposal_id: Annotated[str, Path()],
    body: FixProposalDecisionRequest,
    pool: PoolDep,
    redis: RedisDep,
    catalog: CatalogDep,
) -> Any:
    """Accept (saves the new rule version or runbook step) or reject a pending proposal."""
    try:
        return await decide_proposal(
            pool, redis, proposal_id, body, _runbook_getter(catalog), catalog.actions()
        )
    except ProposalNotFoundError as error:
        raise ApiError(404, "not_found", f"fix proposal {proposal_id} not found") from error
    except AlreadyDecidedError as error:
        raise ApiError(
            409, "already_decided", f"fix proposal {proposal_id} is already decided"
        ) from error
    except ProposalInvalidError as error:
        return _invalid(error)


def _runbook_getter(catalog: RunbookCatalog) -> Any:
    return catalog.get
