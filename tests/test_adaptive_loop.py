import asyncio

from test_adaptive import _bundle, _task
from test_optimizer import ConfidenceProvider, _program

from jevcompiler.baseline import BaselineCompiler
from jevcompiler.dataset.builder import _case_id
from jevcompiler.optimizer import Optimizer, run_adaptive_round
from jevcompiler.providers.teacher import RecordedTeacherProvider


def test_adaptive_round_recompiles_and_preserves_held_out_splits() -> None:
    dataset = _bundle()
    dataset.train[0].state.update({"choice": "billing", "confidence": 0.4})
    dataset.dev[0].state.update({"choice": "technical", "confidence": 0.9})
    dataset.test[0].state.update({"choice": "manual_review", "confidence": 0.2})
    parent_id = dataset.train[0].id
    adaptive_state = {
        "body": "charged again after retry",
        "choice": "billing",
        "confidence": 0.95,
    }
    teacher = RecordedTeacherProvider(
        [
            {
                "question_id": "route",
                "instructions": "Route the ticket.",
                "criteria": {
                    "billing": "Payment issue",
                    "technical": "Product issue",
                    "manual_review": "Unclear issue",
                },
                "confidence_threshold": 0.7,
            },
            {
                "cases": [
                    {
                        "state": adaptive_state,
                        "summary": "near the failed billing case",
                        "parent_id": parent_id,
                    }
                ]
            },
            {
                "labels": [
                    {
                        "case_id": _case_id(adaptive_state),
                        "decision": "billing",
                        "confidence": 0.95,
                    }
                ]
            },
            {
                "question_id": "route",
                "instructions": "Route the ticket using the refined examples.",
                "criteria": {
                    "billing": "Payment issue",
                    "technical": "Product issue",
                    "manual_review": "Unclear issue",
                },
                "confidence_threshold": 0.7,
            },
        ]
    )

    async def exercise():
        baseline = await BaselineCompiler(teacher).compile(_task(), dataset)
        optimizer = Optimizer(ConfidenceProvider())
        initial = await optimizer.optimize(
            _program(),
            dataset.dev,
            thresholds=[0.7],
            max_candidates=2,
        )
        initial = await optimizer.evaluate_held_out(initial, dataset.test)
        adaptive = await run_adaptive_round(
            task=_task(),
            dataset=dataset,
            baseline=baseline,
            initial_result=initial,
            optimizer=optimizer,
            teacher=teacher,
            thresholds=[0.7],
            adaptive_cases=1,
            seed=19,
            max_candidates=3,
        )
        return initial, adaptive

    initial, adaptive = asyncio.run(exercise())

    assert adaptive.adapted is True
    assert adaptive.stop_reason == "completed"
    assert adaptive.dataset.dev == dataset.dev
    assert adaptive.dataset.test == dataset.test
    assert len(adaptive.dataset.train) == len(dataset.train) + 1
    assert adaptive.baseline.provenance.training_corpus_hash == (
        adaptive.dataset.manifest.corpus_hash
    )
    assert adaptive.result.held_out is not None
    assert adaptive.result.held_out.digest == initial.held_out.digest
    assert adaptive.result.search is not None
    assert adaptive.result.search.candidate_budget == 2


def test_adaptive_round_stops_before_teacher_calls_when_candidate_budget_is_spent() -> None:
    dataset = _bundle()
    dataset.train[0].state.update({"choice": "billing", "confidence": 0.4})
    dataset.dev[0].state.update({"choice": "technical", "confidence": 0.9})
    teacher = RecordedTeacherProvider(
        [
            {
                "question_id": "unused",
                "instructions": "Unused response.",
                "criteria": {
                    "billing": "Payment issue",
                    "technical": "Product issue",
                    "manual_review": "Unclear issue",
                },
            }
        ]
    )

    async def exercise():
        baseline = await BaselineCompiler(teacher).compile(_task(), dataset)
        optimizer = Optimizer(ConfidenceProvider())
        initial = await optimizer.optimize(
            _program(), dataset.dev, thresholds=[0.7], max_candidates=1
        )
        return await run_adaptive_round(
            task=_task(),
            dataset=dataset,
            baseline=baseline,
            initial_result=initial,
            optimizer=optimizer,
            teacher=teacher,
            thresholds=[0.7],
            adaptive_cases=1,
            seed=19,
            max_candidates=1,
        )

    adaptive = asyncio.run(exercise())

    assert adaptive.adapted is False
    assert adaptive.stop_reason == "candidate_budget"
    assert adaptive.source_failures.total_evaluated == 0
    assert len(teacher.calls) == 1
