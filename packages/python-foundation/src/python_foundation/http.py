"""Bounded HTTPX clients. Lifetimes are application-owned; retries are never implicit."""

from collections.abc import Awaitable, Callable

import httpx

from python_foundation.errors import BusinessError, ErrorCategory, ErrorSpec
from python_foundation.settings import FoundationSettings

REMOTE_FAILED = ErrorSpec(
    "REMOTE_SERVICE_FAILED", ErrorCategory.UNAVAILABLE, "A required service is unavailable."
)


def http_client(settings: FoundationSettings, *, base_url: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        timeout=settings.http_timeout_seconds,
        limits=httpx.Limits(max_connections=settings.http_max_connections),
        follow_redirects=False,
        trust_env=False,
    )


def async_http_client(settings: FoundationSettings, *, base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=settings.http_timeout_seconds,
        limits=httpx.Limits(max_connections=settings.http_max_connections),
        follow_redirects=False,
        trust_env=False,
    )


def remote_call[T](operation: Callable[[], T]) -> T:
    """The operation must call response.raise_for_status() to classify HTTP failures."""
    try:
        return operation()
    except httpx.HTTPError as failure:
        raise BusinessError(REMOTE_FAILED) from failure


async def async_remote_call[T](operation: Callable[[], Awaitable[T]]) -> T:
    try:
        return await operation()
    except httpx.HTTPError as failure:
        raise BusinessError(REMOTE_FAILED) from failure
