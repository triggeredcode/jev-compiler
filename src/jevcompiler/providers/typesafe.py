from __future__ import annotations

import os
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
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("TYPESAFE_API_KEY")
        if not self._api_key:
            raise TypeSafeError("TYPESAFE_API_KEY is not configured")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

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
            response = await self._client.post(
                "/v1/systemone", headers=self._headers, json=payload
            )
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
            response = await self._client.get("/v1/models", headers=self._headers)
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

