from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from jevcompiler.specs.program import Question


class AnswerModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ChoiceAnswer(AnswerModel):
    type: Literal["choice"]
    choice: str
    probabilities: dict[str, float]
    confidence: float = Field(ge=0, le=1)


class ScoreAnswer(AnswerModel):
    type: Literal["score"]
    score: float
    probabilities: dict[str, float]
    confidence: float = Field(ge=0, le=1)
    legend: dict[str, str] = Field(default_factory=dict)


class NoulAnswer(AnswerModel):
    type: Literal["noul"]
    noul: float = Field(ge=0, le=1)


SystemOneAnswer = ChoiceAnswer | ScoreAnswer | NoulAnswer
_ANSWER_ADAPTER = TypeAdapter(SystemOneAnswer)


class SystemOneResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    answers: dict[str, SystemOneAnswer]
    usage: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> SystemOneResult:
        answers = {
            key: _ANSWER_ADAPTER.validate_python(value)
            for key, value in payload.get("answers", {}).items()
        }
        return cls(
            model=str(payload.get("model", "unknown")),
            answers=answers,
            usage=payload.get("usage") or {},
        )


class SystemOneProvider(Protocol):
    async def evaluate(
        self,
        state: Any,
        questions: dict[str, Question],
        *,
        model: str,
    ) -> SystemOneResult: ...

