from datetime import UTC, datetime

import pytest

from jevcompiler.baseline.models import CaseEvaluation, EvaluationReport
from jevcompiler.dataset.models import DatasetBundle, DatasetManifest
from jevcompiler.freeze import ArtifactError, freeze_optimization, verify_artifact
from jevcompiler.optimizer.models import (
    CandidateMetrics,
    CandidateRecord,
    FailureCorpus,
    OptimizationResult,
)
from jevcompiler.optimizer.mutations import program_id
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
    )
    dataset = DatasetBundle(
        manifest=DatasetManifest(
            task_name="frozen-router",
            seed=1,
            counts={"train": 0, "dev": 0, "test": 0},
            bucket_counts={},
            corpus_hash="a" * 64,
        ),
        train=[],
        dev=[],
        test=[],
    )
    return result, dataset


def test_frozen_artifact_is_complete_and_verifiable(tmp_path) -> None:
    result, dataset = _result()
    root = tmp_path / "frozen"

    manifest = freeze_optimization(result, dataset, root)

    assert manifest.created_at <= datetime.now(UTC)
    assert verify_artifact(root) == manifest
    assert (root / "runtime.py").exists()
    report = (root / "report.html").read_text(encoding="utf-8")
    assert "frozen-router optimization report" in report
    assert "Candidate lineage" in report


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
