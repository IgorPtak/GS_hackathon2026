# One image for every Python service (api, ingest, workers, mock-gateway). Each compose service
# picks its entrypoint with `command:`.
FROM python:3.12.16-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH

# Fixed uid so compose volumes and tmpfs mounts can be made writable for this user by number.
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin appuser

WORKDIR /app

# Dependency layer: depends only on the lockfile and the member manifests, so editing source code
# does not reinstall third-party packages. Workspace members are installed after the code is copied.
COPY pyproject.toml uv.lock ./
COPY contracts/pyproject.toml ./contracts/pyproject.toml
COPY packages/alerting_core/pyproject.toml ./packages/alerting_core/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-workspace

# Copy only the Python workspace. Host-side .venv, node_modules and .env stay out of the image
# (see the root .dockerignore).
COPY contracts ./contracts
COPY packages ./packages
COPY services ./services
COPY plugins ./plugins
COPY config ./config
COPY scripts ./scripts
COPY loadtest ./loadtest
COPY tests ./tests

RUN uv sync --frozen --no-dev

# Byte-compile now, as root: the code is root-owned and read-only for appuser, so Python could not
# write __pycache__ at runtime and would recompile on every start.
RUN python -m compileall -q /app/services /app/plugins /app/packages /app/contracts

# Code stays root-owned (read-only for the app user); only mounts that the services write to
# are made writable for appuser in compose.yaml.
USER appuser
