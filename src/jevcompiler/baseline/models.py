from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from jevcompiler.runtime.execution import TraceEvent
from jevcompiler.specs.program import DecisionProgram


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BaselinePlan(StrictModel):
    question_id: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    instructions: str = Field(min_length=1)
    criteria: dict[str, str] = Field(min_length=2)
    confidence_threshold: float = Field(default=0.65, ge=0, le=1)


class BaselineProvenance(StrictModel):
    provider: str
    requested_model: str
    actual_model: str
    compiled_at: datetime
    training_corpus_hash: str


class BaselineArtifact(StrictModel):
    program: DecisionProgram
    plan: BaselinePlan
    provenance: BaselineProvenance


class CaseEvaluation(StrictModel):
    case_id: str
    expected_action: str
    predicted_action: str | None
    correct: bool
    trace: list[TraceEvent] = Field(default_factory=list)
    error: str | None = None


class ClassMetrics(StrictModel):
    support: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)


class EvaluationReport(StrictModel):
    total: int = Field(ge=0)
    correct: int = Field(ge=0)
    accuracy: float = Field(ge=0, le=1)
    per_action: dict[str, ClassMetrics]
    confusion: dict[str, dict[str, int]]
    cases: list[CaseEvaluation]

