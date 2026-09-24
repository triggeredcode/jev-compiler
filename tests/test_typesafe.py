import asyncio

import httpx

from jevcompiler.providers.typesafe import TypeSafeProvider
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

