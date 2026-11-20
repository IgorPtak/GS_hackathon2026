"""Compare LLMs on turning non-technical runbooks into RunbookStep lists (task B-08-eval).

Usage: PYTHONPATH=contracts:packages/alerting_core:. uv run python scripts/eval_runbook_llm.py \
    --models qwen3.8-27b,deepseek-v4-flash --runs 3 --json out.json

Reads LLM_BASE_URL / LLM_API_KEY / LLM_ALLOWED_HOSTS from the environment or the repo `.env`.
Every runbook (.md and .txt) is normalized as free text so each one goes through the LLM; a run
that falls back to the one-step plain-text path counts as a failure. No client cache is used.
"""

import argparse
import asyncio
import dataclasses
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
# Runnable without PYTHONPATH: contracts, alerting_core and plugins are not installed.
for _path in (ROOT, ROOT / "contracts", ROOT / "packages" / "alerting_core"):
    sys.path.insert(0, str(_path))

import yaml  # noqa: E402
from alerting_contracts.config import ActionConfig, ApprovalPolicy  # noqa: E402
from alerting_contracts.runbooks import RunbookFormat  # noqa: E402
from alerting_core.llm import LlmClient, LlmConfig, LlmError  # noqa: E402
from alerting_core.runbooks.normalize import normalize_runbook_with_llm  # noqa: E402
from eval_runbook_scoring import StepScore, aggregate, score_steps  # noqa: E402

SUFFIXES = (".md", ".txt")


def load_env(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ without overriding existing values."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_actions(directory: Path) -> dict[str, ActionConfig]:
    """Load every action YAML from config/actions."""
    actions = [
        ActionConfig.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
        for f in sorted(directory.glob("*.yaml"))
    ]
    return {action.id: action for action in actions}


def load_cases(directory: Path) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """(name, source text, expected steps) for each runbook that has an .expected.json sibling."""
    cases = []
    for path in sorted(p for p in directory.iterdir() if p.suffix in SUFFIXES):
        expected_path = path.with_name(f"{path.stem}.expected.json")
        expected = json.loads(expected_path.read_text(encoding="utf-8"))["steps"]
        cases.append((path.stem, path.read_text(encoding="utf-8"), expected))
    return cases


def make_client(model: str) -> LlmClient:
    """A cache-free client for `model` using the env connection settings."""
    config = dataclasses.replace(LlmConfig.from_env(), model=model)
    return LlmClient(config)


async def run_once(
    client: LlmClient, name: str, source: str, actions: dict[str, ActionConfig]
) -> tuple[list[dict[str, Any]] | None, float, str | None]:
    """One normalization: (actual steps or None when failed/fallback, seconds, error)."""
    started = time.perf_counter()
    try:
        runbook = await normalize_runbook_with_llm(
            name, name, None, RunbookFormat.text, source, actions, client
        )
    except (ValueError, LlmError) as error:
        return None, time.perf_counter() - started, f"{type(error).__name__}: {error}"
    seconds = time.perf_counter() - started
    if runbook.normalized_by != "llm":
        return None, seconds, "fallback (LLM unavailable, invalid or empty output)"
    steps = [
        {
            "kind": step.kind.value,
            "action": step.action,
            "requires_approval": step.approval is ApprovalPolicy.required,
        }
        for step in runbook.steps
    ]
    return steps, seconds, None


async def evaluate_model(
    model: str,
    cases: list[tuple[str, str, list[dict[str, Any]]]],
    actions: dict[str, ActionConfig],
    runs: int,
) -> dict[str, Any]:
    """All runbooks x runs for one model."""
    client = make_client(model)
    records: list[dict[str, Any]] = []
    for name, source, expected in cases:
        for run in range(1, runs + 1):
            steps, seconds, error = await run_once(client, name, source, actions)
            score = score_steps(expected, steps) if steps is not None else None
            records.append(
                {
                    "runbook": name,
                    "run": run,
                    "seconds": seconds,
                    "error": error,
                    "score": dataclasses.asdict(score) if score else None,
                }
            )
            print(
                f"{model} {name} run {run}: {seconds:.1f}s {'ok' if score else error}", flush=True
            )
    scores = [StepScore(**r["score"]) if r["score"] else None for r in records]
    summary = aggregate(scores, [r["seconds"] for r in records])
    return {"model": model, "summary": summary, "records": records}


def format_report(result: dict[str, Any]) -> str:
    """Markdown summary plus per-runbook table for one model."""
    s = result["summary"]
    lines = [
        f"## {result['model']}",
        "",
        "| runs | valid | precision | recall | approval | exact kinds | p50 s | p90 s |",
        "|---|---|---|---|---|---|---|---|",
        f"| {s['runs']} | {s['valid_rate']:.0%} | {s['action_precision']:.2f} "
        f"| {s['action_recall']:.2f} | {s['approval_accuracy']:.2f} "
        f"| {s['exact_kind_sequence']:.2f} | {s['latency_median_s']:.1f} "
        f"| {s['latency_p90_s']:.1f} |",
        "",
        "| runbook | run | steps (exp/act) | precision | recall | approval | kinds | seconds |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in result["records"]:
        sc = r["score"]
        if sc is None:
            lines.append(
                f"| {r['runbook']} | {r['run']} | FAILED: {r['error']} | | | | "
                f"| {r['seconds']:.1f} |"
            )
            continue
        lines.append(
            f"| {r['runbook']} | {r['run']} "
            f"| {sc['step_count_expected']}/{sc['step_count_actual']} "
            f"| {sc['action_precision']:.2f} | {sc['action_recall']:.2f} "
            f"| {sc['approval_accuracy']:.2f} | {'yes' if sc['exact_kind_sequence'] else 'no'} "
            f"| {r['seconds']:.1f} |"
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--models", default=None, help="comma-separated model names")
    parser.add_argument("--dir", type=Path, default=ROOT / "scripts" / "eval_runbooks")
    parser.add_argument("--runs", type=int, default=1, help="runs per runbook and model")
    parser.add_argument("--json", type=Path, default=None, help="write full results here")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    """Run the eval and return the process exit code."""
    args = parse_args(argv)
    load_env(ROOT / ".env")
    raw = args.models or os.environ.get("LLM_MODEL", "")
    models = [m.strip() for m in raw.split(",") if m.strip()]
    if not models:
        print("no models: pass --models or set LLM_MODEL", file=sys.stderr)
        return 2
    actions = load_actions(ROOT / "config" / "actions")
    cases = load_cases(args.dir)
    results = [await evaluate_model(m, cases, actions, args.runs) for m in models]
    for result in results:
        print("\n" + format_report(result))
    if args.json:
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
