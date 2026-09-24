import asyncio
from datetime import UTC, datetime

import pytest

from jevcompiler.dataset.models import CaseProvenance, DatasetCase, LabelMetadata
from jevcompiler.optimizer import (
    Optimizer,
    add_choice_early_exit,
    add_question,
    confidence_dimensions,
    merge_choice_questions,
    remove_question,
    rewrite_choice_question,
    split_choice_question,
    write_optimization,
)
from jevcompiler.optimizer.mutations import MutationError
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
    assert result.selection_digest is not None

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


def test_add_remove_split_and_merge_questions_preserve_valid_graphs() -> None:
    program = _program()
    extra = ChoiceQuestion(
        type="choice",
        instructions="Independently verify the route.",
        criteria={
            "billing": "Payment concern",
            "technical": "Product concern",
            "manual_review": "Unclear concern",
        },
    )
    added = add_question(
        program,
        stage_id="classify",
        question_id="route_check",
        question=extra,
        hypothesis="A second view may expose ambiguity.",
    )
    removed = remove_question(
        added.program,
        stage_id="classify",
        question_id="route_check",
        hypothesis="The verifier did not improve quality.",
    )
    split = split_choice_question(
        program,
        stage_id="classify",
        question_id="route",
        verifier_id="route_check",
        verifier_instructions="Verify the primary route independently.",
        hypothesis="Independent classification may expose ambiguity.",
    )
    merged = merge_choice_questions(
        split.program,
        stage_id="classify",
        primary_id="route",
        secondary_id="route_check",
        instructions="Route and verify this ticket in one answer.",
        hypothesis="One consolidated question may be sufficient.",
    )

    assert "route_check" in added.program.stages[0].questions
    assert removed.program == program
    assert split.program.stages[0].questions["route_check"].criteria == (
        program.stages[0].questions["route"].criteria
    )
    assert "route_check" not in merged.program.stages[0].questions
    assert merged.program.stages[0].questions["route"].instructions.startswith("Route")


def test_question_mutations_fail_closed_on_duplicates_and_references() -> None:
    program = _program()
    extra = ChoiceQuestion(
        type="choice",
        instructions="Verify route.",
        criteria={
            "billing": "Payment",
            "technical": "Product",
            "manual_review": "Unclear",
        },
    )
    with pytest.raises(MutationError, match="already exists"):
        add_question(
            program,
            stage_id="classify",
            question_id="route",
            question=extra,
            hypothesis="Invalid duplicate.",
        )
    with pytest.raises(MutationError, match="referenced question"):
        remove_question(
            program,
            stage_id="classify",
            question_id="route",
            hypothesis="Invalid removal.",
        )

    split = split_choice_question(
        program,
        stage_id="classify",
        question_id="route",
        verifier_id="route_check",
        verifier_instructions="Verify route.",
        hypothesis="Add verifier.",
    )
    referenced_data = split.program.model_dump(mode="json", by_alias=True)
    referenced_data["stages"][1]["rules"].append(
        {
            "when": "route_check.choice == 'billing'",
            "return": "billing",
        }
    )
    referenced = DecisionProgram.model_validate(referenced_data)
    with pytest.raises(MutationError, match="cannot merge referenced"):
        merge_choice_questions(
            referenced,
            stage_id="classify",
            primary_id="route",
            secondary_id="route_check",
            instructions="Merge route checks.",
            hypothesis="Invalid referenced merge.",
        )


def test_replay_only_optimization_fails_closed_on_missing_evidence(tmp_path) -> None:
    case = _case(1, "billing", 0.9, "billing")
    with JevCache(tmp_path / "empty.sqlite3") as cache:
        provider = CachingSystemOneProvider(cache, mode=CacheMode.replay_only)
        with pytest.raises(CacheMissError):
            asyncio.run(Optimizer(provider).optimize(_program(), [case]))


def test_equal_candidate_does_not_displace_baseline(tmp_path) -> None:
    case = _case(1, "billing", 0.95, "billing")

    async def exercise():
        with JevCache(tmp_path / "jev.sqlite3") as cache:
            provider = CachingSystemOneProvider(cache, ConfidenceProvider())
            return await Optimizer(provider).optimize(
                _program(), [case], thresholds=[0.5, 0.7, 0.9]
            )

    result = asyncio.run(exercise())
    assert result.selected_candidate_id == result.baseline_candidate_id


def test_optimizer_records_counterfactual_stability(tmp_path) -> None:
    parent = _case(1, "billing", 0.95, "billing")
    child = _case(2, "technical", 0.95, "technical").model_copy(
        update={"bucket": "counterfactual", "parent_id": parent.id}
    )

    with JevCache(tmp_path / "jev.sqlite3") as cache:
        provider = CachingSystemOneProvider(cache, ConfidenceProvider())
        result = asyncio.run(
            Optimizer(provider).optimize(_program(), [parent, child], thresholds=[0.7])
        )

    selected = next(
        candidate
        for candidate in result.candidates
        if candidate.candidate_id == result.selected_candidate_id
    )
    assert selected.metrics is not None
    assert selected.metrics.counterfactual_pairs == 1
    assert selected.metrics.counterfactual_stability == 1.0


def test_held_out_evaluation_preserves_selection_and_compares_baseline(tmp_path) -> None:
    selection = [
        _case(1, "billing", 0.9, "billing"),
        _case(2, "billing", 0.6, "billing"),
        _case(3, "technical", 0.4, "manual_review"),
    ]
    held_out = [
        _case(4, "billing", 0.6, "billing"),
        _case(5, "technical", 0.4, "manual_review"),
    ]

    async def exercise():
        upstream = ConfidenceProvider()
        with JevCache(tmp_path / "jev.sqlite3") as cache:
            provider = CachingSystemOneProvider(cache, upstream)
            optimizer = Optimizer(provider)
            result = await optimizer.optimize(_program(), selection, thresholds=[0.3, 0.5, 0.7])
            selected_id = result.selected_candidate_id
            result = await optimizer.evaluate_held_out(result, held_out)
            return result, selected_id

    result, selected_id = asyncio.run(exercise())

    assert result.selected_candidate_id == selected_id
    assert result.held_out is not None
    assert result.held_out.digest != result.selection_digest
    assert result.held_out.baseline_metrics.accuracy == 0.5
    assert result.held_out.selected_metrics.accuracy == 1.0
    assert result.held_out.baseline_evaluation.total == 2
    assert result.held_out.selected_evaluation.total == 2

    output = tmp_path / "optimization"
    write_optimization(result, output)
    assert (output / "held-out.json").exists()


def test_held_out_evaluation_does_not_duplicate_identical_program(tmp_path) -> None:
    case = _case(1, "billing", 0.95, "billing")

    async def exercise():
        provider = ConfidenceProvider()
        optimizer = Optimizer(provider)
        result = await optimizer.optimize(_program(), [case], thresholds=[0.7])
        calls_before = provider.calls
        result = await optimizer.evaluate_held_out(result, [case])
        return result, provider.calls - calls_before

    result, held_out_calls = asyncio.run(exercise())

    assert result.selected_candidate_id == result.baseline_candidate_id
    assert result.held_out is not None
    assert held_out_calls == 1


def test_empty_held_out_split_is_explicitly_unavailable(tmp_path) -> None:
    case = _case(1, "billing", 0.95, "billing")

    async def exercise():
        with JevCache(tmp_path / "jev.sqlite3") as cache:
            provider = CachingSystemOneProvider(cache, ConfidenceProvider())
            optimizer = Optimizer(provider)
            result = await optimizer.optimize(_program(), [case], thresholds=[0.7])
            return await optimizer.evaluate_held_out(result, [])

    result = asyncio.run(exercise())
    assert result.held_out is None


def test_candidate_budget_stops_search_after_hard_ceiling(tmp_path) -> None:
    cases = [
        _case(1, "billing", 0.9, "billing"),
        _case(2, "billing", 0.6, "billing"),
    ]

    async def exercise():
        with JevCache(tmp_path / "jev.sqlite3") as cache:
            provider = CachingSystemOneProvider(cache, ConfidenceProvider())
            return await Optimizer(provider).optimize(
                _program(),
                cases,
                thresholds=[0.1, 0.2, 0.3, 0.4, 0.5],
                max_candidates=2,
            )

    result = asyncio.run(exercise())

    assert len(result.candidates) == 2
    assert result.search is not None
    assert result.search.candidate_budget == 2
    assert result.search.evaluated_candidates == 2
    assert result.search.stop_reason == "candidate_budget"


def test_candidate_budget_must_allow_the_baseline(tmp_path) -> None:
    with JevCache(tmp_path / "jev.sqlite3") as cache:
        provider = CachingSystemOneProvider(cache, ConfidenceProvider())
        with pytest.raises(ValueError, match="max_candidates must be positive"):
            asyncio.run(Optimizer(provider).optimize(_program(), [], max_candidates=0))
