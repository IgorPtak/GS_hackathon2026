# One image for every Python service (api, ingest, workers, mock-gateway). Each compose service
# picks its entrypoint with `command:`.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app

# Copy only the Python workspace. Host-side .venv, node_modules and .env stay out of the image.
COPY pyproject.toml uv.lock ./
COPY contracts ./contracts
COPY packages ./packages
COPY services ./services
COPY plugins ./plugins
COPY config ./config
COPY scripts ./scripts
COPY loadtest ./loadtest
COPY tests ./tests

RUN uv sync --frozen --no-dev
