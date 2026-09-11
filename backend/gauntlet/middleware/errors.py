"""Error envelope (SRS 10.1, 28.1): {"error": {"code", "message", "field", "correlation_id"}}.

Stable codes (SRS 10.3). No stack trace ever reaches a client; the correlation id ties the response to
the server log line.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from gauntlet.middleware.request_id import current_correlation_id

log = logging.getLogger("gauntlet.api")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, field: str | None = None,
                 headers: dict[str, str] | None = None, extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.field = status, code, message, field
        self.headers = headers or {}
        self.extra = extra or {}


def not_found(what: str = "resource") -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def conflict(code: str, message: str, **extra: Any) -> ApiError:
    return ApiError(409, code, message, extra=extra)


def invalid(message: str, field: str | None = None, **extra: Any) -> ApiError:
    return ApiError(422, "validation_failed", message, field, extra=extra)


def _body(code: str, message: str, field: str | None = None, **extra: Any) -> dict[str, Any]:
    err = {"code": code, "message": message, "correlation_id": current_correlation_id()}
    if field:
        err["field"] = field
    err.update(extra)
    return {"error": err}


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        if exc.status == 404:
            log.warning("not_found", extra={"code": exc.code})
        return JSONResponse(_body(exc.code, exc.message, exc.field, **exc.extra), status_code=exc.status,
                            headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        loc = [str(x) for x in first.get("loc", []) if x not in ("body", "query", "path")]
        pointer = "/" + "/".join(loc) if loc else None
        return JSONResponse(_body("validation_failed", first.get("msg", "invalid request"), pointer), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "unauthenticated", 403: "forbidden_scope", 404: "not_found", 405: "method_not_allowed",
                429: "rate_limited"}.get(exc.status_code, "error")
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", extra={"error": type(exc).__name__})
        return JSONResponse(_body("internal_error", "Something went wrong on our side."), status_code=500)
