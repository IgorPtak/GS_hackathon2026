#!/bin/bash
# Steady 200 msg/s for 60 s; hard-kill Redis at t=20 s, start it again 3 s later.
cd "$(dirname "$0")/.."
uv run python loadtest/scenarios.py steady --rate 200 --duration 60 > "$1" 2>&1 &
LOAD=$!
sleep 20
echo "lastsave_age_s=$(( $(date +%s) - $(docker compose exec -T redis redis-cli LASTSAVE | tr -d '\r') ))"
echo "events_len_before_kill=$(docker compose exec -T redis redis-cli XLEN events | tr -d '\r')"
docker kill alerting-redis-1 >/dev/null && echo "killed at $(date +%T)"
sleep 3
docker compose start redis >/dev/null 2>&1 && echo "started at $(date +%T)"
sleep 2
echo "events_len_after_restart=$(docker compose exec -T redis redis-cli XLEN events | tr -d '\r')"
wait $LOAD; echo "load exit=$?"
