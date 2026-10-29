"""Service-side generation contract, independent of HTTP, SDKs and model runtimes."""

from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class CompletionRequest:
    model: str
    system: str
    user: str
    json_schema: dict[str, Any]
    max_output_tokens: int = 8000
    timeout_seconds: float = 90


class CompletionError(RuntimeError):
    """Safe provider error: never includes source text, credentials or raw responses."""

    def __init__(
        self,
        code: Literal["provider_failed", "invalid_response", "incomplete_response", "response_too_large"],
    ):
        self.code = code
        super().__init__(code)


class CompletionProvider(Protocol):
    def complete(self, request: CompletionRequest) -> str:
        """Return complete JSON text; enforce the timeout/limit or raise CompletionError.

        SDK/local implementations must enforce remote opt-in where applicable, avoid logging
        private input, and translate provider exceptions into safe errors. No persistence here.
        """
        ...
