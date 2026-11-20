"""Load source YAML into `SourceConfig`; A-03 swaps the lookup for the ConfigRegistry."""

from pathlib import Path

import yaml
from alerting_contracts.config import SourceConfig
from alerting_core.logging import get_logger

log = get_logger(__name__)


def load_sources(config_dir: str) -> dict[str, SourceConfig]:
    """Read `<config_dir>/sources/*.yaml`; invalid files are logged and skipped."""
    sources: dict[str, SourceConfig] = {}
    for path in sorted(Path(config_dir, "sources").glob("*.yaml")):
        try:
            source = SourceConfig.model_validate(yaml.safe_load(path.read_text()))
        except (OSError, ValueError, yaml.YAMLError) as error:
            log.error("source_config_invalid", extra={"path": str(path), "error": str(error)})
            continue
        sources[source.id] = source
    return sources
