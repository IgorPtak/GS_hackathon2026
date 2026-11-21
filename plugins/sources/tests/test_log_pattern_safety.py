"""log_tail refuses unsafe or oversized line patterns like invalid ones."""

from __future__ import annotations

import pytest
from alerting_contracts.config import SourceConfig

from plugins.sources._log_files import LineParseError, compile_pattern, parse_line


def source_with(pattern: str) -> SourceConfig:
    return SourceConfig(
        id="s", type="log_tail", settings={"line_format": "regex", "line_pattern": pattern}
    )


@pytest.mark.parametrize("pattern", ["(a+)+$", "(a|a)+", r"(a)\1", "(unclosed"])
def test_unsafe_or_invalid_pattern_is_refused(pattern: str) -> None:
    assert compile_pattern(source_with(pattern)) is None


def test_safe_pattern_compiles_and_long_line_is_refused() -> None:
    source = source_with(r"^(?P<word>\S+)")
    pattern = compile_pattern(source)
    assert pattern is not None
    assert parse_line("hello world", source, pattern)["word"] == "hello"
    with pytest.raises(LineParseError, match="longer"):
        parse_line("x" * 9000, source, pattern)
