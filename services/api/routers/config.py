"""Routes tagged `config`."""

from alerting_contracts.api import ConfigLists
from fastapi import APIRouter

from ..dependencies import ConfigSourceDep

router = APIRouter(tags=["config"])


@router.get("/api/v1/config")
async def get_config_lists(source: ConfigSourceDep) -> ConfigLists:
    """Read-only config used by UI dropdowns."""
    return source.get_config_lists()
