import asyncio

import pytest

from jevcompiler.optimizer.models import FailureCorpus
from jevcompiler.optimizer.proposals import ProposalError, propose_question_rewrites
from jevcompiler.providers.teacher import RecordedTeacherProvider
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
        actions=["billing", "manual_review"],
        stages=[
            JevNode(
                id="classify",
                type="jev",
                questions={
                    "route": ChoiceQuestion(
                        type="choice",
                        instructions="Route it",
                        criteria={"billing": "Charges", "manual_review": "Other"},
                    )
                },
            ),
            BranchNode(
                id="decide",
                type="branch",
                rules=[
                    BranchRule(
                        when="route.confidence >= 0.7",
                        **{"return": "billing"},
                    )
                ],
                default="manual_review",
            ),
        ],
    )


def _failures() -> FailureCorpus:
    return FailureCorpus(total_evaluated=0, total_failures=0, cases=[], clusters=[])


def test_teacher_proposal_compiles_to_a_bounded_rewrite() -> None:
    teacher = RecordedTeacherProvider(
        [
            {
                "proposals": [
                    {
                        "stage_id": "classify",
                        "question_id": "route",
                        "hypothesis": "Explicit ambiguity reduces false positives.",
                        "instructions": "Choose billing only for an explicit charge.",
                        "criteria": {
                            "billing": "Explicit invoice, payment, or charge",
                            "manual_review": "Anything ambiguous",
                        },
                    }
                ]
            }
        ]
    )

    proposals = asyncio.run(propose_question_rewrites(teacher, _program(), _failures()))

    assert len(proposals) == 1
    assert proposals[0].mutation_type == "question_rewrite"
    assert proposals[0].parent_id


def test_teacher_proposal_cannot_change_legal_criteria() -> None:
    teacher = RecordedTeacherProvider(
        [
            {
                "proposals": [
                    {
                        "stage_id": "classify",
                        "question_id": "route",
                        "hypothesis": "Invent a class.",
                        "instructions": "Choose a class.",
                        "criteria": {"billing": "Charge", "invented": "New"},
                    }
                ]
            }
        ]
    )

    with pytest.raises(ProposalError, match="preserve the exact criterion keys"):
        asyncio.run(propose_question_rewrites(teacher, _program(), _failures()))
