from typer.testing import CliRunner

from jevcompiler.cli import app
from jevcompiler.cli_common import teacher_config_for
from jevcompiler.specs.task import TaskSpec


def _task() -> TaskSpec:
    return TaskSpec.model_validate(
        {
            "version": 1,
            "name": "support-router",
            "description": "Route a support request.",
            "state": {"description": "A support ticket."},
            "actions": ["technical", "manual_review"],
            "policy": ["Technical problems go to technical support."],
        }
    )


def test_teacher_override_does_not_enable_paid_models() -> None:
    config = teacher_config_for(_task(), "openrouter:openrouter/free")

    assert config.provider == "openrouter"
    assert config.model == "openrouter/free"
    assert config.allow_paid is False


def test_dataset_build_help_exposes_paid_guard() -> None:
    result = CliRunner().invoke(app, ["dataset", "build", "--help"])

    assert result.exit_code == 0
    assert "--allow-paid" in result.output


def test_baseline_build_help_requires_dataset_path() -> None:
    result = CliRunner().invoke(app, ["baseline", "build", "--help"])

    assert result.exit_code == 0
    assert "DATASET_PATH" in result.output
