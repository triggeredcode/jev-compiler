from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from jevcompiler.dataset.models import CaseBucket, CaseProvenance, LabelMetadata
from jevcompiler.runtime.execution import TraceEvent


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
