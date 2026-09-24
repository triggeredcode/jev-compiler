"""Relational stability metrics for parent/counterfactual evidence pairs."""

from __future__ import annotations

from collections.abc import Sequence

from jevcompiler.baseline.models import EvaluationReport
from jevcompiler.dataset.models import DatasetCase


def counterfactual_stability(
    report: EvaluationReport,
    cases: Sequence[DatasetCase],
) -> tuple[float | None, int]:
    """Score whether predictions preserve each pair's expected change relationship."""
    evidence = {case.id: case for case in cases}
    evaluations = {case.case_id: case for case in report.cases}
    stable = 0
    pairs = 0

    for child in cases:
        if child.parent_id is None or child.parent_id not in evidence:
            continue
        parent = evidence[child.parent_id]
        parent_result = evaluations.get(parent.id)
        child_result = evaluations.get(child.id)
        pairs += 1
        if (
            parent_result is None
            or child_result is None
            or parent_result.predicted_action is None
            or child_result.predicted_action is None
        ):
            continue
        expected_changed = parent.expected_action != child.expected_action
        predicted_changed = parent_result.predicted_action != child_result.predicted_action
        stable += expected_changed == predicted_changed

    return ((stable / pairs) if pairs else None, pairs)
