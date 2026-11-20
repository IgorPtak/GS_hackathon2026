"""Runbook format plugins. Importing this package registers the built-ins."""

from plugins.runbook_formats import markdown_format, text_format, yaml_format  # noqa: F401
from plugins.runbook_formats.base import RunbookFormatPlugin
from plugins.runbook_formats.registry import (
    UnknownRunbookFormatError,
    get_runbook_format,
    register_runbook_format,
    registered_formats,
)

__all__ = [
    "RunbookFormatPlugin",
    "UnknownRunbookFormatError",
    "get_runbook_format",
    "register_runbook_format",
    "registered_formats",
]
