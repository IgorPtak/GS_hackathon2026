#!/bin/bash
# Steady 100 msg/s for 60 s; at t=15 s stop delivery 3 s, wipe the unread deliveries, restart.
cd "$(dirname "$0")/.."
uv run python loadtest/scenarios.py steady --rate 100 --duration 60 > "$1" 2>&1 &
LOAD=$!
sleep 15
docker compose stop delivery >/dev/null 2>&1
sleep 3
echo "unread before wipe: $(docker compose exec -T redis redis-cli XINFO GROUPS deliveries | paste - - | awk '$1=="lag"{print $2}')"
docker compose exec -T redis redis-cli XTRIM deliveries MAXLEN 0 | tr -d '\r' | sed 's/^/entries wiped: /'
docker compose start delivery >/dev/null 2>&1; echo "delivery restarted $(date +%T)"
wait $LOAD
