from __future__ import annotations

from typing import Any

from jevcompiler.providers.base import SystemOneResult
from jevcompiler.specs.program import Question


class RecordedSystemOneProvider:
    """Offline provider for tests, examples, and deterministic replay."""

    def __init__(self, responses: list[SystemOneResult]) -> None:
        if not responses:
            raise ValueError("at least one recorded response is required")
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def evaluate(
        self,
        state: Any,
        questions: dict[str, Question],
        *,
        model: str,
    ) -> SystemOneResult:
        self.calls.append({"state": state, "questions": questions, "model": model})
        if not self._responses:
            raise RuntimeError("recorded System One responses are exhausted")
        return self._responses.pop(0)

