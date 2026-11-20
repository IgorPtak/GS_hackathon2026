"""Exception handlers: every error leaves the api as an ErrorResponse."""

from alerting_contracts.api import ConfigValidationError, ErrorResponse
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


class ApiError(Exception):
    """Raise to answer with a specific ErrorResponse code (e.g. 409 invalid_transition)."""

    def __init__(self, status: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.error = error
        self.message = message


def error_response(
    status: int, error: str, message: str, details: list[ConfigValidationError] | None = None
) -> JSONResponse:
    """Build the contract `ErrorResponse` body."""
    body = ErrorResponse(error=error, message=message, details=details or [])
    return JSONResponse(body.model_dump(mode="json"), status_code=status)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _CODES.get(exc.status_code, "internal_error" if exc.status_code >= 500 else "error")
    return error_response(exc.status_code, code, str(exc.detail))


async def _api_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return error_response(exc.status, exc.error, exc.message)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # Union member names pydantic inserts into `loc` (capitalised) are not config keys; drop them.
    details = [
        ConfigValidationError(
            path=".".join(str(p) for p in e["loc"] if not (isinstance(p, str) and p[:1].isupper())),
            message=e["msg"],
        )
        for e in exc.errors()
    ]
    message = "; ".join(f"{d.path}: {d.message}" for d in details)
    return error_response(422, "validation_failed", message, details)


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    log.error(
        "unhandled_error",
        extra={"path": request.url.path, "error": repr(exc)},
        exc_info=exc,
    )
    return error_response(500, "internal_error", "internal server error")


def install_error_handlers(app: FastAPI) -> None:
    """Register the handlers on `app`."""
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unexpected_error)
