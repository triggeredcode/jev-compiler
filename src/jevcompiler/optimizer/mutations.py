"""Safe, structured mutations over the declarative DecisionProgram DSL."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from jevcompiler.runs import content_digest
from jevcompiler.specs.program import (
    BranchNode,
    BranchRule,
    ChoiceQuestion,
    DecisionProgram,
    JevNode,
)

_THRESHOLD = re.compile(
    r"(?P<variable>\b[A-Za-z_][A-Za-z0-9_]*)\.confidence"
    r"(?P<spacing>\s*>=\s*)"
    r"(?P<value>(?:0(?:\.\d+)?|1(?:\.0+)?))"
)


class MutationError(ValueError):
    """A proposed mutation is not valid for the target program."""


@dataclass(frozen=True, slots=True)
class MutationCandidate:
    program: DecisionProgram
    mutation_type: str
    hypothesis: str
    semantic_diff: str
    parent_id: str | None = None


def program_id(program: DecisionProgram) -> str:
    digest = content_digest(program.model_dump(mode="json", by_alias=True, exclude_none=True))
    return f"candidate_{digest[:16]}"


def confidence_dimensions(program: DecisionProgram) -> list[str]:
    dimensions: set[str] = set()
    for stage in program.stages:
        if isinstance(stage, BranchNode):
            for rule in stage.rules:
                dimensions.update(
                    match.group("variable") for match in _THRESHOLD.finditer(rule.when)
                )
    return sorted(dimensions)


def set_confidence_threshold(
    program: DecisionProgram, variable: str, threshold: float
) -> MutationCandidate:
    if not 0 <= threshold <= 1:
        raise MutationError("confidence threshold must be between 0 and 1")
    data = program.model_dump(mode="json", by_alias=True, exclude_none=True)
    replacements = 0
    rendered = format(threshold, ".6g")
    for stage in data["stages"]:
        if stage["type"] != "branch":
            continue
        for rule in stage["rules"]:
            def replace(match: re.Match[str]) -> str:
                nonlocal replacements
                if match.group("variable") != variable:
                    return match.group(0)
                replacements += 1
                return f"{variable}.confidence{match.group('spacing')}{rendered}"

            rule["when"] = _THRESHOLD.sub(replace, rule["when"])
    if not replacements:
        raise MutationError(f"program has no confidence threshold for {variable}")
    mutated = DecisionProgram.model_validate(data)
    return MutationCandidate(
        program=mutated,
        mutation_type="threshold",
        hypothesis=f"Changing {variable} confidence to {rendered} improves calibrated routing.",
        semantic_diff=f"{variable}.confidence threshold -> {rendered}",
        parent_id=program_id(program),
    )


def rewrite_choice_question(
    program: DecisionProgram,
    *,
    stage_id: str,
    question_id: str,
    instructions: str,
    criteria: dict[str, str],
    hypothesis: str,
) -> MutationCandidate:
    data = program.model_dump(mode="json", by_alias=True, exclude_none=True)
    target = next((stage for stage in data["stages"] if stage["id"] == stage_id), None)
    if target is None or target["type"] != "jev":
        raise MutationError(f"unknown Jev stage {stage_id}")
    original = target["questions"].get(question_id)
    if original is None or original["type"] != "choice":
        raise MutationError(f"unknown Choice question {stage_id}.{question_id}")
    if set(criteria) != set(original["criteria"]):
        raise MutationError("a question rewrite must preserve the exact criterion keys")
    target["questions"][question_id] = ChoiceQuestion(
        type="choice",
        instructions=instructions,
        criteria=criteria,
    ).model_dump(mode="json")
    mutated = DecisionProgram.model_validate(data)
    before = content_digest(original)[:8]
    after = content_digest(target["questions"][question_id])[:8]
    return MutationCandidate(
        program=mutated,
        mutation_type="question_rewrite",
        hypothesis=hypothesis,
        semantic_diff=f"{stage_id}.{question_id} rewrite {before} -> {after}",
        parent_id=program_id(program),
    )


def add_choice_early_exit(
    program: DecisionProgram,
    *,
    stage_id: str,
    question_id: str,
    action: str,
    min_confidence: float,
    hypothesis: str,
) -> MutationCandidate:
    if not 0 <= min_confidence <= 1:
        raise MutationError("minimum confidence must be between 0 and 1")
    stages = list(program.stages)
    position = next((index for index, stage in enumerate(stages) if stage.id == stage_id), None)
    if position is None or not isinstance(stages[position], JevNode):
        raise MutationError(f"unknown Jev stage {stage_id}")
    target = stages[position]
    question = target.questions.get(question_id)
    if not isinstance(question, ChoiceQuestion):
        raise MutationError(f"unknown Choice question {stage_id}.{question_id}")
    if action not in question.criteria or action not in program.actions:
        raise MutationError(f"early-exit action {action!r} is not a legal criterion")

    suffix = hashlib.sha256(f"{stage_id}:{question_id}:{action}".encode()).hexdigest()[:8]
    branch_id = f"early_exit_{suffix}"
    if any(stage.id == branch_id for stage in stages):
        raise MutationError(f"generated early-exit stage already exists: {branch_id}")
    old_next = target.next
    if old_next is None and position + 1 < len(stages):
        old_next = stages[position + 1].id
    updated_target = target.model_copy(update={"next": branch_id})
    branch = BranchNode(
        id=branch_id,
        type="branch",
        rules=[
            BranchRule(
                when=(
                    f"{question_id}.choice == {action!r} and "
                    f"{question_id}.confidence >= {format(min_confidence, '.6g')}"
                ),
                **{"return": action},
            )
        ],
        next=old_next,
    )
    stages[position] = updated_target
    stages.insert(position + 1, branch)
    mutated = program.model_copy(update={"stages": stages})
    mutated = DecisionProgram.model_validate(mutated.model_dump(mode="json", by_alias=True))
    return MutationCandidate(
        program=mutated,
        mutation_type="early_exit",
        hypothesis=hypothesis,
        semantic_diff=(
            f"insert {branch_id} after {stage_id}: return {action} at confidence "
            f">= {format(min_confidence, '.6g')}"
        ),
        parent_id=program_id(program),
    )
