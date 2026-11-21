"""Forget rules, runbooks and schema profiles made in the UI, so a demo can start from scratch.

Keeps everything shipped in `config/` and removes only documents that exist in Postgres but not
on disk (made through the UI or API, for example during a rehearsal), plus the unknown-schema
inbox. Without `--yes` it only lists what it would remove.

The API has no DELETE for runbooks and schema profiles, so this talks to the compose Postgres and
Redis containers directly. It is a demo tool: never point it at real data.

Usage:
  uv run python scripts/forget_demo_config.py          # dry run: list what would go
  uv run python scripts/forget_demo_config.py --yes    # remove it and reload every worker
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from alerting_contracts.sse import ConfigChangedEvent

ROOT = Path(__file__).resolve().parent.parent
# kind in config_documents -> folder in config/
KIND_DIRS = {"rule": "rules", "runbook": "runbooks", "schema_profile": "schemas"}
ID_LINE = re.compile(r"^id:\s*['\"]?([A-Za-z0-9_.-]+)['\"]?\s*$", re.MULTILINE)
SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


def shipped_ids(kind: str) -> set[str]:
    """Ids defined by files in config/<dir>: the `id:` line of YAML, else the file name."""
    ids: set[str] = set()
    for path in (ROOT / "config" / KIND_DIRS[kind]).iterdir():
        if path.suffix not in {".yaml", ".yml", ".md", ".txt"}:
            continue
        match = (
            ID_LINE.search(path.read_text(encoding="utf-8"))
            if path.suffix in {".yaml", ".yml"}
            else None
        )
        ids.add(match.group(1) if match else path.stem)
    return ids


def psql(sql: str) -> str:
    user = os.environ.get("POSTGRES_USER", "alerting")
    database = os.environ.get("POSTGRES_DB", "alerting")
    command = ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", user, "-d", database]
    result = subprocess.run(
        [*command, "-At", "-c", sql], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout


def stored_ids(kind: str) -> set[str]:
    rows = psql(f"SELECT id FROM config_documents WHERE kind = '{kind}'")
    return {line.strip() for line in rows.splitlines() if line.strip()}


def publish_reload(kind: str, document_id: str) -> None:
    """One config.changed makes every ConfigRegistry reload all documents from Postgres."""
    event = ConfigChangedEvent(at=datetime.now(UTC), kind=kind, id=document_id, version=1)
    payload = event.model_dump_json()
    for channel in ("config.changed", "broadcast"):
        subprocess.run(
            ["docker", "compose", "exec", "-T", "redis", "redis-cli", "PUBLISH", channel, payload],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="remove; without it, only list")
    args = parser.parse_args(argv)

    extra = {kind: sorted(stored_ids(kind) - shipped_ids(kind)) for kind in KIND_DIRS}
    unknown_count = psql("SELECT count(*) FROM unknown_schema_samples").strip()
    for kind, ids in extra.items():
        print(f"{kind}: {', '.join(ids) if ids else '(none)'}")
    print(f"unknown-schema inbox: {unknown_count} sample(s)")
    if not args.yes:
        print("Dry run. Add --yes to remove these.")
        return 0

    for kind, ids in extra.items():
        safe = [document_id for document_id in ids if SAFE_ID.match(document_id)]
        if safe:
            quoted = ", ".join(f"'{document_id}'" for document_id in safe)
            psql(f"DELETE FROM config_documents WHERE kind = '{kind}' AND id IN ({quoted})")
    psql("DELETE FROM unknown_schema_samples")
    publish_reload("rule", "forget-demo-config")
    print("Removed. Every worker reloads its config now.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
