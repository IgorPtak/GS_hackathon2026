"""Routes tagged `runbooks` in contracts/openapi.yaml (B-06).

Runbooks come from the ConfigRegistry (kind `runbook`); when it holds none (no Postgres, or
config/ not yet synced) they are loaded from `<config_dir>/runbooks` through the same loader.
"""

from pathlib import Path
from typing import Annotated, Any

import yaml
from alerting_contracts.api import (
    ConfigValidationError,
    ErrorResponse,
    RunbookNormalizeRequest,
    RunbookSummary,
    RunbookWrite,
)
from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import Runbook, RunbookFormat
from alerting_core.logging import get_logger
from alerting_core.runbooks import normalize_runbook, save_runbook
from alerting_core.runbooks.approval_policy import StepPolicyError, check_steps
from alerting_core.runbooks.normalize import normalize_runbook_with_llm
from alerting_core.runbooks.store import KIND, load_runbook_file
from fastapi import APIRouter, Depends, Request
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from plugins.runbook_formats.markdown_format import heading_text

from ..dependencies import PoolDep, RedisDep
from ..errors import ApiError

log = get_logger(__name__)

router = APIRouter(tags=["runbooks"])

PREVIEW_ID = "preview"
PREVIEW_TITLE = "Untitled runbook"  # placeholders: a preview has no id; title falls back to this


class RunbookCatalog:
    """Read access to runbooks and actions for the routes (registry first, files as fallback)."""

    def __init__(self, request: Request) -> None:
        self._registry = request.app.state.registry
        self._config_dir = Path(request.app.state.settings.config_dir)
        self._config_source = request.app.state.config_source

    def _from_files(self) -> dict[str, Runbook]:
        found: dict[str, Runbook] = {}
        for path in sorted((self._config_dir / "runbooks").glob("*")):
            try:
                runbook = load_runbook_file(
                    path, normalize_text_with_llm=False
                )  # never the LLM per request
            except Exception as error:  # noqa: BLE001 - one bad file must not hide the others
                log.warning("runbook_file_invalid", extra={"file": path.name, "error": str(error)})
                continue
            found[runbook.id] = runbook
        return found

    def all(self) -> dict[str, Runbook]:
        """Runbooks by id, each with its stored version."""
        registry = self._registry
        if registry is not None:
            documents = registry.snapshot.of_kind(KIND)
            if documents:
                return {
                    rid: doc.model_copy(
                        update={"version": registry.snapshot.versions.get((KIND, rid), doc.version)}
                    )
                    for rid, doc in documents.items()
                }
        return self._from_files()

    def get(self, runbook_id: str) -> Runbook | None:
        """One runbook or None."""
        return self.all().get(runbook_id)

    def actions(self) -> dict[str, ActionConfig]:
        """Actions by id, for approval resolution."""
        lists = self._config_source.get_config_lists()
        return {action.id: action for action in lists.actions}


def get_catalog(request: Request) -> RunbookCatalog:
    """Per-request catalog over app.state; tests override this."""
    return RunbookCatalog(request)


CatalogDep = Annotated[RunbookCatalog, Depends(get_catalog)]
RunbookId = Annotated[str, PathParam(description="Runbook id")]


def _validation_response(error: Exception) -> JSONResponse:
    if isinstance(error, ValidationError):
        details = [
            ConfigValidationError(
                path=".".join(str(part) for part in item["loc"]), message=item["msg"]
            )
            for item in error.errors()
        ]
    elif isinstance(error, StepPolicyError):
        details = [ConfigValidationError(path=p, message=m) for p, m in error.problems]
    else:
        details = [ConfigValidationError(path="", message=str(error))]
    body = ErrorResponse(
        error="validation_failed", message="runbook source is invalid", details=details
    )
    return JSONResponse(body.model_dump(mode="json"), status_code=422)


def _preview_meta(format: RunbookFormat, source: str) -> tuple[str, str | None]:
    """Title and team guessed from the source for a preview."""
    title, team = PREVIEW_TITLE, None
    if format is RunbookFormat.markdown:
        title = heading_text(source) or title
    elif format is RunbookFormat.yaml:
        try:
            data = yaml.safe_load(source)
        except yaml.YAMLError:
            data = None
        if isinstance(data, dict):
            title = str(data.get("title") or title)
            team = data.get("team")
    return title, team


@router.get("/api/v1/runbooks")
async def list_runbooks_route(catalog: CatalogDep) -> list[RunbookSummary]:
    """All runbooks as summaries."""
    return [
        RunbookSummary(
            id=runbook.id,
            title=runbook.title,
            team=runbook.team,
            format=runbook.format,
            step_count=len(runbook.steps),
            normalized_by=runbook.normalized_by,
            llm_model=runbook.llm_model,
            version=runbook.version,
        )
        for runbook in catalog.all().values()
    ]


@router.post("/api/v1/runbooks/normalize", response_model=Runbook)
async def normalize_runbook_route(body: RunbookNormalizeRequest, catalog: CatalogDep) -> Any:
    """Preview normalization without saving; id is `preview`, title is guessed or a placeholder.

    LLM-free on purpose: a text runbook previews as the fallback (one text step). The LLM runs
    only when a text runbook is saved (PUT).
    """
    title, team = _preview_meta(body.format, body.source)
    try:
        return normalize_runbook(
            PREVIEW_ID, title, team, body.format, body.source, catalog.actions()
        )
    except (ValidationError, ValueError) as error:
        return _validation_response(error)


@router.get("/api/v1/runbooks/{runbook_id}")
async def get_runbook_route(runbook_id: RunbookId, catalog: CatalogDep) -> Runbook:
    """One runbook with its original source."""
    runbook = catalog.get(runbook_id)
    if runbook is None:
        raise ApiError(404, "not_found", f"runbook {runbook_id} not found")
    return runbook


@router.put("/api/v1/runbooks/{runbook_id}", response_model=Runbook)
async def save_runbook_route(
    runbook_id: RunbookId,
    body: RunbookWrite,
    request: Request,
    catalog: CatalogDep,
    pool: PoolDep,
    redis: RedisDep,
) -> Any:
    """Normalize and store; returns the runbook with its new version.

    For format text the LLM proposes the steps (normalized_by "llm", llm_model set); without an
    LLM, or on any LLM error, the whole text is kept as one text step ("fallback"). yaml and
    markdown are parsed.
    """
    if body.id != runbook_id:
        raise ApiError(422, "validation_failed", "path id and body id differ")
    try:
        runbook = await normalize_runbook_with_llm(
            body.id,
            body.title,
            body.team,
            body.format,
            body.source,
            catalog.actions(),
            getattr(request.app.state, "llm", None),
        )
        problems = check_steps(runbook.steps, catalog.actions())
        if problems:
            raise StepPolicyError(problems)
    except StepPolicyError as error:
        return _validation_response(error)
    except (ValidationError, ValueError) as error:
        return _validation_response(error)
    version = await save_runbook(pool, redis, runbook, body.actor)
    return runbook.model_copy(update={"version": version})
