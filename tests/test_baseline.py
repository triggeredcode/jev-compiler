import asyncio

from jevcompiler.baseline import BaselineCompiler, BaselineEvaluator
from jevcompiler.dataset.models import (
    CaseProvenance,
    DatasetBundle,
    DatasetCase,
    DatasetManifest,
    LabelMetadata,
)
from jevcompiler.providers.base import SystemOneResult
from jevcompiler.providers.teacher import RecordedTeacherProvider
from jevcompiler.specs.task import TaskSpec


def _task() -> TaskSpec:
    return TaskSpec.model_validate(
        {
            "name": "router",
            "description": "Route tickets",
            "state": {"description": "Ticket"},
            "actions": ["billing", "technical", "manual_review"],
            "policy": ["Charges are billing", "Bugs are technical", "Otherwise review"],
        }
    )


def _case(case_id: str, body: str, expected: str) -> DatasetCase:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return DatasetCase(
        id=case_id,
        state={"body": body},
        expected_action=expected,
        bucket="normal",
        summary=body,
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


def _bundle() -> DatasetBundle:
    train = [
        _case("case_1111111111111111", "charged twice", "billing"),
        _case("case_2222222222222222", "app crashes", "technical"),
    ]
    return DatasetBundle(
        manifest=DatasetManifest(
            task_name="router",
            seed=1,
            counts={"train": 2, "dev": 0, "test": 0},
            bucket_counts={"normal": 2},
            corpus_hash="a" * 64,
        ),
        train=train,
        dev=[],
        test=[],
    )


def test_baseline_compiler_emits_restricted_choice_graph() -> None:
    teacher = RecordedTeacherProvider(
        [
            {
                "question_id": "route",
                "instructions": "What is the ticket's primary issue?",
                "criteria": {
                    "billing": "Charges and payments",
                    "technical": "Broken behavior",
                    "manual_review": "Ambiguous or unsupported",
                },
                "confidence_threshold": 0.7,
            }
        ]
    )
    artifact = asyncio.run(BaselineCompiler(teacher).compile(_task(), _bundle()))
    assert [node.type for node in artifact.program.stages] == ["jev", "branch"]
    assert artifact.program.stages[1].default == "manual_review"
    assert artifact.provenance.actual_model == "recorded-model"


class RuleSystemOne:
    async def evaluate(self, state, questions, *, model):
        choice = "billing" if "charged" in state["body"] else "technical"
        return SystemOneResult.from_api(
            {
                "model": "jev-test",
                "answers": {
                    "route": {
                        "type": "choice",
                        "choice": choice,
                        "probabilities": {choice: 0.95, "manual_review": 0.05},
                        "confidence": 0.9,
                    }
                },
            }
        )


def test_evaluator_reports_accuracy_confusion_and_traces() -> None:
    teacher = RecordedTeacherProvider(
        [
            {
                "question_id": "route",
                "instructions": "What is the ticket's primary issue?",
                "criteria": {
                    "billing": "Charges",
                    "technical": "Broken behavior",
                    "manual_review": "Ambiguous",
                },
                "confidence_threshold": 0.7,
            }
        ]
    )
    program = asyncio.run(BaselineCompiler(teacher).compile(_task(), _bundle())).program
    report = asyncio.run(BaselineEvaluator(RuleSystemOne()).evaluate(program, _bundle().train))
    assert report.accuracy == 1.0
    assert report.per_action["billing"].f1 == 1.0
    assert all(result.trace for result in report.cases)

