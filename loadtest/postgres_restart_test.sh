#!/bin/bash
# Steady 100 msg/s for 60 s inside the compose network; restart Postgres at t=15 s.
set -uo pipefail

cd "$(dirname "$0")/.."

LOG_FILE="${1:-}"
CLEANUP_LOG=0
if [ -z "$LOG_FILE" ]; then
    LOG_FILE="$(mktemp -t postgres-restart-load.XXXXXX)"
    CLEANUP_LOG=1
fi
cleanup() {
    if [ "$CLEANUP_LOG" -eq 1 ] && [ -f "$LOG_FILE" ]; then
        rm -f "$LOG_FILE"
    fi
}
trap cleanup EXIT

docker run --rm --network alerting_default -v "$PWD":/work -w /work \
    -e INGEST_URL=http://ingest:8001 \
    -e LOADTEST_DATABASE_URL=postgresql://alerting:change-me-local-only@postgres:5432/alerting \
    -e LOADTEST_REDIS_URL=redis://redis:6379/0 \
    alerting-python:dev python loadtest/scenarios.py steady --rate 100 --duration 60 \
    > "$LOG_FILE" 2>&1 &
LOAD=$!

sleep 15
echo "restarting alerting-postgres-1 at $(date +%T)"
RESTART_EXIT=0
docker restart alerting-postgres-1 >/dev/null || RESTART_EXIT=$?
echo "restarted alerting-postgres-1 at $(date +%T) (exit=$RESTART_EXIT)"

LOAD_EXIT=0
wait "$LOAD" || LOAD_EXIT=$?

cat "$LOG_FILE"
echo "load exit=$LOAD_EXIT"

RESULT_PATH="$(sed -n 's/^wrote //p' "$LOG_FILE" | tail -n 1 | sed 's#^/work/##')"
if [ -z "$RESULT_PATH" ] || [ ! -f "$RESULT_PATH" ]; then
    echo "ERROR: missing steady result JSON in load output" >&2
    exit 1
fi

LOST_CHECK=0
python3 - "$RESULT_PATH" <<'PY' || LOST_CHECK=$?
import json
import sys

with open(sys.argv[1]) as fh:
    step = json.load(fh)["steps"][0]

lost = step["lost"]
settled = step["is_settled"]
print(
    f"summary: run_id={step['run_id']} accepted={step['accepted']} "
    f"delivered={step['delivered']}/{step['expected_deliveries']} "
    f"fallback={step['covered_by_fallback']} lost={lost} settled={settled}"
)
sys.exit(0 if (lost == 0 and settled) else 1)
PY

if [ "$RESTART_EXIT" -ne 0 ] || [ "$LOAD_EXIT" -ne 0 ] || [ "$LOST_CHECK" -ne 0 ]; then
    exit 1
fi
