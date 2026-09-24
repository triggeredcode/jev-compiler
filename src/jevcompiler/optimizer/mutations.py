"""Safe, structured mutations over the declarative DecisionProgram DSL."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from jevcompiler.runs import content_digest
from jevcompiler.specs.program import (
    BranchNode,
    BranchRule,
    ChoiceQuestion,
    DecisionProgram,
    JevNode,
    NoulQuestion,
    ScoreQuestion,
)

_THRESHOLD = re.compile(
    r"(?P<variable>\b[A-Za-z_][A-Za-z0-9_]*)\.confidence"
    r"(?P<spacing>\s*>=\s*)"
    r"(?P<value>(?:0(?:\.\d+)?|1(?:\.0+)?))"
)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

QuestionValue = ChoiceQuestion | ScoreQuestion | NoulQuestion


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


def _program_data(program: DecisionProgram) -> dict[str, Any]:
    return program.model_dump(mode="json", by_alias=True, exclude_none=True)


def _jev_stage(data: dict[str, Any], stage_id: str) -> dict[str, Any]:
    target = next((stage for stage in data["stages"] if stage["id"] == stage_id), None)
    if target is None or target["type"] != "jev":
        raise MutationError(f"unknown Jev stage {stage_id}")
    return target


def _question_is_referenced(program: DecisionProgram, question_id: str) -> bool:
    reference = re.compile(rf"\b{re.escape(question_id)}\s*\.")
    for stage in program.stages:
        if isinstance(stage, JevNode) and stage.when and reference.search(stage.when):
            return True
        if isinstance(stage, BranchNode) and any(
            reference.search(rule.when) for rule in stage.rules
        ):
            return True
    return False


def add_question(
    program: DecisionProgram,
    *,
    stage_id: str,
    question_id: str,
    question: QuestionValue,
    hypothesis: str,
) -> MutationCandidate:
    if not _IDENTIFIER.fullmatch(question_id):
        raise MutationError("question id must be an expression-safe identifier")
    if any(
        question_id in stage.questions
        for stage in program.stages
        if isinstance(stage, JevNode)
    ):
        raise MutationError(f"question id already exists: {question_id}")
    data = _program_data(program)
    target = _jev_stage(data, stage_id)
    target["questions"][question_id] = question.model_dump(
        mode="json", exclude_none=True
    )
    mutated = DecisionProgram.model_validate(data)
    return MutationCandidate(
        program=mutated,
        mutation_type="question_add",
        hypothesis=hypothesis,
        semantic_diff=f"add {stage_id}.{question_id} ({question.type})",
        parent_id=program_id(program),
    )


def remove_question(
    program: DecisionProgram,
    *,
    stage_id: str,
    question_id: str,
    hypothesis: str,
) -> MutationCandidate:
    data = _program_data(program)
    target = _jev_stage(data, stage_id)
    if question_id not in target["questions"]:
        raise MutationError(f"unknown question {stage_id}.{question_id}")
    if _question_is_referenced(program, question_id):
        raise MutationError(f"cannot remove referenced question {question_id}")
    if len(target["questions"]) == 1:
        raise MutationError("a Jev stage must retain at least one question")
    removed = target["questions"].pop(question_id)
    mutated = DecisionProgram.model_validate(data)
    return MutationCandidate(
        program=mutated,
        mutation_type="question_remove",
        hypothesis=hypothesis,
        semantic_diff=f"remove {stage_id}.{question_id} ({removed['type']})",
        parent_id=program_id(program),
    )


def split_choice_question(
    program: DecisionProgram,
    *,
    stage_id: str,
    question_id: str,
    verifier_id: str,
    verifier_instructions: str,
    hypothesis: str,
) -> MutationCandidate:
    stage = next(
        (
            node
            for node in program.stages
            if node.id == stage_id and isinstance(node, JevNode)
        ),
        None,
    )
    if stage is None:
        raise MutationError(f"unknown Jev stage {stage_id}")
    question = stage.questions.get(question_id)
    if not isinstance(question, ChoiceQuestion):
        raise MutationError(f"unknown Choice question {stage_id}.{question_id}")
    verifier = ChoiceQuestion(
        type="choice",
        instructions=verifier_instructions,
        criteria=question.criteria,
    )
    added = add_question(
        program,
        stage_id=stage_id,
        question_id=verifier_id,
        question=verifier,
        hypothesis=hypothesis,
    )
    return MutationCandidate(
        program=added.program,
        mutation_type="question_split",
        hypothesis=hypothesis,
        semantic_diff=(
            f"split {stage_id}.{question_id} with verifier {stage_id}.{verifier_id}"
        ),
        parent_id=program_id(program),
    )


def merge_choice_questions(
    program: DecisionProgram,
    *,
    stage_id: str,
    primary_id: str,
    secondary_id: str,
    instructions: str,
    hypothesis: str,
) -> MutationCandidate:
    if primary_id == secondary_id:
        raise MutationError("merge requires two different questions")
    stage = next(
        (
            node
            for node in program.stages
            if node.id == stage_id and isinstance(node, JevNode)
        ),
        None,
    )
    if stage is None:
        raise MutationError(f"unknown Jev stage {stage_id}")
    primary = stage.questions.get(primary_id)
    secondary = stage.questions.get(secondary_id)
    if not isinstance(primary, ChoiceQuestion) or not isinstance(
        secondary, ChoiceQuestion
    ):
        raise MutationError("merge requires two Choice questions in the same stage")
    if set(primary.criteria) != set(secondary.criteria):
        raise MutationError("merged Choice questions must have identical criterion keys")
    if _question_is_referenced(program, secondary_id):
        raise MutationError(f"cannot merge referenced question {secondary_id}")

    data = _program_data(program)
    target = _jev_stage(data, stage_id)
    target["questions"][primary_id] = ChoiceQuestion(
        type="choice",
        instructions=instructions,
        criteria={
            key: f"{primary.criteria[key]} {secondary.criteria[key]}".strip()
            for key in primary.criteria
        },
    ).model_dump(mode="json")
    del target["questions"][secondary_id]
    mutated = DecisionProgram.model_validate(data)
    return MutationCandidate(
        program=mutated,
        mutation_type="question_merge",
        hypothesis=hypothesis,
        semantic_diff=(
            f"merge {stage_id}.{secondary_id} into {stage_id}.{primary_id}"
        ),
        parent_id=program_id(program),
    )


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
