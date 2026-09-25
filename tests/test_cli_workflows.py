import re

from typer.testing import CliRunner

from jevcompiler.cli import app
from jevcompiler.cli_build import (
    BUDGETS,
    BuildBudget,
    _dataset_matches_build_settings,
)
from jevcompiler.cli_common import teacher_config_for
from jevcompiler.cli_optimize import parse_thresholds
from jevcompiler.dataset.models import DatasetBundle, DatasetManifest
from jevcompiler.specs.task import TaskSpec

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _help(*command: str) -> str:
    result = CliRunner().invoke(app, [*command, "--help"])
    assert result.exit_code == 0
    return _ANSI_ESCAPE.sub("", result.output)


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
    assert "--allow-paid" in _help("dataset", "build")


def test_dataset_adapt_help_requires_failure_evidence_and_paid_guard() -> None:
    output = _help("dataset", "adapt")

    assert "failures_path" in output
    assert "--allow-paid" in output


def test_baseline_build_help_requires_dataset_path() -> None:
    assert "DATASET_PATH" in _help("baseline", "build")


def test_optimize_help_exposes_cache_and_semantic_controls() -> None:
    output = _help("optimize", "run")

    assert "--cache-mode" in output
    assert "--semantic" in output
    assert "--allow-paid" in output


def test_threshold_parser_deduplicates_and_validates() -> None:
    assert parse_thresholds("0.7,0.5,0.7") == [0.5, 0.7]


def test_artifact_commands_are_exposed() -> None:
    freeze_help = _help("artifact", "freeze")
    _help("artifact", "verify")

    assert "OPTIMIZATION_PATH" in freeze_help.upper()


def test_build_command_exposes_budgets_and_resume() -> None:
    output = _help("build")

    assert "quick" in output
    assert "--resume" in output
    assert "--adaptive-cases" in output
    assert BUDGETS[BuildBudget.quick].semantic is False
    assert BUDGETS[BuildBudget.standard].semantic is True
    assert BUDGETS[BuildBudget.quick].max_live_calls < BUDGETS[BuildBudget.deep].max_live_calls
    assert BUDGETS[BuildBudget.quick].max_candidates < BUDGETS[BuildBudget.deep].max_candidates


def test_build_resume_requires_matching_semantic_variation_budget() -> None:
    dataset = DatasetBundle.model_construct(
        manifest=DatasetManifest.model_construct(
            bucket_counts={"semantic_variation": 4},
        )
    )

    assert _dataset_matches_build_settings(dataset, BUDGETS[BuildBudget.standard])
    assert not _dataset_matches_build_settings(dataset, BUDGETS[BuildBudget.quick])
