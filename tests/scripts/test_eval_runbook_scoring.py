"""Unit tests for the runbook LLM eval scoring and its expected.json files (no LLM calls)."""

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from eval_runbook_scoring import StepScore, aggregate, percentile, score_steps  # noqa: E402

EVAL_DIR = ROOT / "scripts" / "eval_runbooks"
ACTION_IDS = {
    yaml.safe_load(p.read_text(encoding="utf-8"))["id"]
    for p in (ROOT / "config" / "actions").glob("*.yaml")
}
KINDS = {"text", "check", "action"}


def step(kind: str, action: str | None = None, approval: bool = False) -> dict:
    return {"kind": kind, "action": action, "requires_approval": approval}


def test_perfect_match() -> None:
    steps = [step("check", "http-health-check"), step("action", "escalate", True), step("text")]
    score = score_steps(steps, steps)
    assert score == StepScore(3, 3, 1.0, 1.0, 1.0, True)


def test_missing_and_extra_actions() -> None:
    expected = [step("action", "open-ticket"), step("action", "retry-workflow")]
    actual = [step("action", "open-ticket"), step("action", "escalate", True)]
    score = score_steps(expected, actual)
    assert score.action_precision == 0.5
    assert score.action_recall == 0.5


def test_action_ids_are_a_multiset() -> None:
    expected = [step("action", "open-ticket")]
    actual = [step("action", "open-ticket"), step("action", "open-ticket")]
    score = score_steps(expected, actual)
    assert score.action_precision == 0.5
    assert score.action_recall == 1.0


def test_approval_accuracy_on_matched_actions() -> None:
    expected = [step("action", "retry-workflow", True), step("action", "open-ticket", False)]
    actual = [step("action", "retry-workflow", False), step("action", "open-ticket", False)]
    assert score_steps(expected, actual).approval_accuracy == 0.5


def test_all_manual_runbook() -> None:
    expected = [step("text"), step("text")]
    assert score_steps(expected, [step("text"), step("text")]).action_precision == 1.0
    wrong = score_steps(expected, [step("action", "open-ticket")])
    assert wrong.action_precision == 0.0
    assert wrong.action_recall == 1.0
    assert wrong.exact_kind_sequence is False


def test_empty_actual_scores_zero_recall() -> None:
    score = score_steps([step("action", "escalate", True)], [])
    assert (score.action_precision, score.action_recall, score.approval_accuracy) == (0, 0, 0)


def test_percentile_and_aggregate() -> None:
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9) == 9
    good = score_steps([step("text")], [step("text")])
    summary = aggregate([good, None], [1.0, 3.0])
    assert summary["valid_rate"] == 0.5
    assert summary["latency_median_s"] == 2.0
    assert summary["exact_kind_sequence"] == 1.0


def expected_files() -> list[Path]:
    return sorted(EVAL_DIR.glob("*.expected.json"))


def test_twelve_runbooks_with_expected_files() -> None:
    runbooks = [p for p in EVAL_DIR.iterdir() if p.suffix in {".md", ".txt"}]
    assert len(runbooks) == 12
    for path in runbooks:
        assert path.with_name(f"{path.stem}.expected.json").exists(), path.name


@pytest.mark.parametrize("path", expected_files(), ids=lambda p: p.name)
def test_expected_file_is_valid(path: Path) -> None:
    steps = json.loads(path.read_text(encoding="utf-8"))["steps"]
    assert steps
    for item in steps:
        assert set(item) == {"kind", "action", "requires_approval"}
        assert item["kind"] in KINDS
        assert isinstance(item["requires_approval"], bool)
        assert item["action"] is None or item["action"] in ACTION_IDS
        assert (item["kind"] == "text") == (item["action"] is None)
