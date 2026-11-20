.PHONY: up down logs test test-integration lint format smoke loadtest

GATE ?= 3h

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

# pytest exits 5 when no tests are collected; that is success while the suites are empty.
test:
	uv run pytest -q; rc=$$?; if [ $$rc -eq 5 ]; then exit 0; else exit $$rc; fi

test-integration:
	uv run pytest -m integration tests/integration -q

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

smoke:
	uv run python scripts/smoke_test.py --gate $${GATE:-3h}

loadtest:
	uv run python loadtest/scenarios.py steady --duration 60
