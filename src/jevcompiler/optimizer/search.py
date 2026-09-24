"""Deterministic candidate evaluation, threshold search, and Pareto selection."""

from __future__ import annotations

from collections.abc import Sequence

from jevcompiler.baseline import BaselineEvaluator
from jevcompiler.baseline.models import EvaluationReport
from jevcompiler.dataset.models import DatasetCase
from jevcompiler.optimizer.failures import build_failure_corpus
from jevcompiler.optimizer.models import (
    CandidateMetrics,
    CandidateRecord,
    HeldOutEvaluation,
    OptimizationResult,
    SearchSummary,
)
from jevcompiler.optimizer.mutations import (
    MutationCandidate,
    confidence_dimensions,
    program_id,
    set_confidence_threshold,
)
from jevcompiler.optimizer.stability import counterfactual_stability
from jevcompiler.providers.base import SystemOneProvider
from jevcompiler.providers.cache import CacheMissError
from jevcompiler.runs import content_digest
from jevcompiler.specs.program import BranchNode, DecisionProgram, JevNode


def _question_tokens(program: DecisionProgram) -> int:
    text: list[str] = []
    for stage in program.stages:
        if not isinstance(stage, JevNode):
            continue
        for question in stage.questions.values():
            text.append(question.instructions)
            criteria = question.criteria
            if isinstance(criteria, dict):
                text.extend(f"{key} {value}" for key, value in criteria.items())
            elif isinstance(criteria, list):
                text.extend(criteria)
            elif criteria:
                text.append(criteria)
    return len(" ".join(text).split())


def candidate_metrics(
    program: DecisionProgram,
    report: EvaluationReport,
    cases: Sequence[DatasetCase] = (),
) -> CandidateMetrics:
    macro_f1 = (
        sum(metric.f1 for metric in report.per_action.values()) / len(report.per_action)
        if report.per_action
        else 0.0
    )
    jev_calls = sum(event.stage_type == "jev" for case in report.cases for event in case.trace)
    question_count = sum(
        len(stage.questions) for stage in program.stages if isinstance(stage, JevNode)
    )
    rule_count = sum(len(stage.rules) for stage in program.stages if isinstance(stage, BranchNode))
    stability, pairs = counterfactual_stability(report, cases)
    return CandidateMetrics(
        accuracy=report.accuracy,
        macro_f1=macro_f1,
        counterfactual_stability=stability,
        counterfactual_pairs=pairs,
        jev_calls=jev_calls,
        question_count=question_count,
        question_tokens=_question_tokens(program),
        graph_complexity=len(program.stages) + question_count + rule_count,
    )


def _quality_key(
    record: CandidateRecord,
) -> tuple[float, float, float, int, int, int, int, str]:
    assert record.metrics is not None
    return (
        record.metrics.accuracy,
        record.metrics.macro_f1,
        record.metrics.counterfactual_stability or 0.0,
        -record.metrics.jev_calls,
        -record.metrics.question_tokens,
        -record.metrics.graph_complexity,
        -record.generation,
        record.candidate_id,
    )


def _dominates(left: CandidateMetrics, right: CandidateMetrics) -> bool:
    comparisons = (
        left.accuracy >= right.accuracy,
        left.macro_f1 >= right.macro_f1,
        (left.counterfactual_stability or 0.0) >= (right.counterfactual_stability or 0.0),
        left.jev_calls <= right.jev_calls,
        left.question_tokens <= right.question_tokens,
        left.graph_complexity <= right.graph_complexity,
    )
    strict = (
        left.accuracy > right.accuracy
        or left.macro_f1 > right.macro_f1
        or (left.counterfactual_stability or 0.0) > (right.counterfactual_stability or 0.0)
        or left.jev_calls < right.jev_calls
        or left.question_tokens < right.question_tokens
        or left.graph_complexity < right.graph_complexity
    )
    return all(comparisons) and strict


def pareto_frontier(records: Sequence[CandidateRecord]) -> list[str]:
    measured = [record for record in records if record.metrics is not None]
    return sorted(
        record.candidate_id
        for record in measured
        if not any(
            other.candidate_id != record.candidate_id
            and other.metrics is not None
            and _dominates(other.metrics, record.metrics)
            for other in measured
        )
    )


class Optimizer:
    def __init__(self, provider: SystemOneProvider, *, concurrency: int = 10) -> None:
        self.provider = provider
        self.evaluator = BaselineEvaluator(
            provider,
            concurrency=concurrency,
            fatal_errors=(CacheMissError,),
        )

    async def optimize(
        self,
        baseline: DecisionProgram,
        cases: list[DatasetCase],
        *,
        thresholds: Sequence[float] = (0.5, 0.6, 0.7, 0.8, 0.9),
        mutations: Sequence[MutationCandidate] = (),
        max_candidates: int | None = None,
    ) -> OptimizationResult:
        if max_candidates is not None and max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        baseline_record = await self._evaluate(
            baseline,
            cases=cases,
            parent_id=None,
            generation=0,
            mutation_type="baseline",
            hypothesis="Measure the unmodified baseline on the selection split.",
            semantic_diff="no change",
            status="baseline",
        )
        records = [baseline_record]
        seen = {baseline_record.candidate_id}
        current = baseline_record
        budget_exhausted = False

        for dimension in confidence_dimensions(baseline):
            local: list[CandidateRecord] = []
            for threshold in sorted(set(thresholds)):
                mutation = set_confidence_threshold(current.program, dimension, threshold)
                identifier = program_id(mutation.program)
                if identifier in seen:
                    continue
                if max_candidates is not None and len(records) >= max_candidates:
                    budget_exhausted = True
                    break
                seen.add(identifier)
                record = await self._evaluate(
                    mutation.program,
                    cases=cases,
                    parent_id=current.candidate_id,
                    generation=current.generation + 1,
                    mutation_type=mutation.mutation_type,
                    hypothesis=mutation.hypothesis,
                    semantic_diff=mutation.semantic_diff,
                    status="rejected",
                )
                records.append(record)
                local.append(record)
            if local:
                best = max([current, *local], key=_quality_key)
                if _quality_key(best) > _quality_key(current):
                    current = best
            if budget_exhausted:
                break

        if not budget_exhausted:
            for mutation in mutations:
                identifier = program_id(mutation.program)
                if identifier in seen:
                    continue
                if max_candidates is not None and len(records) >= max_candidates:
                    budget_exhausted = True
                    break
                seen.add(identifier)
                records.append(
                    await self._evaluate(
                        mutation.program,
                        cases=cases,
                        parent_id=mutation.parent_id or baseline_record.candidate_id,
                        generation=1,
                        mutation_type=mutation.mutation_type,
                        hypothesis=mutation.hypothesis,
                        semantic_diff=mutation.semantic_diff,
                        status="rejected",
                    )
                )

        frontier = pareto_frontier(records)
        eligible = [record for record in records if record.candidate_id in frontier]
        selected = max(eligible, key=_quality_key)
        finalized: list[CandidateRecord] = []
        for record in records:
            if record.candidate_id == selected.candidate_id:
                status = "selected"
                reason = None
            elif record.candidate_id in frontier:
                status = "frontier"
                reason = None
            else:
                status = "rejected"
                reason = "dominated on the selection split"
            finalized.append(
                record.model_copy(update={"status": status, "rejection_reason": reason})
            )

        stats = getattr(self.provider, "stats", None)
        return OptimizationResult(
            baseline_candidate_id=baseline_record.candidate_id,
            selected_candidate_id=selected.candidate_id,
            pareto_frontier=frontier,
            candidates=finalized,
            baseline_failures=build_failure_corpus(
                baseline_record.evaluation,
                cases,  # type: ignore[arg-type]
            ),
            selected_failures=build_failure_corpus(
                selected.evaluation,
                cases,  # type: ignore[arg-type]
            ),
            cache_hits=stats.hits if stats else 0,
            cache_misses=stats.misses if stats else 0,
            live_calls=stats.live_calls if stats else 0,
            selection_digest=content_digest([case.model_dump(mode="json") for case in cases]),
            search=SearchSummary(
                candidate_budget=max_candidates,
                evaluated_candidates=len(records),
                stop_reason=("candidate_budget" if budget_exhausted else "search_exhausted"),
            ),
        )

    async def evaluate_held_out(
        self,
        result: OptimizationResult,
        cases: list[DatasetCase],
    ) -> OptimizationResult:
        """Measure the frozen selection on untouched cases without reselecting it."""
        if not cases:
            return result.model_copy(update={"held_out": None})

        by_id = {candidate.candidate_id: candidate for candidate in result.candidates}
        baseline = by_id[result.baseline_candidate_id]
        selected = by_id[result.selected_candidate_id]
        baseline_report = await self.evaluator.evaluate(baseline.program, cases=cases)
        if baseline.candidate_id == selected.candidate_id:
            selected_report = baseline_report
        else:
            selected_report = await self.evaluator.evaluate(selected.program, cases=cases)

        stats = getattr(self.provider, "stats", None)
        held_out = HeldOutEvaluation(
            digest=content_digest([case.model_dump(mode="json") for case in cases]),
            baseline_candidate_id=baseline.candidate_id,
            selected_candidate_id=selected.candidate_id,
            baseline_metrics=candidate_metrics(baseline.program, baseline_report, cases),
            selected_metrics=candidate_metrics(selected.program, selected_report, cases),
            baseline_evaluation=baseline_report,
            selected_evaluation=selected_report,
        )
        return result.model_copy(
            update={
                "held_out": held_out,
                "cache_hits": stats.hits if stats else result.cache_hits,
                "cache_misses": stats.misses if stats else result.cache_misses,
                "live_calls": stats.live_calls if stats else result.live_calls,
            }
        )

    async def _evaluate(
        self,
        program: DecisionProgram,
        *,
        cases: list[DatasetCase],
        parent_id: str | None,
        generation: int,
        mutation_type: str,
        hypothesis: str,
        semantic_diff: str,
        status: str,
    ) -> CandidateRecord:
        report = await self.evaluator.evaluate(program, cases=cases)
        return CandidateRecord(
            candidate_id=program_id(program),
            parent_id=parent_id,
            generation=generation,
            mutation_type=mutation_type,
            hypothesis=hypothesis,
            semantic_diff=semantic_diff,
            status=status,
            program=program,
            metrics=candidate_metrics(program, report, cases),
            evaluation=report,
        )
