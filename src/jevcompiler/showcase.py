"""Run a committed replay bundle through evaluation, freeze, and verification."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from jevcompiler.baseline import BaselineEvaluator
from jevcompiler.dataset.models import (
    CaseProvenance,
    DatasetBundle,
    DatasetCase,
    DatasetManifest,
    LabelMetadata,
)
from jevcompiler.freeze import (
    FrozenManifest,
    freeze_optimization,
    frozen_artifact_id,
    verify_artifact,
)
from jevcompiler.optimizer.failures import build_failure_corpus
from jevcompiler.optimizer.models import (
    CandidateRecord,
    HeldOutEvaluation,
    OptimizationResult,
)
from jevcompiler.optimizer.mutations import program_id
from jevcompiler.optimizer.search import candidate_metrics
from jevcompiler.paths import artifact_directory
from jevcompiler.providers.base import SystemOneResult
from jevcompiler.providers.fake import RecordedSystemOneProvider
from jevcompiler.runs import content_digest
from jevcompiler.specs import load_program, load_task


class ShowcaseError(RuntimeError):
    """A replay bundle is incomplete, inconsistent, or produces the wrong decision."""


class ShowcaseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    expected_action: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recorded_at must include a timezone")
        return value


class ShowcaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    expected_action: str
    case_id: str
    candidate_id: str
    artifact_path: str
    artifact_files: int = Field(ge=1)
    live_calls: Literal[0] = 0
    verified: Literal[True] = True


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShowcaseError(f"unable to read {path.name}: {exc}") from None


def _load_answers(path: Path) -> list[SystemOneResult]:
    raw = _read_json(path)
    payloads = raw if isinstance(raw, list) else [raw]
    if not payloads or any(not isinstance(payload, dict) for payload in payloads):
        raise ShowcaseError(
            "answers.json must contain an object or a non-empty list of objects"
        )
    try:
        responses = [SystemOneResult.from_api(payload) for payload in payloads]
    except (TypeError, ValidationError) as exc:
        raise ShowcaseError(f"invalid recorded answers: {exc}") from None
    return responses


def _showcase_case(
    *,
    task_name: str,
    state: dict[str, Any],
    spec: ShowcaseSpec,
    requested_model: str,
    actual_model: str,
) -> DatasetCase:
    case_digest = content_digest(
        {
            "task_name": task_name,
            "state": state,
            "expected_action": spec.expected_action,
        }
    )
    return DatasetCase(
        id=f"case_{case_digest[:16]}",
        state=state,
        expected_action=spec.expected_action,
        bucket="user",
        summary=spec.summary,
        provenance=CaseProvenance(
            source="user",
            role="showcase_replay",
            provider="recorded",
            requested_model=requested_model,
            actual_model=actual_model,
            generated_at=spec.recorded_at,
            seed=0,
        ),
        label=LabelMetadata(
            provider="recorded",
            requested_model=requested_model,
            actual_model=actual_model,
            labeled_at=spec.recorded_at,
            confidence=1,
            important_factors=["committed replay expectation"],
        ),
    )


async def run_showcase(
    source: Path,
    *,
    output: Path | None = None,
) -> tuple[ShowcaseResult, FrozenManifest]:
    """Replay one committed example without network access and freeze verified evidence."""
    task = load_task(source / "task.yaml")
    program = load_program(source / "program.yaml")
    try:
        spec = ShowcaseSpec.model_validate(_read_json(source / "showcase.json"))
    except ValidationError as exc:
        raise ShowcaseError(f"invalid showcase.json: {exc}") from None

    state = _read_json(source / "state.json")
    if not isinstance(state, dict):
        raise ShowcaseError("state.json must contain a JSON object")
    responses = _load_answers(source / "answers.json")

    if task.name != program.name:
        raise ShowcaseError("task and program names do not match")
    if task.actions != program.actions:
        raise ShowcaseError("task and program actions do not match")
    if spec.expected_action not in task.actions:
        raise ShowcaseError(
            f"expected action {spec.expected_action!r} is not declared by the task"
        )

    actual_models = ",".join(sorted({response.model for response in responses}))
    case = _showcase_case(
        task_name=task.name,
        state=state,
        spec=spec,
        requested_model=program.jev_model,
        actual_model=actual_models,
    )
    dataset_digest = content_digest([case.model_dump(mode="json")])
    dataset = DatasetBundle(
        manifest=DatasetManifest(
            task_name=task.name,
            seed=0,
            counts={"train": 0, "dev": 0, "test": 1},
            bucket_counts={"user": 1},
            corpus_hash=dataset_digest,
        ),
        train=[],
        dev=[],
        test=[case],
    )

    report = await BaselineEvaluator(RecordedSystemOneProvider(responses)).evaluate(
        program, [case]
    )
    replay = report.cases[0]
    if replay.error is not None:
        raise ShowcaseError(f"recorded replay failed: {replay.error}")
    if replay.predicted_action != spec.expected_action:
        raise ShowcaseError(
            "recorded replay action mismatch: "
            f"expected {spec.expected_action!r}, got {replay.predicted_action!r}"
        )

    identifier = program_id(program)
    metrics = candidate_metrics(program, report, [case])
    candidate = CandidateRecord(
        candidate_id=identifier,
        generation=0,
        mutation_type="replay",
        hypothesis="Verify the committed program against recorded evidence.",
        semantic_diff="offline replay; no program mutation",
        status="selected",
        program=program,
        metrics=metrics,
        evaluation=report,
    )
    failures = build_failure_corpus(report, [case])
    held_out = HeldOutEvaluation(
        digest=dataset_digest,
        baseline_candidate_id=identifier,
        selected_candidate_id=identifier,
        baseline_metrics=metrics,
        selected_metrics=metrics,
        baseline_evaluation=report,
        selected_evaluation=report,
    )
    optimization = OptimizationResult(
        baseline_candidate_id=identifier,
        selected_candidate_id=identifier,
        pareto_frontier=[identifier],
        candidates=[candidate],
        baseline_failures=failures,
        selected_failures=failures,
        cache_hits=0,
        cache_misses=0,
        live_calls=0,
        selection_digest=dataset_digest,
        held_out=held_out,
    )

    destination = output or (
        artifact_directory(task.name, "showcase") / frozen_artifact_id(optimization)
    )
    manifest = freeze_optimization(optimization, dataset, destination)
    verified = verify_artifact(destination)
    if verified != manifest:
        raise ShowcaseError("frozen artifact verification returned inconsistent metadata")

    return (
        ShowcaseResult(
            action=replay.predicted_action,
            expected_action=spec.expected_action,
            case_id=case.id,
            candidate_id=identifier,
            artifact_path=destination.as_posix(),
            artifact_files=len(manifest.files),
        ),
        manifest,
    )
