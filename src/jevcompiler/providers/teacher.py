"""Structured teacher generation over OpenAI-compatible HTTP endpoints."""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from jevcompiler.providers.discovery import discover_teacher_providers, select_teacher
from jevcompiler.security import redact
from jevcompiler.specs.task import TeacherConfig

T = TypeVar("T", bound=BaseModel)
TeacherMessage = Mapping[str, str]


class TeacherError(RuntimeError):
    """A teacher provider failed without exposing credential material."""


@dataclass(frozen=True, slots=True)
class StructuredGeneration(Generic[T]):
    value: T
    provider: str
    requested_model: str
    actual_model: str
    usage: dict[str, Any]


class TeacherProvider(Protocol):
    async def structured_generate(
        self,
        messages: Sequence[TeacherMessage],
        schema: type[T],
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> StructuredGeneration[T]: ...


def _schema_name(schema: type[BaseModel]) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", schema.__name__)[:64]


def _json_content(content: Any) -> Any:
    if not isinstance(content, str):
        raise TeacherError("teacher response content must be a JSON string")
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1])
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise TeacherError(f"teacher returned invalid JSON: {exc.msg}") from None


class OpenAICompatibleTeacher:
    """Use JSON-schema chat completions across Ollama, LM Studio, and OpenRouter."""

    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 2,
        require_parameters: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.max_retries = max_retries
        self.require_parameters = require_parameters
        self._owns_client = client is None
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if provider == "openrouter":
            headers.update({"HTTP-Referer": "https://github.com/", "X-Title": "Jev Compiler"})
        self._client = client or httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            headers=headers,
            timeout=timeout,
        )

    async def structured_generate(
        self,
        messages: Sequence[TeacherMessage],
        schema: type[T],
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> StructuredGeneration[T]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [dict(message) for message in messages],
            "stream": False,
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": _schema_name(schema),
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            },
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if self.require_parameters:
            payload["provider"] = {"require_parameters": True, "allow_fallbacks": True}

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.post("chat/completions", json=payload)
                retryable = response.status_code == 429 or response.status_code >= 500
                if retryable and attempt < self.max_retries:
                    retry_after = min(float(response.headers.get("retry-after", "1")), 5.0)
                    await asyncio.sleep(max(retry_after, 0.0))
                    continue
                response.raise_for_status()
            except (httpx.HTTPError, ValueError) as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2**attempt, 5))
                    continue
                raise TeacherError(f"{self.provider} request failed: {redact(str(exc))}") from None
            try:
                body = response.json()
                choices = body["choices"]
                content = choices[0]["message"]["content"]
                value = schema.model_validate(_json_content(content))
            except (
                KeyError,
                IndexError,
                TypeError,
                ValueError,
                ValidationError,
                TeacherError,
            ) as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2**attempt, 5))
                    continue
                raise TeacherError(
                    f"{self.provider} returned an invalid structured response: "
                    f"{redact(str(exc))}"
                ) from None
            return StructuredGeneration(
                value=value,
                provider=self.provider,
                requested_model=self.model,
                actual_model=str(body.get("model") or self.model),
                usage=body.get("usage") if isinstance(body.get("usage"), dict) else {},
            )
        raise TeacherError(f"{self.provider} request produced no response")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> OpenAICompatibleTeacher:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()


class RecordedTeacherProvider:
    """Deterministic structured teacher used by unit tests and offline replay."""

    def __init__(
        self,
        responses: Sequence[BaseModel | dict[str, Any]],
        *,
        provider: str = "recorded",
        model: str = "recorded-model",
    ) -> None:
        if not responses:
            raise ValueError("at least one recorded teacher response is required")
        self._responses = list(responses)
        self.provider = provider
        self.model = model
        self.calls: list[dict[str, Any]] = []

    async def structured_generate(
        self,
        messages: Sequence[TeacherMessage],
        schema: type[T],
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> StructuredGeneration[T]:
        if not self._responses:
            raise TeacherError("recorded teacher responses are exhausted")
        raw = self._responses.pop(0)
        value = raw if isinstance(raw, schema) else schema.model_validate(raw)
        self.calls.append(
            {
                "messages": [dict(message) for message in messages],
                "schema": schema,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return StructuredGeneration(
            value=value,
            provider=self.provider,
            requested_model=self.model,
            actual_model=self.model,
            usage={},
        )


async def resolve_teacher(config: TeacherConfig) -> OpenAICompatibleTeacher:
    """Resolve a configured teacher without ever selecting paid routing implicitly."""
    provider = config.provider
    model = config.model
    base_url = str(config.base_url) if config.base_url else None

    if provider == "auto":
        availability = await discover_teacher_providers()
        selected, selected_model = select_teacher(
            availability,
            allow_paid=config.allow_paid,
            paid_model=model if config.allow_paid else None,
        )
        provider = "openrouter" if selected.startswith("openrouter") else selected
        model = selected_model

    if provider == "ollama":
        if not model:
            availability = await discover_teacher_providers()
            selected = next((item for item in availability if item.provider == "ollama"), None)
            model = selected.models[0] if selected and selected.models else None
        if not model:
            raise TeacherError("Ollama is selected but no local model is available")
        root = base_url or f"{os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')}/v1"
        return OpenAICompatibleTeacher(
            provider="ollama", base_url=root, model=model, api_key="ollama"
        )

    if provider == "lmstudio":
        if not model:
            availability = await discover_teacher_providers()
            selected = next((item for item in availability if item.provider == "lmstudio"), None)
            model = selected.models[0] if selected and selected.models else None
        if not model:
            raise TeacherError("LM Studio is selected but no loaded model is available")
        root = base_url or os.getenv("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
        return OpenAICompatibleTeacher(
            provider="lmstudio", base_url=root, model=model, api_key="lm-studio"
        )

    if provider == "openrouter":
        model = model or "openrouter/free"
        if model != "openrouter/free" and not config.allow_paid:
            raise TeacherError("paid OpenRouter models require allow_paid: true")
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise TeacherError("OPENROUTER_API_KEY is not configured")
        return OpenAICompatibleTeacher(
            provider="openrouter",
            base_url=base_url or "https://openrouter.ai/api/v1",
            model=model,
            api_key=api_key,
            require_parameters=True,
        )

    if provider == "openai":
        if not model:
            raise TeacherError("OpenAI requires an explicit model")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise TeacherError("OPENAI_API_KEY is not configured")
        return OpenAICompatibleTeacher(
            provider="openai",
            base_url=base_url or "https://api.openai.com/v1",
            model=model,
            api_key=api_key,
        )

    if provider == "openai-compatible":
        if not base_url or not model:
            raise TeacherError("openai-compatible requires base_url and model")
        return OpenAICompatibleTeacher(
            provider="openai-compatible",
            base_url=base_url,
            model=model,
            api_key=os.getenv("OPENAI_COMPAT_API_KEY"),
        )

    raise TeacherError(f"unsupported teacher provider: {provider}")
