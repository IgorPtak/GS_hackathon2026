"""Shared primitives used by every contract module."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# Config ids are slugs so they are safe in Redis keys, URLs and file names.
ConfigId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$", examples=["rates-large-rejections"])]

# Durations are written the way humans write them in YAML; alerting_core.durations parses them.
Duration = Annotated[str, Field(pattern=r"^[0-9]+(ms|s|m|h|d)$", examples=["60s", "5m", "1h"])]

# "08:00-20:00"; a window that wraps midnight ("22:00-06:00") is allowed.
TimeOfDayRange = Annotated[str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]-([01][0-9]|2[0-3]):[0-5][0-9]$")]

# A dot path into the raw event ("payload.notional") or into normalized fields ("normalized.severity").
FieldPath = Annotated[str, Field(min_length=1, examples=["payload.notional", "normalized.severity"])]

# A string with {{field.path}} placeholders rendered by alerting_core.templating.render_template.
Template = Annotated[str, Field(examples=["Rejected {{payload.currency}} {{payload.notional}}"])]


class ContractModel(BaseModel):
    """Base for all contract models: unknown fields are errors, so drift fails loudly."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Severity(StrEnum):
    """Ordered from least to most severe; comparisons use SEVERITY_ORDER."""

    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


SEVERITY_ORDER: dict[Severity, int] = {severity: rank for rank, severity in enumerate(Severity)}


class Actor(ContractModel):
    """Who performed something: a recipient id, 'system:<service>' or 'llm'."""

    id: str = Field(examples=["anna", "system:processor", "llm"])
    display_name: str | None = None
