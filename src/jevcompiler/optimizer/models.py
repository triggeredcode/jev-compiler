from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from jevcompiler.baseline.models import EvaluationReport
from jevcompiler.dataset.models import CaseBucket, CaseProvenance, LabelMetadata
from jevcompiler.runtime.execution import TraceEvent
from jevcompiler.specs.program import DecisionProgram


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FailureCase(StrictModel):
    case_id: str
    state: dict[str, Any]
    bucket: CaseBucket
    expected_action: str
    predicted_action: str | None
    error: str | None = None
    trace: list[TraceEvent] = Field(default_factory=list)
    source_provenance: CaseProvenance
    label_provenance: LabelMetadata


class FailureCluster(StrictModel):
    key: str
    description: str
    case_ids: list[str] = Field(min_length=1)


class FailureCorpus(StrictModel):
    total_evaluated: int = Field(ge=0)
    total_failures: int = Field(ge=0)
    cases: list[FailureCase]
    clusters: list[FailureCluster]


class CandidateMetrics(StrictModel):
    accuracy: float = Field(ge=0, le=1)
    macro_f1: float = Field(ge=0, le=1)
    jev_calls: int = Field(ge=0)
    question_count: int = Field(ge=0)
    question_tokens: int = Field(ge=0)
    graph_complexity: int = Field(ge=0)


class CandidateRecord(StrictModel):
    candidate_id: str = Field(pattern=r"^candidate_[a-f0-9]{16}$")
    parent_id: str | None = None
    generation: int = Field(ge=0)
    mutation_type: str
    hypothesis: str
    semantic_diff: str
    status: Literal["baseline", "frontier", "selected", "rejected", "invalid"]
    rejection_reason: str | None = None
    program: DecisionProgram
    metrics: CandidateMetrics | None = None
    evaluation: EvaluationReport | None = None


class HeldOutEvaluation(StrictModel):
    split: Literal["test"] = "test"
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    baseline_candidate_id: str
    selected_candidate_id: str
    baseline_metrics: CandidateMetrics
    selected_metrics: CandidateMetrics
    baseline_evaluation: EvaluationReport
    selected_evaluation: EvaluationReport


class OptimizationResult(StrictModel):
    baseline_candidate_id: str
    selected_candidate_id: str
    pareto_frontier: list[str]
    candidates: list[CandidateRecord]
    baseline_failures: FailureCorpus
    selected_failures: FailureCorpus
    cache_hits: int = Field(ge=0)
    cache_misses: int = Field(ge=0)
    live_calls: int = Field(ge=0)
    selection_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    held_out: HeldOutEvaluation | None = None
