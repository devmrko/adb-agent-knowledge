"""Safe error responses, request correlation and structured diagnostic logs."""

import contextvars
import json
import logging
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from python_foundation.errors import AccessDenied, AuthenticationRequired, BusinessError, ErrorCategory
from python_foundation.security import Security

request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    """Log explicitly chosen messages; does not automatically serialize exception text or request bodies."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "requestId": request_id.get(),
            },
            ensure_ascii=False,
        )


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("python_foundation")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False


def problem(status: int, code: str, detail: str, *, correlation: str | None = None) -> JSONResponse:
    return JSONResponse(
        {
            "type": "about:blank",
            "title": HTTPStatus(status).phrase,
            "status": status,
            "detail": detail,
            "code": code,
            "requestId": correlation or request_id.get(),
        },
        status_code=status,
        media_type="application/problem+json",
    )


class RequestContextMiddleware:
    """Pure ASGI middleware preserves context through threaded handlers and async dependencies."""

    def __init__(self, app: ASGIApp, max_request_bytes: int = 1_048_576) -> None:
        self.app = app
        self.maximum = max_request_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        correlation = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = correlation
        token = request_id.set(correlation)
        started = False
        received = 0

        async def correlated_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"]
                message["headers"] = headers + [(b"x-request-id", correlation.encode())]
            await send(message)

        async def bounded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.maximum:
                    raise HTTPException(413, "Request body too large")
            return message

        try:
            try:
                await self.app(scope, bounded_receive, correlated_send)
            except Exception as failure:
                if started:
                    raise
                # Log only type and correlation: raw exception messages may contain secrets.
                logging.getLogger("python_foundation.web").error(
                    "Unhandled failure type=%s", type(failure).__name__
                )
                await problem(500, "INTERNAL_ERROR", "An unexpected error occurred.")(
                    scope, receive, correlated_send
                )
        finally:
            request_id.reset(token)


def install_web(app: FastAPI, security: Security) -> None:
    app.state.security = security
    app.add_middleware(RequestContextMiddleware, max_request_bytes=security.settings.max_request_bytes)

    @app.exception_handler(BusinessError)
    async def business(request: Request, exception: BusinessError) -> JSONResponse:
        status = {
            ErrorCategory.VALIDATION: 400,
            ErrorCategory.NOT_FOUND: 404,
            ErrorCategory.CONFLICT: 409,
            ErrorCategory.UNAVAILABLE: 503,
        }[exception.error.category]
        return problem(status, exception.error.code, exception.error.message)

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exception: RequestValidationError) -> JSONResponse:
        response = problem(400, "VALIDATION_FAILED", "Input validation failed")
        data = cast(dict[str, Any], json.loads(bytes(response.body)))
        data["fieldErrors"] = [
            {"field": ".".join(str(part) for part in error["loc"][1:]), "code": error["type"]}
            for error in exception.errors()
        ]
        return JSONResponse(data, status_code=400, media_type="application/problem+json")

    @app.exception_handler(AuthenticationRequired)
    async def authentication(
        request: Request, exception: AuthenticationRequired
    ) -> JSONResponse | RedirectResponse:
        if (
            not security.token_route(security.path(request))
            and not security.path(request).startswith("/api/")
            and "text/html" in request.headers.get("accept", "")
            and any(getattr(route, "name", None) == "login_page" for route in request.app.routes)
        ):
            return RedirectResponse(str(request.url_for("login_page")), status_code=303)
        response = problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")
        if security.token_route(security.path(request)):
            response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @app.exception_handler(AccessDenied)
    async def denied(request: Request, exception: AccessDenied) -> JSONResponse:
        return problem(403, "ACCESS_DENIED", "Access denied")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exception: HTTPException) -> JSONResponse:
        response = problem(exception.status_code, "HTTP_ERROR", HTTPStatus(exception.status_code).phrase)
        response.headers.update(exception.headers or {})
        return response
