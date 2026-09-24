from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from jevcompiler.specs.common import load_yaml_mapping


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StateSpec(StrictModel):
    description: str = Field(min_length=1)
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")


class ObjectiveSpec(StrictModel):
    primary: Literal["teacher_agreement"] = "teacher_agreement"
    secondary: list[
        Literal["minimize_cost", "minimize_latency", "minimize_graph_complexity"]
    ] = Field(default_factory=list)


class TaskConstraints(StrictModel):
    max_jev_calls: int = Field(default=3, ge=1, le=100)
    max_questions: int = Field(default=12, ge=1, le=500)
    allow_fallback: bool = True


class TeacherConfig(StrictModel):
    provider: Literal[
        "auto", "ollama", "lmstudio", "openrouter", "openai", "openai-compatible"
    ] = "auto"
    model: str | None = None
    base_url: HttpUrl | None = None
    allow_paid: bool = False


class TaskSpec(StrictModel):
    version: Literal[1] = 1
    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str = Field(min_length=1)
    state: StateSpec
    actions: list[str] = Field(min_length=2)
    policy: list[str] = Field(min_length=1)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    objectives: ObjectiveSpec = Field(default_factory=ObjectiveSpec)
    constraints: TaskConstraints = Field(default_factory=TaskConstraints)
    teacher: TeacherConfig = Field(default_factory=TeacherConfig)

    @model_validator(mode="after")
    def validate_actions(self) -> TaskSpec:
        if len(set(self.actions)) != len(self.actions):
            raise ValueError("actions must be unique")
        if any(not action.strip() for action in self.actions):
            raise ValueError("actions cannot be blank")
        return self


def load_task(path: str | Path) -> TaskSpec:
    return TaskSpec.model_validate(load_yaml_mapping(path))
