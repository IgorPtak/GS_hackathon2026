"""Ingest HTTP service stub (track A, port 8001).

Routes arrive in A-04; this only answers /healthz.
"""

from fastapi import FastAPI

app = FastAPI()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe used by compose healthchecks."""
    return {"status": "ok"}
