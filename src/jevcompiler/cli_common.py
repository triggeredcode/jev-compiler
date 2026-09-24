from __future__ import annotations

from jevcompiler.specs.task import TaskSpec, TeacherConfig


def teacher_config_for(
    task: TaskSpec, override: str | None, *, allow_paid: bool = False
) -> TeacherConfig:
    """Apply CLI teacher overrides while preserving the paid-provider guard."""
    if override is None:
        return task.teacher.model_copy(
            update={"allow_paid": task.teacher.allow_paid or allow_paid}
        )

    provider, separator, model = override.partition(":")
    data = task.teacher.model_dump()
    data.update(
        {
            "provider": provider,
            "model": model if separator and model else None,
            "allow_paid": allow_paid,
        }
    )
    return TeacherConfig.model_validate(data)
