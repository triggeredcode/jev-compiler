from datetime import UTC, datetime

import pytest

from jevcompiler.baseline.models import CaseEvaluation, EvaluationReport
from jevcompiler.dataset.models import CaseProvenance, DatasetCase, LabelMetadata
from jevcompiler.optimizer.failures import FailureCorpusError, build_failure_corpus


def _case(case_id: str, expected: str) -> DatasetCase:
    now = datetime.now(UTC)
    return DatasetCase(
        id=case_id,
        state={"body": case_id},
        expected_action=expected,
        bucket="boundary",
        summary="boundary case",
        provenance=CaseProvenance(
            source="teacher",
            role="boundary_generator",
            provider="teacher",
            requested_model="requested",
            actual_model="actual",
            generated_at=now,
            seed=7,
        ),
        label=LabelMetadata(
            provider="teacher",
            requested_model="requested",
            actual_model="actual",
            labeled_at=now,
            confidence=0.8,
        ),
    )


def test_failure_corpus_preserves_evidence_and_clusters() -> None:
    case = _case("case_1111111111111111", "billing")
    report = EvaluationReport(
        total=1,
        correct=0,
        accuracy=0,
        per_action={},
        confusion={"billing": {"manual_review": 1}},
        cases=[
            CaseEvaluation(
                case_id=case.id,
                expected_action="billing",
                predicted_action="manual_review",
                correct=False,
            )
        ],
    )

    corpus = build_failure_corpus(report, [case])

    assert corpus.total_failures == 1
    assert corpus.clusters[0].key == "billing->manual_review"
    assert corpus.cases[0].label_provenance.actual_model == "actual"


def test_failure_corpus_rejects_unknown_case() -> None:
    report = EvaluationReport(
        total=1,
        correct=0,
        accuracy=0,
        per_action={},
        confusion={},
        cases=[
            CaseEvaluation(
                case_id="case_9999999999999999",
                expected_action="billing",
                predicted_action=None,
                correct=False,
            )
        ],
    )

    with pytest.raises(FailureCorpusError, match="unknown dataset case"):
        build_failure_corpus(report, [])
