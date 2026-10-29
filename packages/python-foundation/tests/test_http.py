import asyncio

import httpx
import pytest

from python_foundation.errors import BusinessError
from python_foundation.http import async_remote_call, remote_call


def test_remote_error_is_safe_and_not_retried():
    calls = []
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(503, text="private diagnostic")
        )
    ) as client:

        def operation():
            response = client.get("https://service.example")
            response.raise_for_status()
            return response.text

        with pytest.raises(BusinessError) as caught:
            remote_call(operation)
        assert len(calls) == 1
        assert "private" not in str(caught.value)
        assert isinstance(caught.value.__cause__, httpx.HTTPStatusError)


def test_async_remote_timeout_mapping():
    async def operation():
        raise httpx.ReadTimeout("private-url-and-token")

    with pytest.raises(BusinessError, match="unavailable"):
        asyncio.run(async_remote_call(operation))
