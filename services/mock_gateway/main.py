"""Mock SMS/phone gateway stub (track A, port 8090).

Routes arrive in A-14; this only answers /healthz.
"""

from fastapi import FastAPI

app = FastAPI()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe used by compose healthchecks."""
    return {"status": "ok"}
