"""Custom exceptions + global exception handlers.

Every error, whether ours, FastAPI's validation, an HTTPException, a database
failure or an unexpected crash, is returned in ONE shape:

    {"error": {"code": "not_found", "message": "...", "details": null, "request_id": "..."}}

Clients (like our Flask app) only have to understand one error format.
"""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """Base class for errors we raise on purpose from routes/services."""

    status_code = 400
    code = "bad_request"
    default_message = "The request could not be processed."

    def __init__(self, message: str | None = None, *, details: Any = None, headers: dict[str, str] | None = None):
        self.message = message or self.default_message
        self.details = details
        self.headers = headers
        super().__init__(self.message)


class BadRequestError(AppError):
    pass


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    default_message = "Could not validate credentials."

    def __init__(self, message: str | None = None, **kw: Any):
        kw.setdefault("headers", {"WWW-Authenticate": "Bearer"})
        super().__init__(message, **kw)


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    default_message = "You do not have permission to do that."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    default_message = "Resource not found."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    default_message = "This conflicts with existing data."


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"
    default_message = "The uploaded file is too large."


class UnsupportedMediaTypeError(AppError):
    status_code = 415
    code = "unsupported_media_type"
    default_message = "This file type is not supported."


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"
    default_message = "Too many requests. Slow down."


class ExternalServiceError(AppError):
    status_code = 502
    code = "upstream_error"
    default_message = "An external service failed."


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    429: "rate_limited",
}


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": getattr(request.state, "request_id", None),
        }
    }
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(request, exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Catches FastAPI's own 401 (missing token), 404 (unknown URL), 405, ...
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        headers = dict(exc.headers) if exc.headers else None
        return error_response(request, exc.status_code, code, str(exc.detail), headers=headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(p) for p in err["loc"] if p != "body"),
                "message": err["msg"],
                "type": err["type"],
            }
            for err in exc.errors()
        ]
        return error_response(request, 422, "validation_error", "Request validation failed.", details)

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("Integrity error: %s", exc.orig)
        return error_response(request, 409, "conflict", "This conflicts with existing data.")

    @app.exception_handler(SQLAlchemyError)
    async def handle_db_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Database error")  # full detail in logs, nothing leaked to the client
        return error_response(request, 500, "database_error", "A database error occurred.")

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(request, 500, "internal_error", "Something went wrong on our side.")
