import asyncio

import pytest

from jevcompiler.providers.base import SystemOneResult
from jevcompiler.providers.cache import (
    CacheMissError,
    CacheMode,
    CachingSystemOneProvider,
    JevCache,
    LiveCallBudgetExceeded,
    cache_key,
)
from jevcompiler.specs.program import ChoiceQuestion


def _questions():
    return {
        "route": ChoiceQuestion(
            type="choice",
            instructions="Route the ticket",
            criteria={"billing": "Charges", "review": "Anything else"},
        )
    }


class CountingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(self, state, questions, *, model):
        self.calls += 1
        await asyncio.sleep(0)
        return SystemOneResult.from_api(
            {
                "model": model,
                "answers": {
                    "route": {
                        "type": "choice",
                        "choice": "billing",
                        "probabilities": {"billing": 0.9, "review": 0.1},
                        "confidence": 0.9,
                    }
                },
            }
        )


def test_cache_key_is_canonical() -> None:
    questions = _questions()
    assert cache_key("jev", {"b": 2, "a": 1}, questions) == cache_key(
        "jev", {"a": 1, "b": 2}, questions
    )


def test_cache_coalesces_live_calls_and_replays(tmp_path) -> None:
    async def exercise() -> tuple[int, int, int]:
        upstream = CountingProvider()
        with JevCache(tmp_path / "jev.sqlite3") as cache:
            provider = CachingSystemOneProvider(cache, upstream)
            results = await asyncio.gather(
                provider.evaluate({"body": "charged"}, _questions(), model="jev-test"),
                provider.evaluate({"body": "charged"}, _questions(), model="jev-test"),
            )
            assert results[0] == results[1]
            assert cache.count() == 1
            return upstream.calls, provider.stats.hits, provider.stats.live_calls

    calls, hits, live_calls = asyncio.run(exercise())
    assert (calls, hits, live_calls) == (1, 1, 1)


def test_replay_only_fails_closed_on_cache_miss(tmp_path) -> None:
    with JevCache(tmp_path / "jev.sqlite3") as cache:
        provider = CachingSystemOneProvider(cache, mode=CacheMode.replay_only)
        with pytest.raises(CacheMissError, match="no recorded Jev response"):
            asyncio.run(provider.evaluate({"body": "new"}, _questions(), model="jev-test"))


def test_live_call_budget_is_a_hard_concurrent_ceiling(tmp_path) -> None:
    async def exercise():
        upstream = CountingProvider()
        with JevCache(tmp_path / "jev.sqlite3") as cache:
            provider = CachingSystemOneProvider(
                cache,
                upstream,
                max_live_calls=2,
            )
            results = await asyncio.gather(
                *(
                    provider.evaluate(
                        {"body": f"ticket {index}"},
                        _questions(),
                        model="jev-test",
                    )
                    for index in range(3)
                ),
                return_exceptions=True,
            )
            return upstream.calls, provider.stats.live_calls, results

    calls, live_calls, results = asyncio.run(exercise())

    assert calls == 2
    assert live_calls == 2
    assert sum(isinstance(result, LiveCallBudgetExceeded) for result in results) == 1


def test_cached_answers_remain_available_after_budget_is_exhausted(tmp_path) -> None:
    async def exercise():
        upstream = CountingProvider()
        with JevCache(tmp_path / "jev.sqlite3") as cache:
            provider = CachingSystemOneProvider(
                cache,
                upstream,
                max_live_calls=1,
            )
            first = await provider.evaluate(
                {"body": "charged"}, _questions(), model="jev-test"
            )
            replay = await provider.evaluate(
                {"body": "charged"}, _questions(), model="jev-test"
            )
            return first, replay, upstream.calls, provider.stats

    first, replay, calls, stats = asyncio.run(exercise())

    assert first == replay
    assert calls == 1
    assert stats.live_calls == 1
    assert stats.hits == 1
