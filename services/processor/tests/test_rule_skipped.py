"""A rule that cannot compile is skipped and logged once, with its validation errors."""

import pytest

from services.processor.evaluation import RuleSet

from .conftest import load_snapshot


def test_uncompilable_rule_logs_rule_skipped_with_errors(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise ValueError("bad condition")

    monkeypatch.setattr("services.processor.evaluation.compile_condition", boom)
    rule_set = RuleSet(load_snapshot())
    assert rule_set.rule_count == 0
    records = [r for r in caplog.records if r.getMessage() == "rule_skipped"]
    assert records
    assert records[0].error == "bad condition"
    assert isinstance(records[0].errors, list)
