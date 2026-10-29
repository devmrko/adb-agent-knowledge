"""Public error definitions stay independent of HTTP and database libraries."""

from dataclasses import dataclass
from enum import StrEnum


class ErrorCategory(StrEnum):
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ErrorSpec:
    code: str
    category: ErrorCategory
    message: str

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.message.strip():
            raise ValueError("Error code and safe message are required")


class BusinessError(Exception):
    """Expected failure. Use 'raise BusinessError(spec) from cause' for diagnostics.

    The message must never contain SQL, tokens, rejected values or remote response bodies.
    """

    def __init__(self, error: ErrorSpec) -> None:
        super().__init__(error.message)
        self.error = error


class AuthenticationRequired(Exception):
    """No acceptable authenticated actor for this request."""


class AccessDenied(Exception):
    """Actor lacks authority or a session request has no valid CSRF token."""
