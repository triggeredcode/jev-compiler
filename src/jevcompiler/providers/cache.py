"""Content-addressed recording and replay for Jev provider responses."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from jevcompiler.providers.base import SystemOneProvider, SystemOneResult
from jevcompiler.specs.program import Question


class CacheError(RuntimeError):
    """The Jev response cache could not serve a request safely."""


class CacheMissError(CacheError):
    """Replay-only mode encountered an unrecorded request."""


class CacheMode(StrEnum):
    read_write = "read_write"
    replay_only = "replay_only"
    refresh = "refresh"


@dataclass(slots=True)
class CacheStats:
    hits: int = 0
    misses: int = 0
    live_calls: int = 0


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    except (TypeError, ValueError) as exc:
        raise CacheError(f"cache request is not JSON-serializable: {exc}") from None


def cache_request(model: str, state: Any, questions: dict[str, Question]) -> dict[str, Any]:
    return {
        "model": model,
        "state": state,
        "questions": {
            key: question.model_dump(mode="json", by_alias=True, exclude_none=True)
            for key, question in sorted(questions.items())
        },
    }


def cache_key(model: str, state: Any, questions: dict[str, Question]) -> str:
    request = cache_request(model, state, questions)
    return hashlib.sha256(_canonical_json(request).encode()).hexdigest()


class JevCache:
    """Small SQLite store whose first response for a request remains canonical."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._connection = sqlite3.connect(path)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jev_responses (
                cache_key TEXT PRIMARY KEY,
                request_json TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._connection.commit()

    def get(self, key: str) -> SystemOneResult | None:
        row = self._connection.execute(
            "SELECT response_json FROM jev_responses WHERE cache_key = ?", (key,)
        ).fetchone()
        return SystemOneResult.model_validate_json(row[0]) if row else None

    def put(self, key: str, request: dict[str, Any], result: SystemOneResult) -> None:
        self._connection.execute(
            """
            INSERT OR IGNORE INTO jev_responses(cache_key, request_json, response_json)
            VALUES (?, ?, ?)
            """,
            (key, _canonical_json(request), result.model_dump_json()),
        )
        self._connection.commit()

    def count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) FROM jev_responses").fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> JevCache:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class CachingSystemOneProvider:
    """Coalesce identical requests and serve later evaluations from a recording."""

    def __init__(
        self,
        cache: JevCache,
        upstream: SystemOneProvider | None = None,
        *,
        mode: CacheMode = CacheMode.read_write,
    ) -> None:
        if mode is not CacheMode.replay_only and upstream is None:
            raise ValueError("an upstream provider is required outside replay-only mode")
        self.cache = cache
        self.upstream = upstream
        self.mode = mode
        self.stats = CacheStats()
        self._locks: dict[str, asyncio.Lock] = {}

    async def evaluate(
        self,
        state: Any,
        questions: dict[str, Question],
        *,
        model: str,
    ) -> SystemOneResult:
        request = cache_request(model, state, questions)
        key = hashlib.sha256(_canonical_json(request).encode()).hexdigest()
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if self.mode is not CacheMode.refresh:
                cached = self.cache.get(key)
                if cached is not None:
                    self.stats.hits += 1
                    return cached

            self.stats.misses += 1
            if self.mode is CacheMode.replay_only or self.upstream is None:
                raise CacheMissError(f"no recorded Jev response for cache key {key}")

            self.stats.live_calls += 1
            result = await self.upstream.evaluate(state, questions, model=model)
            self.cache.put(key, request, result)
            return result
