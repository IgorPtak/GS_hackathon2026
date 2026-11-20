"""YAML runbooks: the file already is a RunbookYamlDocument; validate and return its steps."""

from __future__ import annotations

from collections.abc import Mapping

import yaml
from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import RunbookFormat, RunbookStep, RunbookYamlDocument
from pydantic_core import InitErrorDetails, ValidationError

from plugins.runbook_formats.base import RunbookFormatPlugin
from plugins.runbook_formats.registry import register_runbook_format


def parse_yaml_document(source: str) -> RunbookYamlDocument:
    """Parse and validate; raises ``ValidationError`` with a field path."""
    data = yaml.safe_load(source)
    if not isinstance(data, dict):
        raise ValueError("runbook YAML must be a mapping with id, title and steps")
    document = RunbookYamlDocument.model_validate(data)
    errors: list[InitErrorDetails] = [
        {
            "type": "value_error",
            "loc": ("steps", position, "index"),
            "input": step.index,
            "ctx": {
                "error": ValueError(f"step indexes must be 0..n-1 in order, expected {position}")
            },
        }
        for position, step in enumerate(document.steps)
        if step.index != position
    ]
    if errors:
        raise ValidationError.from_exception_data("RunbookYamlDocument", errors)
    return document


@register_runbook_format
class YamlRunbookFormat(RunbookFormatPlugin):
    format = RunbookFormat.yaml

    def normalize(self, source: str, actions: Mapping[str, ActionConfig]) -> list[RunbookStep]:
        return parse_yaml_document(source).steps
