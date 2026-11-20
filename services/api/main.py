"""HTTP API stub (track B, port 8000). Routes arrive in B-01; this only answers /healthz."""

from fastapi import FastAPI

app = FastAPI()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe used by compose healthchecks."""
    return {"status": "ok"}
