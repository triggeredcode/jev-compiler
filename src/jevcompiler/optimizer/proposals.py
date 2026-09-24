"""Teacher-assisted proposals constrained to safe question rewrites."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, create_model

from jevcompiler.optimizer.models import FailureCorpus
from jevcompiler.optimizer.mutations import (
    MutationCandidate,
    MutationError,
    rewrite_choice_question,
)
from jevcompiler.providers.teacher import TeacherProvider
from jevcompiler.specs.program import DecisionProgram


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuestionRewriteDraft(StrictModel):
    stage_id: str
    question_id: str
    hypothesis: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    criteria: dict[str, str] = Field(min_length=2)


class QuestionRewriteBatch(StrictModel):
    proposals: list[QuestionRewriteDraft] = Field(min_length=1)


class ProposalError(ValueError):
    """A teacher proposal could not be compiled into a safe mutation."""


async def propose_question_rewrites(
    teacher: TeacherProvider,
    program: DecisionProgram,
    failures: FailureCorpus,
    *,
    limit: int = 3,
    max_attempts: int = 2,
) -> list[MutationCandidate]:
    if limit < 1:
        raise ValueError("proposal limit must be positive")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    schema = create_model(
        f"QuestionRewriteBatch{limit}",
        __base__=QuestionRewriteBatch,
        proposals=(
            list[QuestionRewriteDraft],
            Field(min_length=1, max_length=limit),
        ),
    )
    evidence = failures.model_dump_json(
        include={"cases": {"__all__": {"expected_action", "predicted_action", "state", "error"}}}
    )
    messages = [
        {
            "role": "system",
            "content": (
                "Propose bounded Choice-question rewrites for a declarative decision program. "
                "Each rewrite must target an existing Choice question, preserve its exact "
                "criterion keys, state a falsifiable hypothesis, and emit no code or graph."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Return at most {limit} proposals.\n"
                f"Program:\n{program.model_dump_json(by_alias=True, exclude_none=True)}\n"
                f"Selection failures:\n{evidence}"
            ),
        },
    ]
    last_problem = ""
    for attempt in range(max_attempts):
        if attempt:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Repair every proposal using only exact stage/question IDs and criterion "
                        f"keys from the program. Validation problem: {last_problem}"
                    ),
                }
            )
        generation = await teacher.structured_generate(
            messages,
            schema,
            temperature=0.2,
            max_tokens=4096,
        )
        mutations: list[MutationCandidate] = []
        try:
            for proposal in generation.value.proposals:
                mutations.append(
                    rewrite_choice_question(
                        program,
                        stage_id=proposal.stage_id,
                        question_id=proposal.question_id,
                        instructions=proposal.instructions,
                        criteria=proposal.criteria,
                        hypothesis=proposal.hypothesis,
                    )
                )
        except MutationError as exc:
            last_problem = str(exc)
            continue
        return mutations
    raise ProposalError(f"invalid rewrite proposal: {last_problem}")
