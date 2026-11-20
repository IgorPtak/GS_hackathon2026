"""Registry mapping runbook ``format`` to plugin class."""

from __future__ import annotations

from alerting_contracts.runbooks import RunbookFormat

from plugins.runbook_formats.base import RunbookFormatPlugin

_REGISTRY: dict[RunbookFormat, type[RunbookFormatPlugin]] = {}


class UnknownRunbookFormatError(KeyError):
    """No runbook format plugin is registered for this format."""


def register_runbook_format[T: type[RunbookFormatPlugin]](cls: T) -> T:
    """Class decorator: register ``cls`` under ``cls.format``."""
    _REGISTRY[cls.format] = cls
    return cls


def get_runbook_format(format: RunbookFormat | str) -> RunbookFormatPlugin:
    try:
        return _REGISTRY[RunbookFormat(format)]()
    except (KeyError, ValueError):
        raise UnknownRunbookFormatError(str(format)) from None


def registered_formats() -> list[str]:
    return sorted(str(f) for f in _REGISTRY)
