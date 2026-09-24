"""Evaluate a DecisionProgram against labeled cases with complete traces."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from jevcompiler.baseline.models import (
    CaseEvaluation,
    ClassMetrics,
    EvaluationReport,
)
from jevcompiler.dataset.models import DatasetCase
from jevcompiler.providers.base import SystemOneProvider
from jevcompiler.runtime import ProgramRuntime
from jevcompiler.security import redact
from jevcompiler.specs.program import DecisionProgram


class BaselineEvaluator:
    def __init__(
        self,
        provider: SystemOneProvider,
        *,
        concurrency: int = 10,
        fatal_errors: tuple[type[Exception], ...] = (),
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        self.provider = provider
        self.concurrency = concurrency
        self.fatal_errors = fatal_errors

    async def evaluate(
        self, program: DecisionProgram, cases: list[DatasetCase]
    ) -> EvaluationReport:
        semaphore = asyncio.Semaphore(self.concurrency)

        async def run_case(case: DatasetCase) -> CaseEvaluation:
            async with semaphore:
                try:
                    result = await ProgramRuntime(self.provider).run(program, case.state)
                    return CaseEvaluation(
                        case_id=case.id,
                        expected_action=case.expected_action,
                        predicted_action=result.action,
                        correct=result.action == case.expected_action,
                        trace=result.trace,
                    )
                except self.fatal_errors:
                    raise
                except Exception as exc:  # Runtime/provider failures are evaluation evidence.
                    return CaseEvaluation(
                        case_id=case.id,
                        expected_action=case.expected_action,
                        predicted_action=None,
                        correct=False,
                        error=str(redact(str(exc))),
                    )

        results = list(await asyncio.gather(*(run_case(case) for case in cases)))
        return self._metrics(program.actions, results)

    @staticmethod
    def _metrics(actions: list[str], results: list[CaseEvaluation]) -> EvaluationReport:
        confusion: dict[str, dict[str, int]] = {
            action: defaultdict(int) for action in actions
        }
        for result in results:
            predicted = result.predicted_action or "__error__"
            confusion.setdefault(result.expected_action, defaultdict(int))[predicted] += 1

        per_action: dict[str, ClassMetrics] = {}
        for action in actions:
            support = sum(1 for result in results if result.expected_action == action)
            true_positive = sum(
                1
                for result in results
                if result.expected_action == action and result.predicted_action == action
            )
            false_positive = sum(
                1
                for result in results
                if result.expected_action != action and result.predicted_action == action
            )
            precision = (
                true_positive / (true_positive + false_positive)
                if true_positive + false_positive
                else 0.0
            )
            recall = true_positive / support if support else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            per_action[action] = ClassMetrics(
                support=support, precision=precision, recall=recall, f1=f1
            )

        correct = sum(result.correct for result in results)
        total = len(results)
        normalized_confusion = {
            expected: dict(sorted(predictions.items()))
            for expected, predictions in sorted(confusion.items())
        }
        return EvaluationReport(
            total=total,
            correct=correct,
            accuracy=correct / total if total else 0.0,
            per_action=per_action,
            confusion=normalized_confusion,
            cases=results,
        )
