from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from jevcompiler.providers.base import ChoiceAnswer, NoulAnswer, ScoreAnswer, SystemOneProvider
from jevcompiler.runtime.expressions import evaluate_expression
from jevcompiler.specs.program import BranchNode, DecisionProgram, JevNode, ReturnNode


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: str
    stage_type: str
    started_at: datetime
    output: dict[str, Any] = Field(default_factory=dict)


class DecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    variables: dict[str, Any]
    trace: list[TraceEvent]


def _answer_variables(answer: ChoiceAnswer | ScoreAnswer | NoulAnswer) -> Any:
    if isinstance(answer, NoulAnswer):
        return answer.noul
    if isinstance(answer, ChoiceAnswer):
        return {
            "value": answer.choice,
            "choice": answer.choice,
            "confidence": answer.confidence,
            "probabilities": answer.probabilities,
        }
    return {
        "value": answer.score,
        "score": answer.score,
        "confidence": answer.confidence,
        "probabilities": answer.probabilities,
        "legend": answer.legend,
    }


class ProgramRuntime:
    def __init__(self, provider: SystemOneProvider) -> None:
        self.provider = provider

    async def run(self, program: DecisionProgram, state: Any) -> DecisionResult:
        stages = {node.id: node for node in program.stages}
        positions = {node.id: index for index, node in enumerate(program.stages)}
        current = program.entrypoint or program.stages[0].id
        variables: dict[str, Any] = {}
        trace: list[TraceEvent] = []
        visited: set[str] = set()

        while current:
            if current in visited:
                raise RuntimeError(f"cycle detected at stage {current}")
            visited.add(current)
            node = stages[current]
            started = datetime.now(UTC)

            if isinstance(node, JevNode):
                if node.when is None or bool(evaluate_expression(node.when, variables)):
                    response = await self.provider.evaluate(
                        state, node.questions, model=program.jev_model
                    )
                    output = {
                        key: _answer_variables(answer) for key, answer in response.answers.items()
                    }
                    missing = set(node.questions) - set(output)
                    if missing:
                        raise RuntimeError(f"Jev response omitted answers: {sorted(missing)}")
                    variables.update(output)
                    trace.append(TraceEvent(
                        stage_id=node.id,
                        stage_type=node.type,
                        started_at=started,
                        output={"model": response.model, "answers": output},
                    ))
                else:
                    trace.append(TraceEvent(
                        stage_id=node.id,
                        stage_type=node.type,
                        started_at=started,
                        output={"skipped": True},
                    ))
                current = node.next or self._next_stage(program, positions[current])
                continue

            if isinstance(node, BranchNode):
                action = next(
                    (
                        rule.return_
                        for rule in node.rules
                        if bool(evaluate_expression(rule.when, variables))
                    ),
                    node.default,
                )
                trace.append(TraceEvent(
                    stage_id=node.id,
                    stage_type=node.type,
                    started_at=started,
                    output={"action": action},
                ))
                if action is not None:
                    return DecisionResult(action=action, variables=variables, trace=trace)
                current = node.next or self._next_stage(program, positions[current])
                continue

            if isinstance(node, ReturnNode):
                trace.append(TraceEvent(
                    stage_id=node.id,
                    stage_type=node.type,
                    started_at=started,
                    output={"action": node.value},
                ))
                return DecisionResult(action=node.value, variables=variables, trace=trace)

        raise RuntimeError("program ended without returning an action")

    @staticmethod
    def _next_stage(program: DecisionProgram, position: int) -> str | None:
        next_position = position + 1
        return program.stages[next_position].id if next_position < len(program.stages) else None

