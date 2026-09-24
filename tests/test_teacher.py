import asyncio
import json

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from jevcompiler.providers.teacher import (
    OpenAICompatibleTeacher,
    TeacherError,
    resolve_teacher,
)
from jevcompiler.specs.task import TeacherConfig


class ExampleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


def test_openai_compatible_teacher_uses_strict_json_schema() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/api/v1/chat/completions"
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert payload["provider"]["require_parameters"] is True
        return httpx.Response(
            200,
            json={
                "model": "free/actual-model",
                "choices": [{"message": {"content": '{"answer":"billing"}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://openrouter.ai/api/v1/"
    )
    teacher = OpenAICompatibleTeacher(
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
        model="openrouter/free",
        api_key="secret",
        require_parameters=True,
        client=client,
    )
    result = asyncio.run(
        teacher.structured_generate(
            [{"role": "user", "content": "Choose."}], ExampleOutput, temperature=0
        )
    )
    asyncio.run(client.aclose())
    assert result.value.answer == "billing"
    assert result.actual_model == "free/actual-model"


def test_teacher_rejects_invalid_structured_content() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={"model": "local", "choices": [{"message": {"content": "not json"}}]},
        )
    )
    client = httpx.AsyncClient(transport=transport, base_url="http://local/v1/")
    teacher = OpenAICompatibleTeacher(
        provider="local",
        base_url="http://local/v1",
        model="model",
        client=client,
        max_retries=0,
    )
    with pytest.raises(TeacherError, match="invalid JSON"):
        asyncio.run(teacher.structured_generate([], ExampleOutput))
    asyncio.run(client.aclose())


def test_teacher_retries_invalid_structured_content() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = "not json" if calls == 1 else '{"answer":"billing"}'
        return httpx.Response(
            200,
            json={"model": "local", "choices": [{"message": {"content": content}}]},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://local/v1/",
    )
    teacher = OpenAICompatibleTeacher(
        provider="local",
        base_url="http://local/v1",
        model="model",
        client=client,
        max_retries=1,
    )

    result = asyncio.run(teacher.structured_generate([], ExampleOutput))

    asyncio.run(client.aclose())
    assert result.value.answer == "billing"
    assert calls == 2


def test_paid_openrouter_requires_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    config = TeacherConfig(provider="openrouter", model="vendor/paid-model")
    with pytest.raises(TeacherError, match="allow_paid"):
        asyncio.run(resolve_teacher(config))


def test_free_openrouter_is_allowed(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    teacher = asyncio.run(
        resolve_teacher(TeacherConfig(provider="openrouter", model="openrouter/free"))
    )
    assert teacher.model == "openrouter/free"
    asyncio.run(teacher.aclose())
