from jevcompiler.baseline.models import CaseEvaluation, EvaluationReport
from jevcompiler.dataset.models import DatasetCase
from jevcompiler.optimizer.stability import counterfactual_stability, semantic_invariance


def _case(case_id: str, expected: str, parent_id: str | None = None) -> DatasetCase:
    return DatasetCase.model_construct(
        id=case_id,
        expected_action=expected,
        parent_id=parent_id,
        bucket="normal",
    )


def _report(*predictions: tuple[str, str | None]) -> EvaluationReport:
    cases = [
        CaseEvaluation(
            case_id=case_id,
            expected_action="unused",
            predicted_action=predicted,
            correct=False,
        )
        for case_id, predicted in predictions
    ]
    return EvaluationReport(
        total=len(cases),
        correct=0,
        accuracy=0,
        per_action={},
        confusion={},
        cases=cases,
    )


def test_counterfactual_stability_scores_expected_prediction_relationships() -> None:
    cases = [
        _case("parent", "billing"),
        _case("same", "billing", "parent"),
        _case("changed", "technical", "parent"),
        _case("missing", "technical", "parent"),
    ]
    report = _report(
        ("parent", "billing"),
        ("same", "billing"),
        ("changed", "manual_review"),
        ("missing", None),
    )

    score, pairs = counterfactual_stability(report, cases)

    assert pairs == 3
    assert score == 2 / 3


def test_counterfactual_stability_is_unavailable_without_complete_pairs() -> None:
    score, pairs = counterfactual_stability(
        _report(("orphan", "billing")),
        [_case("orphan", "billing", "outside-split")],
    )

    assert score is None
    assert pairs == 0


def test_semantic_invariance_scores_only_meaning_preserving_variations() -> None:
    cases = [
        _case("parent", "billing"),
        _case("same", "billing", "parent").model_copy(
            update={"bucket": "semantic_variation"}
        ),
        _case("drifted", "billing", "parent").model_copy(
            update={"bucket": "semantic_variation"}
        ),
        _case("missing", "billing", "parent").model_copy(
            update={"bucket": "semantic_variation"}
        ),
        _case("changed-label", "technical", "parent").model_copy(
            update={"bucket": "semantic_variation"}
        ),
        _case("ordinary-child", "billing", "parent"),
    ]
    report = _report(
        ("parent", "billing"),
        ("same", "billing"),
        ("drifted", "technical"),
        ("missing", None),
        ("changed-label", "technical"),
        ("ordinary-child", "billing"),
    )

    score, pairs = semantic_invariance(report, cases)

    assert pairs == 3
    assert score == 1 / 3


def test_semantic_invariance_is_unavailable_for_orphan_variations() -> None:
    variation = _case("orphan", "billing", "outside-split").model_copy(
        update={"bucket": "semantic_variation"}
    )

    score, pairs = semantic_invariance(_report(("orphan", "billing")), [variation])

    assert score is None
    assert pairs == 0
