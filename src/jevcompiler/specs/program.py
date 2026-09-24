from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from jevcompiler.specs.common import load_yaml_mapping

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChoiceQuestion(StrictModel):
    type: Literal["choice"]
    instructions: str = Field(min_length=1)
    criteria: dict[str, str] = Field(min_length=2)


class ScoreQuestion(StrictModel):
    type: Literal["score"]
    instructions: str = Field(min_length=1)
    criteria: list[str] = Field(min_length=2)


class NoulQuestion(StrictModel):
    type: Literal["noul"]
    instructions: str = Field(min_length=1)
    criteria: str | dict[str, str] | None = None


Question = Annotated[ChoiceQuestion | ScoreQuestion | NoulQuestion, Field(discriminator="type")]


class JevNode(StrictModel):
    id: str
    type: Literal["jev"]
    questions: dict[str, Question] = Field(min_length=1)
    when: str | None = None
    next: str | None = None


class BranchRule(StrictModel):
    when: str
    return_: str = Field(alias="return")


class BranchNode(StrictModel):
    id: str
    type: Literal["branch"]
    rules: list[BranchRule] = Field(min_length=1)
    default: str | None = None
    next: str | None = None


class ReturnNode(StrictModel):
    id: str
    type: Literal["return"]
    value: str


Node = Annotated[JevNode | BranchNode | ReturnNode, Field(discriminator="type")]


class DecisionProgram(StrictModel):
    version: Literal[1] = 1
    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    actions: list[str] = Field(min_length=1)
    entrypoint: str | None = None
    jev_model: str = "jev-latest"
    stages: list[Node] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_graph(self) -> DecisionProgram:
        node_ids = [node.id for node in self.stages]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("stage ids must be unique")
        known = set(node_ids)
        if self.entrypoint is not None and self.entrypoint not in known:
            raise ValueError(f"unknown entrypoint: {self.entrypoint}")
        action_set = set(self.actions)
        if len(action_set) != len(self.actions):
            raise ValueError("actions must be unique")
        question_ids = [
            question_id
            for node in self.stages
            if isinstance(node, JevNode)
            for question_id in node.questions
        ]
        invalid_question_ids = sorted(
            question_id for question_id in question_ids if not _IDENTIFIER.fullmatch(question_id)
        )
        if invalid_question_ids:
            raise ValueError(
                f"question ids must be expression-safe identifiers: {invalid_question_ids}"
            )
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("question ids must be unique across Jev stages")
        for node in self.stages:
            next_id = getattr(node, "next", None)
            if next_id is not None and next_id not in known:
                raise ValueError(f"stage {node.id} references unknown next stage {next_id}")
            if isinstance(node, BranchNode):
                returned = [rule.return_ for rule in node.rules]
                if node.default is not None:
                    returned.append(node.default)
                unknown = set(returned) - action_set
                if unknown:
                    raise ValueError(f"stage {node.id} returns unknown actions: {sorted(unknown)}")
            if isinstance(node, ReturnNode) and node.value not in action_set:
                raise ValueError(f"stage {node.id} returns unknown action: {node.value}")
        return self


def load_program(path: str | Path) -> DecisionProgram:
    return DecisionProgram.model_validate(load_yaml_mapping(path))
