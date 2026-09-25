import asyncio

import httpx
import pytest

from jevcompiler.providers.typesafe import TypeSafeError, TypeSafeProvider
from jevcompiler.specs.program import NoulQuestion


def test_typesafe_provider_request_and_response_shape() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-secret"
        payload = __import__("json").loads(request.content)
        assert payload["model"] == "jev-latest"
        assert payload["questions"]["urgent"]["type"] == "noul"
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": {"urgent": {"type": "noul", "noul": 0.87}},
                "usage": {"input_tokens": 9, "output_tokens": 1},
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.typesafe.ai"
    )
    provider = TypeSafeProvider(api_key="test-secret", client=client)
    result = asyncio.run(
        provider.evaluate(
            "Please help now",
            {"urgent": NoulQuestion(type="noul", instructions="Is this urgent?")},
            model="jev-latest",
        )
    )
    asyncio.run(client.aclose())
    assert result.model == "jev-1.13.0"
    assert result.answers["urgent"].noul == 0.87


def test_typesafe_provider_retries_rate_limit_with_bounded_delay() -> None:
    calls = 0
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "30"})
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": {"urgent": {"type": "noul", "noul": 0.75}},
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.typesafe.ai"
    )
    provider = TypeSafeProvider(
        api_key="test-secret",
        client=client,
        max_retries=1,
        sleep=sleep,
    )

    result = asyncio.run(
        provider.evaluate(
            "Please help now",
            {"urgent": NoulQuestion(type="noul", instructions="Is this urgent?")},
        )
    )

    asyncio.run(client.aclose())
    assert result.answers["urgent"].noul == 0.75
    assert calls == 2
    assert delays == [5.0]


def test_typesafe_provider_retries_server_error_when_listing_models() -> None:
    calls = 0
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"models": [{"id": "jev-latest"}]})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.typesafe.ai"
    )
    provider = TypeSafeProvider(
        api_key="test-secret",
        client=client,
        max_retries=1,
        sleep=sleep,
    )

    models = asyncio.run(provider.list_models())

    asyncio.run(client.aclose())
    assert models == [{"id": "jev-latest"}]
    assert calls == 2
    assert delays == [1.0]


def test_typesafe_provider_does_not_retry_client_error() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": "invalid request"})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.typesafe.ai"
    )
    provider = TypeSafeProvider(api_key="test-secret", client=client)

    with pytest.raises(TypeSafeError, match="TypeSafe request failed"):
        asyncio.run(
            provider.evaluate(
                "Please help now",
                {"urgent": NoulQuestion(type="noul", instructions="Is this urgent?")},
            )
        )

    asyncio.run(client.aclose())
    assert calls == 1


def test_typesafe_provider_does_not_retry_ambiguous_transport_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("connection failed", request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.typesafe.ai"
    )
    provider = TypeSafeProvider(api_key="test-secret", client=client)

    with pytest.raises(TypeSafeError, match="TypeSafe request failed"):
        asyncio.run(
            provider.evaluate(
                "Please help now",
                {"urgent": NoulQuestion(type="noul", instructions="Is this urgent?")},
            )
        )

    asyncio.run(client.aclose())
    assert calls == 1


def test_typesafe_provider_rejects_negative_retries() -> None:
    with pytest.raises(ValueError, match="max_retries cannot be negative"):
        TypeSafeProvider(api_key="test-secret", max_retries=-1)
