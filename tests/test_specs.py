import pytest
from pydantic import ValidationError

from jevcompiler.specs.program import DecisionProgram
from jevcompiler.specs.task import TaskSpec


def test_task_rejects_duplicate_actions() -> None:
    with pytest.raises(ValidationError, match="actions must be unique"):
        TaskSpec.model_validate(
            {
                "name": "bad-task",
                "description": "A task",
                "state": {"description": "Input"},
                "actions": ["yes", "yes"],
                "policy": ["Choose carefully"],
            }
        )


def test_program_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError, match="unknown action"):
        DecisionProgram.model_validate(
            {
                "name": "bad-program",
                "actions": ["yes"],
                "stages": [{"id": "finish", "type": "return", "value": "no"}],
            }
        )


def test_program_rejects_unknown_next_stage() -> None:
    with pytest.raises(ValidationError, match="unknown next stage"):
        DecisionProgram.model_validate(
            {
                "name": "bad-link",
                "actions": ["yes"],
                "stages": [
                    {
                        "id": "judge",
                        "type": "jev",
                        "questions": {
                            "ready": {"type": "noul", "instructions": "Is it ready?"}
                        },
                        "next": "missing",
                    }
                ],
            }
        )


def test_program_rejects_duplicate_question_ids_across_stages() -> None:
    with pytest.raises(ValidationError, match="question ids must be unique"):
        DecisionProgram.model_validate(
            {
                "name": "bad-questions",
                "actions": ["yes"],
                "stages": [
                    {
                        "id": "first",
                        "type": "jev",
                        "questions": {
                            "ready": {"type": "noul", "instructions": "Ready?"}
                        },
                    },
                    {
                        "id": "second",
                        "type": "jev",
                        "questions": {
                            "ready": {"type": "noul", "instructions": "Still ready?"}
                        },
                    },
                ],
            }
        )


def test_program_rejects_question_ids_that_cannot_be_expression_variables() -> None:
    with pytest.raises(ValidationError, match="expression-safe identifiers"):
        DecisionProgram.model_validate(
            {
                "name": "bad-question-name",
                "actions": ["yes"],
                "stages": [
                    {
                        "id": "judge",
                        "type": "jev",
                        "questions": {
                            "not-valid": {"type": "noul", "instructions": "Ready?"}
                        },
                    }
                ],
            }
        )
