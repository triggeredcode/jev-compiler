from jevcompiler.baseline.models import CaseEvaluation, EvaluationReport
from jevcompiler.dataset.models import DatasetCase
from jevcompiler.optimizer.stability import counterfactual_stability


def _case(case_id: str, expected: str, parent_id: str | None = None) -> DatasetCase:
    return DatasetCase.model_construct(
        id=case_id,
        expected_action=expected,
        parent_id=parent_id,
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
