from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from jevcompiler.providers.base import SystemOneResult
from jevcompiler.security import redact
from jevcompiler.specs.program import Question


class TypeSafeError(RuntimeError):
    """A TypeSafe request failed without exposing credential material."""


class TypeSafeProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.typesafe.ai",
        timeout: float = 30.0,
        max_retries: int = 2,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self._api_key = api_key or os.getenv("TYPESAFE_API_KEY")
        if not self._api_key:
            raise TypeSafeError("TYPESAFE_API_KEY is not configured")
        self._owns_client = client is None
        self._max_retries = max_retries
        self._sleep = sleep
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("retry-after")
        if retry_after is not None:
            try:
                return min(max(float(retry_after), 0.0), 5.0)
            except ValueError:
                pass
        return min(float(2**attempt), 5.0)

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            response = await self._client.request(
                method,
                path,
                headers=self._headers,
                **kwargs,
            )
            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and attempt < self._max_retries:
                await self._sleep(self._retry_delay(response, attempt))
                continue
            return response
        raise TypeSafeError("TypeSafe request produced no response")

    async def evaluate(
        self,
        state: Any,
        questions: dict[str, Question],
        *,
        model: str = "jev-latest",
    ) -> SystemOneResult:
        payload = {
            "state": state,
            "model": model,
            "questions": {
                key: question.model_dump(mode="json", exclude_none=True)
                for key, question in questions.items()
            },
        }
        try:
            response = await self._request("POST", "/v1/systemone", json=payload)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise TypeSafeError("TypeSafe returned a non-object response")
            return SystemOneResult.from_api(body)
        except TypeSafeError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            safe_message = redact(str(exc))
            raise TypeSafeError(f"TypeSafe request failed: {safe_message}") from None

    async def list_models(self) -> list[dict[str, Any]]:
        try:
            response = await self._request("GET", "/v1/models")
            response.raise_for_status()
            body = response.json()
            models = body.get("models", []) if isinstance(body, dict) else []
            return [model for model in models if isinstance(model, dict)]
        except (httpx.HTTPError, ValueError) as exc:
            raise TypeSafeError(f"Unable to list TypeSafe models: {redact(str(exc))}") from None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> TypeSafeProvider:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
