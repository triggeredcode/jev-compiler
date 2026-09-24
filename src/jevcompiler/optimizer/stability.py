"""Relational stability metrics for paired evaluation evidence."""

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


def semantic_invariance(
    report: EvaluationReport,
    cases: Sequence[DatasetCase],
) -> tuple[float | None, int]:
    """Score whether predictions remain equal across meaning-preserving variations."""
    evidence = {case.id: case for case in cases}
    evaluations = {case.case_id: case for case in report.cases}
    invariant = 0
    pairs = 0

    for variation in cases:
        if variation.bucket != "semantic_variation" or variation.parent_id not in evidence:
            continue
        parent = evidence[variation.parent_id]
        if parent.expected_action != variation.expected_action:
            continue
        parent_result = evaluations.get(parent.id)
        variation_result = evaluations.get(variation.id)
        pairs += 1
        if (
            parent_result is not None
            and variation_result is not None
            and parent_result.predicted_action is not None
            and variation_result.predicted_action is not None
            and parent_result.predicted_action == variation_result.predicted_action
        ):
            invariant += 1

    return ((invariant / pairs) if pairs else None, pairs)
