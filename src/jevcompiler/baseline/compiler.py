"""Compile a constrained baseline plan into the DecisionProgram DSL."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from jevcompiler.baseline.models import BaselineArtifact, BaselinePlan, BaselineProvenance
from jevcompiler.dataset.models import DatasetBundle
from jevcompiler.providers.teacher import TeacherProvider
from jevcompiler.specs.program import (
    BranchNode,
    BranchRule,
    ChoiceQuestion,
    DecisionProgram,
    JevNode,
)
from jevcompiler.specs.task import TaskSpec


class BaselineCompileError(RuntimeError):
    """The teacher could not produce a valid constrained baseline plan."""


class BaselineCompiler:
    def __init__(self, teacher: TeacherProvider, *, max_attempts: int = 2) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.teacher = teacher
        self.max_attempts = max_attempts

    async def compile(self, task: TaskSpec, dataset: DatasetBundle) -> BaselineArtifact:
        training = [
            {
                "state": case.state,
                "expected_action": case.expected_action,
                "important_factors": case.label.important_factors,
            }
            for case in dataset.train
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    "Design one atomic TypeSafe Choice question as a transparent baseline. "
                    "Criteria keys must exactly equal the legal actions. Keep each criterion "
                    "specific and mutually distinguishable. Do not emit code or a graph."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"TaskSpec:\n{task.model_dump_json(by_alias=True, exclude_none=True)}\n"
                    f"Training cases:\n{json.dumps(training, sort_keys=True)}"
                ),
            },
        ]
        last_problem = ""
        for attempt in range(self.max_attempts):
            if attempt and last_problem:
                messages.append(
                    {
                        "role": "user",
                        "content": f"Repair the plan. Previous validation problem: {last_problem}",
                    }
                )
            generation = await self.teacher.structured_generate(
                messages, BaselinePlan, temperature=0, max_tokens=4096
            )
            plan = generation.value
            if set(plan.criteria) != set(task.actions):
                last_problem = (
                    "criteria keys must exactly equal actions; "
                    f"expected={sorted(task.actions)}, actual={sorted(plan.criteria)}"
                )
                continue
            program = self._program_from_plan(task, plan)
            return BaselineArtifact(
                program=program,
                plan=plan,
                provenance=BaselineProvenance(
                    provider=generation.provider,
                    requested_model=generation.requested_model,
                    actual_model=generation.actual_model,
                    compiled_at=datetime.now(UTC),
                    training_corpus_hash=dataset.manifest.corpus_hash,
                ),
            )
        raise BaselineCompileError(last_problem or "teacher returned no valid baseline plan")

    @staticmethod
    def _program_from_plan(task: TaskSpec, plan: BaselinePlan) -> DecisionProgram:
        fallback = "manual_review" if "manual_review" in task.actions else task.actions[0]
        rules = [
            BranchRule(
                when=(
                    f"{plan.question_id}.choice == {json.dumps(action)} and "
                    f"{plan.question_id}.confidence >= {plan.confidence_threshold}"
                ),
                **{"return": action},
            )
            for action in task.actions
            if action != fallback
        ]
        return DecisionProgram(
            name=task.name,
            actions=task.actions,
            entrypoint="classify",
            stages=[
                JevNode(
                    id="classify",
                    type="jev",
                    questions={
                        plan.question_id: ChoiceQuestion(
                            type="choice",
                            instructions=plan.instructions,
                            criteria=plan.criteria,
                        )
                    },
                    next="decide",
                ),
                BranchNode(
                    id="decide", type="branch", rules=rules, default=fallback
                ),
            ],
        )


def write_baseline(artifact: BaselineArtifact, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    program_data = artifact.program.model_dump(mode="json", by_alias=True, exclude_none=True)
    (output / "program.yaml").write_text(
        yaml.safe_dump(program_data, sort_keys=False), encoding="utf-8"
    )
    (output / "baseline.json").write_text(
        artifact.model_dump_json(indent=2, by_alias=True), encoding="utf-8"
    )
