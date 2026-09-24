from typer.testing import CliRunner

from jevcompiler.cli import app
from jevcompiler.cli_build import BUDGETS, BuildBudget
from jevcompiler.cli_common import teacher_config_for
from jevcompiler.cli_optimize import parse_thresholds
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


def test_dataset_adapt_help_requires_failure_evidence_and_paid_guard() -> None:
    result = CliRunner().invoke(app, ["dataset", "adapt", "--help"])

    assert result.exit_code == 0
    assert "failures_path" in result.output
    assert "--allow-paid" in result.output


def test_baseline_build_help_requires_dataset_path() -> None:
    result = CliRunner().invoke(app, ["baseline", "build", "--help"])

    assert result.exit_code == 0
    assert "DATASET_PATH" in result.output


def test_optimize_help_exposes_cache_and_semantic_controls() -> None:
    result = CliRunner().invoke(app, ["optimize", "run", "--help"])

    assert result.exit_code == 0
    assert "--cache-mode" in result.output
    assert "--semantic" in result.output
    assert "--allow-paid" in result.output


def test_threshold_parser_deduplicates_and_validates() -> None:
    assert parse_thresholds("0.7,0.5,0.7") == [0.5, 0.7]


def test_artifact_commands_are_exposed() -> None:
    freeze_help = CliRunner().invoke(app, ["artifact", "freeze", "--help"])
    verify_help = CliRunner().invoke(app, ["artifact", "verify", "--help"])

    assert freeze_help.exit_code == 0
    assert verify_help.exit_code == 0
    assert "OPTIMIZATION_PATH" in freeze_help.output.upper()


def test_build_command_exposes_budgets_and_resume() -> None:
    result = CliRunner().invoke(app, ["build", "--help"])

    assert result.exit_code == 0
    assert "quick" in result.output
    assert "--resume" in result.output
    assert BUDGETS[BuildBudget.quick].semantic is False
    assert BUDGETS[BuildBudget.standard].semantic is True
    assert BUDGETS[BuildBudget.quick].max_live_calls < BUDGETS[BuildBudget.deep].max_live_calls
    assert BUDGETS[BuildBudget.quick].max_candidates < BUDGETS[BuildBudget.deep].max_candidates
