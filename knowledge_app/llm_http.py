"""OpenAI-compatible HTTP implementation for self-hosted and remote LLM endpoints."""

import json
from typing import Any

import httpx
from pydantic import SecretStr

from knowledge_app.llm import CompletionError, CompletionRequest
from knowledge_app.provider_http import endpoint


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        url: str,
        api_key: SecretStr | None = None,
        allow_remote: bool = False,
        structured_output: bool = False,
        reasoning_effort: str | None = None,
    ):
        self.url = endpoint(url, allow_remote=allow_remote)
        self.api_key = api_key if api_key is not None else SecretStr("")
        self.structured_output = structured_output
        self.reasoning_effort = reasoning_effort

    def complete(self, request: CompletionRequest) -> str:
        try:
            return self._complete(request)
        except CompletionError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise CompletionError("provider_failed") from None

    def _complete(self, request: CompletionRequest) -> str:
        body: dict[str, Any] = dict(
            model=request.model,
            temperature=0,
            max_tokens=request.max_output_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": request.system},
                {
                    "role": "user",
                    "content": request.user,
                },
            ],
        )
        if self.structured_output:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "graph_result", "strict": True, "schema": request.json_schema},
            }
        if self.url.rstrip("/") == "https://openrouter.ai/api/v1":
            body["provider"] = {"require_parameters": True, "data_collection": "deny"}
            body["reasoning"] = {"enabled": False}
        if self.reasoning_effort is not None:
            body["reasoning_effort"] = self.reasoning_effort
        headers = (
            {"Authorization": "Bearer " + self.api_key.get_secret_value()}
            if self.api_key.get_secret_value()
            else {}
        )
        with httpx.Client(timeout=request.timeout_seconds, trust_env=False, follow_redirects=False) as client:
            with client.stream(
                "POST", self.url.rstrip("/") + "/chat/completions", json=body, headers=headers
            ) as response:
                response.raise_for_status()
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 1_000_000:
                        raise CompletionError("response_too_large")
        data = json.loads(raw)
        choice = data["choices"][0]
        if choice.get("finish_reason") not in {None, "stop"}:
            raise CompletionError("incomplete_response")
        result = choice["message"]["content"]
        if not isinstance(result, str) or not result.strip():
            raise CompletionError("invalid_response")
        return result
