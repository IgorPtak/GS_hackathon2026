"""Exception handlers: every error leaves the api as an ErrorResponse."""

from alerting_contracts.api import ErrorResponse
from alerting_core.logging import get_logger
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = get_logger(__name__)

_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_failed",
    503: "unavailable",
}


def error_response(status: int, error: str, message: str) -> JSONResponse:
    """Build the contract `ErrorResponse` body."""
    body = ErrorResponse(error=error, message=message)
    return JSONResponse(body.model_dump(mode="json"), status_code=status)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _CODES.get(exc.status_code, "internal_error" if exc.status_code >= 500 else "error")
    return error_response(exc.status_code, code, str(exc.detail))


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    parts = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
    return error_response(422, "validation_failed", "; ".join(parts))


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    log.error(
        "unhandled_error",
        extra={"path": request.url.path, "error": repr(exc)},
        exc_info=exc,
    )
    return error_response(500, "internal_error", "internal server error")


def install_error_handlers(app: FastAPI) -> None:
    """Register the three handlers on `app`."""
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unexpected_error)
