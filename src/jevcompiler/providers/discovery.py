from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

import httpx

ProviderKind = Literal["ollama", "lmstudio", "openrouter-free", "openrouter-paid"]


@dataclass(frozen=True, slots=True)
class ProviderAvailability:
    provider: ProviderKind
    available: bool
    endpoint: str | None = None
    models: tuple[str, ...] = ()
    reason: str | None = None


async def _probe_models(
    client: httpx.AsyncClient, provider: ProviderKind, url: str
) -> ProviderAvailability:
    try:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
        raw_models = payload.get("models", []) if isinstance(payload, dict) else []
        models = tuple(
            str(item.get("name") or item.get("id"))
            for item in raw_models
            if isinstance(item, dict) and (item.get("name") or item.get("id"))
        )
        return ProviderAvailability(provider, True, str(response.request.url), models)
    except (httpx.HTTPError, ValueError) as exc:
        return ProviderAvailability(provider, False, url, reason=type(exc).__name__)


async def discover_teacher_providers(
    *, client: httpx.AsyncClient | None = None
) -> list[ProviderAvailability]:
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=0.8)
    ollama_root = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    lmstudio_root = os.getenv("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
    try:
        ollama = await _probe_models(active_client, "ollama", f"{ollama_root}/api/tags")
        lmstudio = await _probe_models(active_client, "lmstudio", f"{lmstudio_root}/models")
    finally:
        if owns_client:
            await active_client.aclose()
    has_openrouter = bool(os.getenv("OPENROUTER_API_KEY"))
    return [
        ollama,
        lmstudio,
        ProviderAvailability(
            "openrouter-free",
            has_openrouter,
            "https://openrouter.ai/api/v1",
            ("openrouter/free",) if has_openrouter else (),
            None if has_openrouter else "OPENROUTER_API_KEY is not configured",
        ),
        ProviderAvailability(
            "openrouter-paid",
            has_openrouter,
            "https://openrouter.ai/api/v1",
            reason=None if has_openrouter else "OPENROUTER_API_KEY is not configured",
        ),
    ]


def select_teacher(
    availability: list[ProviderAvailability],
    *,
    allow_paid: bool = False,
    paid_model: str | None = None,
) -> tuple[ProviderKind, str | None]:
    by_name = {item.provider: item for item in availability}
    for provider in ("ollama", "lmstudio"):
        item = by_name.get(provider)
        if item and item.available:
            return provider, item.models[0] if item.models else None
    free = by_name.get("openrouter-free")
    if free and free.available:
        return "openrouter-free", "openrouter/free"
    paid = by_name.get("openrouter-paid")
    if allow_paid and paid_model and paid and paid.available:
        return "openrouter-paid", paid_model
    raise RuntimeError(
        "No local or free teacher is available. Paid fallback requires --allow-paid and a model."
    )

