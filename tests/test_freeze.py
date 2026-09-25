from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from jevcompiler.baseline.models import CaseEvaluation, EvaluationReport
from jevcompiler.cli import app
from jevcompiler.dataset.models import (
    CaseProvenance,
    DatasetBundle,
    DatasetCase,
    DatasetManifest,
    LabelMetadata,
)
from jevcompiler.freeze import (
    ArtifactError,
    freeze_optimization,
    frozen_artifact_id,
    verify_artifact,
)
from jevcompiler.optimizer.models import (
    CandidateMetrics,
    CandidateRecord,
    FailureCorpus,
    HeldOutEvaluation,
    OptimizationResult,
)
from jevcompiler.optimizer.mutations import program_id
from jevcompiler.runs import content_digest
from jevcompiler.specs.program import DecisionProgram, ReturnNode


def _result() -> tuple[OptimizationResult, DatasetBundle]:
    program = DecisionProgram(
        name="frozen-router",
        actions=["accept", "review"],
        stages=[ReturnNode(id="done", type="return", value="accept")],
    )
    report = EvaluationReport(
        total=1,
        correct=1,
        accuracy=1,
        per_action={},
        confusion={"accept": {"accept": 1}},
        cases=[
            CaseEvaluation(
                case_id="case_1111111111111111",
                expected_action="accept",
                predicted_action="accept",
                correct=True,
            )
        ],
    )
    identifier = program_id(program)
    candidate = CandidateRecord(
        candidate_id=identifier,
        generation=0,
        mutation_type="baseline",
        hypothesis="Measure baseline.",
        semantic_diff="no change",
        status="selected",
        program=program,
        metrics=CandidateMetrics(
            accuracy=1,
            macro_f1=1,
            jev_calls=0,
            question_count=0,
            question_tokens=0,
            graph_complexity=1,
        ),
        evaluation=report,
    )
    empty_failures = FailureCorpus(
        total_evaluated=1,
        total_failures=0,
        cases=[],
        clusters=[],
    )
    now = datetime.now(UTC)
    test_case = DatasetCase(
        id="case_1111111111111111",
        state={},
        expected_action="accept",
        bucket="normal",
        summary="accept by default",
        provenance=CaseProvenance(
            source="teacher",
            role="normal_generator",
            provider="fake",
            requested_model="fake",
            actual_model="fake",
            generated_at=now,
            seed=1,
        ),
        label=LabelMetadata(
            provider="fake",
            requested_model="fake",
            actual_model="fake",
            labeled_at=now,
            confidence=1,
        ),
    )
    held_out = HeldOutEvaluation(
        digest=content_digest([test_case.model_dump(mode="json")]),
        baseline_candidate_id=identifier,
        selected_candidate_id=identifier,
        baseline_metrics=candidate.metrics,
        selected_metrics=candidate.metrics,
        baseline_evaluation=report,
        selected_evaluation=report,
    )
    result = OptimizationResult(
        baseline_candidate_id=identifier,
        selected_candidate_id=identifier,
        pareto_frontier=[identifier],
        candidates=[candidate],
        baseline_failures=empty_failures,
        selected_failures=empty_failures,
        cache_hits=1,
        cache_misses=0,
        live_calls=0,
        held_out=held_out,
    )
    dataset = DatasetBundle(
        manifest=DatasetManifest(
            task_name="frozen-router",
            seed=1,
            counts={"train": 0, "dev": 0, "test": 1},
            bucket_counts={"normal": 1},
            corpus_hash="a" * 64,
        ),
        train=[],
        dev=[],
        test=[test_case],
    )
    return result, dataset


def test_frozen_artifact_is_complete_and_verifiable(tmp_path) -> None:
    result, dataset = _result()
    root = tmp_path / "frozen"

    manifest = freeze_optimization(result, dataset, root)

    assert manifest.created_at <= datetime.now(UTC)
    assert verify_artifact(root) == manifest
    assert (root / "runtime.py").exists()
    assert (root / "runtime.ts").exists()
    assert (root / "program.json").exists()
    assert {"runtime.py", "runtime.ts", "program.yaml", "program.json"} <= set(manifest.files)
    assert (root / "held-out.json").exists()
    assert manifest.held_out_metrics is not None
    report = (root / "report.html").read_text(encoding="utf-8")
    assert "frozen-router optimization report" in report
    assert "Candidate lineage" in report
    assert "Baseline vs selected" in report
    assert "Held-out test" in report
    assert "Accuracy by generation" in report
    assert "Pareto trade-off" in report
    assert "CF stability" in report
    assert "Failure browser" in report


def test_verification_detects_tampering(tmp_path) -> None:
    result, dataset = _result()
    root = tmp_path / "frozen"
    freeze_optimization(result, dataset, root)
    (root / "program.yaml").write_text("tampered: true\n", encoding="utf-8")

    with pytest.raises(ArtifactError, match="hash mismatch"):
        verify_artifact(root)


def test_freeze_refuses_to_overwrite(tmp_path) -> None:
    result, dataset = _result()
    root = tmp_path / "frozen"
    root.mkdir()

    with pytest.raises(ArtifactError, match="refusing to overwrite"):
        freeze_optimization(result, dataset, root)


def test_freeze_rejects_mismatched_held_out_evidence(tmp_path) -> None:
    result, dataset = _result()
    assert result.held_out is not None
    result = result.model_copy(
        update={"held_out": result.held_out.model_copy(update={"digest": "b" * 64})}
    )

    with pytest.raises(ArtifactError, match="held-out evaluation digest"):
        freeze_optimization(result, dataset, tmp_path / "frozen")


def test_report_command_verifies_artifact_without_opening_browser(tmp_path) -> None:
    result, dataset = _result()
    root = tmp_path / "frozen"
    freeze_optimization(result, dataset, root)

    completed = CliRunner().invoke(app, ["report", str(root), "--no-open"])

    assert completed.exit_code == 0
    assert "report.html" in "".join(completed.output.splitlines())
    assert root.name in completed.output


def test_frozen_artifact_identity_includes_approval_evidence() -> None:
    result, _ = _result()
    original = frozen_artifact_id(result)
    assert result.held_out is not None
    changed = result.model_copy(
        update={"held_out": result.held_out.model_copy(update={"digest": "b" * 64})}
    )

    assert original.startswith(f"{result.selected_candidate_id}-")
    assert frozen_artifact_id(changed) != original
