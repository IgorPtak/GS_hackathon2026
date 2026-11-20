"""Hour-1 LLM check: normalize the pricing runbook 3 times via LlmClient.

Usage: PYTHONPATH=contracts:packages/alerting_core python scripts/check_llm.py
Exit 1 if the median latency exceeds 20 s or fewer than 2 runs are valid.
"""

import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

from alerting_contracts.runbooks import RunbookStep
from alerting_core.llm import LlmClient, LlmConfig, LlmError
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
RUNS = 3
MAX_MEDIAN_SECONDS = 20
MIN_VALID = 2

SYSTEM = (
    "You convert an operations runbook written in free text into ordered, normalized steps. "
    "Return JSON only, matching the given schema. index starts at 0. "
    "Use {{field}} placeholders for values that come from the alert (e.g. {{feed}}, {{instrument}}). "
    'Set approval to "required" for steps the text says need approval.\n\n'
    "Available action ids (use only these in `action`):\n"
    "- http-health-check (kind check): params {url}\n"
    "- retry-workflow (kind action): params {workflow_id}\n"
    "- restart-pricing-adapter (kind action, approval required): params {feed}\n"
    "- open-ticket (kind action): params {summary}\n"
    "- escalate (kind action, approval required): params {workflow_id, reason}\n"
    'Steps that match no action are kind "text" with action null.'
)


class StepsResponse(BaseModel):
    """LLM answer: normalized runbook steps."""

    steps: list[RunbookStep]


def load_env(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ without overriding existing values."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def main() -> int:
    """Run the check and return the process exit code."""
    load_env(ROOT / ".env")
    client = LlmClient(LlmConfig.from_env())
    text = (ROOT / "contracts/fixtures/runbooks/pricing-stale-feed.txt").read_text()
    latencies: list[float] = []
    valid = 0
    last: StepsResponse | None = None
    for run in range(1, RUNS + 1):
        started = time.perf_counter()
        try:
            result = await client.generate(text, StepsResponse, system=SYSTEM)
        except LlmError as error:
            latencies.append(time.perf_counter() - started)
            print(
                f"run {run}: {latencies[-1]:.1f}s FAILED {type(error).__name__}: {error}"
            )
            continue
        latencies.append(time.perf_counter() - started)
        assert isinstance(result, StepsResponse)
        valid += 1
        last = result
        print(f"run {run}: {latencies[-1]:.1f}s VALID steps={len(result.steps)}")
    median = statistics.median(latencies)
    restart = (
        next((s for s in last.steps if s.action == "restart-pricing-adapter"), None)
        if last
        else None
    )
    print(f"model={client.model} host={client.base_host}")
    print(
        f"median={median:.1f}s valid={valid}/{RUNS} steps={len(last.steps) if last else 0}"
    )
    print(
        f"restart-pricing-adapter approval required: {restart is not None and restart.approval == 'required'}"
    )
    return 1 if median > MAX_MEDIAN_SECONDS or valid < MIN_VALID else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
