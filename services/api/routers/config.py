"""Routes tagged `config`."""

from typing import Any

import yaml
from alerting_contracts.api import (
    ConfigLists,
    ConfigValidationError,
    ConfigValidationRequest,
    ConfigValidationResult,
)
from alerting_contracts.runbooks import RunbookYamlDocument
from alerting_core.config import get_kind
from fastapi import APIRouter
from pydantic import BaseModel, ValidationError

from ..dependencies import ConfigSourceDep
from .rules import validation_errors

router = APIRouter(tags=["config"])


@router.get("/api/v1/config")
async def get_config_lists(source: ConfigSourceDep) -> ConfigLists:
    """Read-only config used by UI dropdowns (registry-backed; directory fallback without DB)."""
    return source.get_config_lists()


def _fail(*errors: ConfigValidationError) -> ConfigValidationResult:
    return ConfigValidationResult(is_valid=False, errors=list(errors))


def _validate(kind: str, data: dict[str, Any]) -> BaseModel:
    if kind == "runbook":
        return RunbookYamlDocument.model_validate(data)
    return get_kind(kind).validate_document(data)


@router.post("/api/v1/config/validate")
async def validate_config(body: ConfigValidationRequest) -> ConfigValidationResult:
    """Validate a YAML document of any kind; errors carry dot paths ('' = whole document)."""
    try:
        data = yaml.safe_load(body.yaml)
    except yaml.YAMLError as exc:
        return _fail(ConfigValidationError(path="", message=f"invalid YAML: {exc}"))
    if not isinstance(data, dict):
        return _fail(ConfigValidationError(path="", message="document must be a YAML mapping"))
    try:
        model = _validate(body.kind, data)
    except ValidationError as exc:
        return _fail(*validation_errors(exc))
    except KeyError:
        return _fail(ConfigValidationError(path="", message=f"unknown kind {body.kind!r}"))
    return ConfigValidationResult(
        is_valid=True, document=model.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
