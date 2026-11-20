# Changelog

One line per task: `- <ID> <title>: <what changed>`. Newest at the bottom.

- S-00 contracts v1: Pydantic contracts, generated JSON Schemas and OpenAPI components, config examples, reconstructed fixtures.
- S-02 initial migration: 11 tables from contracts/storage.md with partial indexes (unrelayed outbox, open alerts, pending approval codes)
- S-01 contract generator: scripts/generate_contracts.py regenerates contracts/schemas, openapi components.schemas (paths untouched) and web/src/api/schema.gen.ts; --check detects drift, validates $refs and config examples.
- B-00 web scaffold: Vite + React + TS strict + Tailwind + ESLint/Prettier, tab layout, TeamPicker from GET /api/v1/config, openapi-fetch client, nginx Dockerfile with API proxy.
- S-03 seed demo configuration: full demo set in config/, loadtest/fixtures, scripts/validate_config.py.
- B-08 hour-1 LLM check: Qwen3.8-27B @ llm.hpc.psnc.pl (OpenAI-compatible, json_schema), 4.7/4.5/4.7 s, median 4.7 s, 3/3 valid, restart-pricing-adapter approval=required.
