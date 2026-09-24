import asyncio
from datetime import UTC, datetime

import pytest

from jevcompiler.dataset.models import CaseProvenance, DatasetCase, LabelMetadata
from jevcompiler.optimizer import (
    Optimizer,
    add_choice_early_exit,
    confidence_dimensions,
    rewrite_choice_question,
    write_optimization,
)
from jevcompiler.providers.base import SystemOneResult
from jevcompiler.providers.cache import (
    CacheMissError,
    CacheMode,
    CachingSystemOneProvider,
    JevCache,
)
from jevcompiler.specs.program import (
    BranchNode,
    BranchRule,
    ChoiceQuestion,
    DecisionProgram,
    JevNode,
)


def _program() -> DecisionProgram:
    return DecisionProgram(
        name="router",
        actions=["billing", "technical", "manual_review"],
        entrypoint="classify",
        jev_model="jev-test",
        stages=[
            JevNode(
                id="classify",
                type="jev",
                questions={
                    "route": ChoiceQuestion(
                        type="choice",
                        instructions="Route this ticket",
                        criteria={
                            "billing": "Charges",
                            "technical": "Broken behavior",
                            "manual_review": "Ambiguous",
                        },
                    )
                },
                next="decide",
            ),
            BranchNode(
                id="decide",
                type="branch",
                rules=[
                    BranchRule(
                        when="route.choice == 'billing' and route.confidence >= 0.7",
                        **{"return": "billing"},
                    ),
                    BranchRule(
                        when="route.choice == 'technical' and route.confidence >= 0.7",
                        **{"return": "technical"},
                    ),
                ],
                default="manual_review",
            ),
        ],
    )


def _case(index: int, choice: str, confidence: float, expected: str) -> DatasetCase:
    now = datetime.now(UTC)
    return DatasetCase(
        id=f"case_{index:016x}",
        state={"choice": choice, "confidence": confidence},
        expected_action=expected,
        bucket="normal",
        summary=f"{choice} at {confidence}",
        provenance=CaseProvenance(
            source="teacher",
            role="normal_generator",
            provider="fake",
            requested_model="fake",
            actual_model="fake",
            generated_at=now,
            seed=1,
        ),
        label=LabelMetadata(
            provider="fake",
            requested_model="fake",
            actual_model="fake",
            labeled_at=now,
            confidence=1,
        ),
    )


class ConfidenceProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(self, state, questions, *, model):
        self.calls += 1
        choice = state["choice"]
        confidence = state["confidence"]
        return SystemOneResult.from_api(
            {
                "model": model,
                "answers": {
                    "route": {
                        "type": "choice",
                        "choice": choice,
                        "probabilities": {choice: confidence},
                        "confidence": confidence,
                    }
                },
            }
        )


def test_threshold_search_reuses_cache_and_improves_selection(tmp_path) -> None:
    cases = [
        _case(1, "billing", 0.9, "billing"),
        _case(2, "billing", 0.6, "billing"),
        _case(3, "technical", 0.4, "manual_review"),
    ]

    async def exercise():
        upstream = ConfidenceProvider()
        with JevCache(tmp_path / "jev.sqlite3") as cache:
            provider = CachingSystemOneProvider(cache, upstream)
            result = await Optimizer(provider).optimize(
                _program(), cases, thresholds=[0.3, 0.5, 0.7]
            )
            return result, upstream.calls

    result, calls = asyncio.run(exercise())
    selected = next(
        candidate
        for candidate in result.candidates
        if candidate.candidate_id == result.selected_candidate_id
    )

    assert selected.metrics is not None
    assert selected.metrics.accuracy == 1.0
    assert selected.parent_id == result.baseline_candidate_id
    assert result.baseline_failures.total_failures == 1
    assert result.selected_failures.total_failures == 0
    baseline = next(
        candidate
        for candidate in result.candidates
        if candidate.candidate_id == result.baseline_candidate_id
    )
    assert baseline.status == "rejected"
    assert baseline.rejection_reason
    assert calls == 3
    assert result.live_calls == 3
    assert result.cache_hits == 6

    output = tmp_path / "optimization"
    write_optimization(result, output)
    assert (output / "selected-program.yaml").exists()
    assert (output / "lineage.json").exists()
    assert (output / "baseline-failures" / "failures.jsonl").exists()


def test_structured_question_and_early_exit_mutations_are_valid() -> None:
    program = _program()
    rewrite = rewrite_choice_question(
        program,
        stage_id="classify",
        question_id="route",
        instructions="Select the single responsible team.",
        criteria={
            "billing": "Payment or invoice",
            "technical": "Product malfunction",
            "manual_review": "Unclear",
        },
        hypothesis="Sharper criteria reduce class overlap.",
    )
    early_exit = add_choice_early_exit(
        rewrite.program,
        stage_id="classify",
        question_id="route",
        action="billing",
        min_confidence=0.95,
        hypothesis="Very confident billing predictions can return early.",
    )

    assert confidence_dimensions(program) == ["route"]
    assert rewrite.program != program
    assert len(early_exit.program.stages) == len(program.stages) + 1
    assert early_exit.program.stages[1].type == "branch"


def test_replay_only_optimization_fails_closed_on_missing_evidence(tmp_path) -> None:
    case = _case(1, "billing", 0.9, "billing")
    with JevCache(tmp_path / "empty.sqlite3") as cache:
        provider = CachingSystemOneProvider(cache, mode=CacheMode.replay_only)
        with pytest.raises(CacheMissError):
            asyncio.run(Optimizer(provider).optimize(_program(), [case]))
