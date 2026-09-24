"""Deterministic, inspectable run metadata."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class RunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    command: str
    created_at: datetime
    input_digest: str
    compiler_version: str


def content_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def create_run_metadata(command: str, inputs: Any, compiler_version: str) -> RunMetadata:
    created_at = datetime.now(UTC)
    digest = content_digest(inputs)
    stamp = created_at.strftime("%Y%m%dT%H%M%S%fZ")
    return RunMetadata(
        run_id=f"{stamp}-{digest[:10]}",
        command=command,
        created_at=created_at,
        input_digest=digest,
        compiler_version=compiler_version,
    )


def write_run_metadata(root: Path, metadata: RunMetadata) -> Path:
    run_dir = root / "runs" / metadata.run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    path = run_dir / "metadata.json"
    path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    return path

