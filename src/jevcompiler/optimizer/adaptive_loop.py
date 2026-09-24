"""One bounded adaptive recompile-and-search round."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from jevcompiler.baseline import BaselineArtifact, BaselineCompiler
from jevcompiler.dataset.models import DatasetBundle
from jevcompiler.optimizer.adaptive import AdaptiveDatasetBuilder
from jevcompiler.optimizer.models import FailureCorpus, OptimizationResult
from jevcompiler.optimizer.mutations import MutationCandidate
from jevcompiler.optimizer.search import Optimizer
from jevcompiler.providers.teacher import TeacherProvider
from jevcompiler.specs.task import TaskSpec


@dataclass(frozen=True, slots=True)
class AdaptiveOptimizationRound:
    """Outputs and stop evidence from a single adaptive round."""

    adapted: bool
    stop_reason: Literal["completed", "no_training_failures", "candidate_budget"]
    source_candidate_id: str
    source_failures: FailureCorpus
    added_case_ids: tuple[str, ...]
    dataset: DatasetBundle
    baseline: BaselineArtifact
    result: OptimizationResult


def _candidate_count(result: OptimizationResult) -> int:
    if result.search is not None:
        return result.search.evaluated_candidates
    return len(result.candidates)


async def run_adaptive_round(
    *,
    task: TaskSpec,
    dataset: DatasetBundle,
    baseline: BaselineArtifact,
    initial_result: OptimizationResult,
    optimizer: Optimizer,
    teacher: TeacherProvider,
    thresholds: Sequence[float],
    adaptive_cases: int,
    seed: int,
    max_candidates: int | None,
    mutations: Sequence[MutationCandidate] = (),
) -> AdaptiveOptimizationRound:
    """Recompile from targeted train evidence and reselect on the untouched dev split."""
    by_id = {candidate.candidate_id: candidate for candidate in initial_result.candidates}
    selected = by_id[initial_result.selected_candidate_id]
    candidates_used = _candidate_count(initial_result)
    remaining_candidates = None if max_candidates is None else max_candidates - candidates_used
    if remaining_candidates is not None and remaining_candidates < 1:
        return AdaptiveOptimizationRound(
            adapted=False,
            stop_reason="candidate_budget",
            source_candidate_id=selected.candidate_id,
            source_failures=FailureCorpus(
                total_evaluated=0,
                total_failures=0,
                cases=[],
                clusters=[],
            ),
            added_case_ids=(),
            dataset=dataset,
            baseline=baseline,
            result=initial_result,
        )

    failures = await optimizer.evaluate_failures(selected.program, dataset.train)
    if failures.total_failures == 0:
        return AdaptiveOptimizationRound(
            adapted=False,
            stop_reason="no_training_failures",
            source_candidate_id=selected.candidate_id,
            source_failures=failures,
            added_case_ids=(),
            dataset=dataset,
            baseline=baseline,
            result=initial_result,
        )

    adaptation = await AdaptiveDatasetBuilder(teacher).extend(
        task,
        dataset,
        failures,
        count=adaptive_cases,
        seed=seed,
    )
    adaptive_baseline = await BaselineCompiler(teacher).compile(task, adaptation.bundle)
    result = await optimizer.optimize(
        adaptive_baseline.program,
        adaptation.bundle.dev,
        thresholds=thresholds,
        mutations=mutations,
        max_candidates=remaining_candidates,
    )
    result = await optimizer.evaluate_held_out(result, adaptation.bundle.test)
    return AdaptiveOptimizationRound(
        adapted=True,
        stop_reason="completed",
        source_candidate_id=selected.candidate_id,
        source_failures=failures,
        added_case_ids=tuple(adaptation.added_case_ids),
        dataset=adaptation.bundle,
        baseline=adaptive_baseline,
        result=result,
    )
