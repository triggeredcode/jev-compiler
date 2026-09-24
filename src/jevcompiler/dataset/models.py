from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CaseBucket = Literal[
    "normal",
    "boundary",
    "counterfactual",
    "semantic_variation",
    "edge",
    "user",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioDraft(StrictModel):
    state: dict[str, Any]
    summary: str = Field(min_length=1)
    parent_id: str | None = None


class ScenarioBatch(StrictModel):
    cases: list[ScenarioDraft] = Field(min_length=1)


class LabelDraft(StrictModel):
    case_id: str
    decision: str
    confidence: float = Field(ge=0, le=1)
    important_factors: list[str] = Field(default_factory=list)


class LabelBatch(StrictModel):
    labels: list[LabelDraft] = Field(min_length=1)


class CaseProvenance(StrictModel):
    source: Literal["teacher", "user"]
    role: str
    provider: str
    requested_model: str
    actual_model: str
    generated_at: datetime
    seed: int


class LabelMetadata(StrictModel):
    provider: str
    requested_model: str
    actual_model: str
    labeled_at: datetime
    confidence: float = Field(ge=0, le=1)
    important_factors: list[str] = Field(default_factory=list)


class DatasetCase(StrictModel):
    id: str = Field(pattern=r"^case_[a-f0-9]{16}$")
    state: dict[str, Any]
    expected_action: str
    bucket: CaseBucket
    summary: str
    parent_id: str | None = None
    provenance: CaseProvenance
    label: LabelMetadata


class DatasetManifest(StrictModel):
    version: Literal[1] = 1
    task_name: str
    seed: int
    counts: dict[Literal["train", "dev", "test"], int]
    bucket_counts: dict[str, int]
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class DatasetBundle(StrictModel):
    manifest: DatasetManifest
    train: list[DatasetCase]
    dev: list[DatasetCase]
    test: list[DatasetCase]

    @property
    def all_cases(self) -> list[DatasetCase]:
        return [*self.train, *self.dev, *self.test]
