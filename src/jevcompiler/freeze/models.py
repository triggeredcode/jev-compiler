from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FrozenManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    task_name: str
    created_at: datetime
    compiler_version: str
    selected_candidate_id: str
    program_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    jev_model: str
    actions: list[str]
    selection_metrics: dict[str, float | int]
    held_out_metrics: dict[str, float | int] | None = None
    files: dict[str, str]
