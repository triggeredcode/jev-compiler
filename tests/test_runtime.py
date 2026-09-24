import asyncio

import pytest

from jevcompiler.providers.base import SystemOneResult
from jevcompiler.providers.fake import RecordedSystemOneProvider
from jevcompiler.runtime.execution import ProgramRuntime
from jevcompiler.specs.program import DecisionProgram


def test_runtime_batches_questions_and_branches() -> None:
    program = DecisionProgram.model_validate(
        {
            "name": "router",
            "actions": ["billing", "review"],
            "stages": [
                {
                    "id": "classify",
                    "type": "jev",
                    "questions": {
                        "route": {
                            "type": "choice",
                            "instructions": "Where should this go?",
                            "criteria": {"billing": "Payment", "other": "Anything else"},
                        },
                        "urgent": {"type": "noul", "instructions": "Is it urgent?"},
                    },
                },
                {
                    "id": "decide",
                    "type": "branch",
                    "rules": [
                        {
                            "when": 'route.choice == "billing" and route.confidence >= 0.8',
                            "return": "billing",
                        }
                    ],
                    "default": "review",
                },
            ],
        }
    )
    response = SystemOneResult.from_api(
        {
            "model": "jev-1.13.0",
            "answers": {
                "route": {
                    "type": "choice",
                    "choice": "billing",
                    "confidence": 0.9,
                    "probabilities": {"billing": 0.95, "other": 0.05},
                },
                "urgent": {"type": "noul", "noul": 0.7},
            },
        }
    )
    provider = RecordedSystemOneProvider([response])

    result = asyncio.run(ProgramRuntime(provider).run(program, {"body": "charged twice"}))

    assert result.action == "billing"
    assert len(provider.calls) == 1
    assert set(provider.calls[0]["questions"]) == {"route", "urgent"}
    assert [event.stage_id for event in result.trace] == ["classify", "decide"]


def test_runtime_detects_explicit_cycle() -> None:
    program = DecisionProgram.model_validate(
        {
            "name": "cycle",
            "actions": ["done"],
            "stages": [
                {
                    "id": "again",
                    "type": "jev",
                    "questions": {"ok": {"type": "noul", "instructions": "Okay?"}},
                    "next": "again",
                }
            ],
        }
    )
    response = SystemOneResult.from_api(
        {"model": "jev", "answers": {"ok": {"type": "noul", "noul": 1.0}}}
    )
    with pytest.raises(RuntimeError, match="cycle detected"):
        asyncio.run(ProgramRuntime(RecordedSystemOneProvider([response])).run(program, {}))
