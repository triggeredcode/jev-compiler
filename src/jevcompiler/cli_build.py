from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from jevcompiler.baseline import BaselineArtifact, BaselineCompileError
from jevcompiler.cli_baseline import _build_baseline
from jevcompiler.cli_dataset import _build_dataset
from jevcompiler.cli_optimize import SplitName, _run_optimization
from jevcompiler.dataset import DatasetBuildError, read_dataset
from jevcompiler.freeze import (
    ArtifactError,
    freeze_optimization,
    frozen_artifact_id,
    verify_artifact,
)
from jevcompiler.optimizer import ProposalError, program_id
from jevcompiler.optimizer.models import OptimizationResult
from jevcompiler.paths import DEFAULT_CACHE_PATH, artifact_directory
from jevcompiler.providers.cache import CacheError, CacheMode
from jevcompiler.providers.teacher import TeacherError
from jevcompiler.providers.typesafe import TypeSafeError
from jevcompiler.runs import content_digest
from jevcompiler.specs import load_task
from jevcompiler.specs.common import SpecLoadError

console = Console()


class BuildBudget(StrEnum):
    quick = "quick"
    standard = "standard"
    deep = "deep"


@dataclass(frozen=True, slots=True)
class BudgetSettings:
    normal: int
    boundary: int
    edge: int
    counterfactual: int
    thresholds: tuple[float, ...]
    semantic: bool
    max_live_calls: int
    max_candidates: int


BUDGETS = {
    BuildBudget.quick: BudgetSettings(4, 2, 1, 1, (0.5, 0.65, 0.8), False, 50, 12),
    BuildBudget.standard: BudgetSettings(
        8,
        4,
        4,
        4,
        (0.5, 0.6, 0.7, 0.8, 0.9),
        True,
        250,
        40,
    ),
    BuildBudget.deep: BudgetSettings(
        20,
        10,
        10,
        10,
        (0.4, 0.5, 0.6, 0.7, 0.8, 0.9),
        True,
        1000,
        100,
    ),
}


def _split_digest(dataset_path: Path, split: str) -> str:
    dataset = read_dataset(dataset_path)
    cases = getattr(dataset, split)
    return content_digest([case.model_dump(mode="json") for case in cases])


async def _build_all(
    task_path: Path,
    *,
    budget: BuildBudget,
    resume: bool,
    teacher_override: str | None,
    allow_paid: bool,
    concurrency: int,
) -> tuple[Path, list[str]]:
    task = load_task(task_path)
    settings = BUDGETS[budget]
    completed: list[str] = []

    dataset_dir = artifact_directory(task.name, "dataset")
    if resume and (dataset_dir / "manifest.json").exists():
        dataset = read_dataset(dataset_dir)
        completed.append("dataset (resumed)")
    else:
        await _build_dataset(
            task_path,
            dataset_dir,
            teacher_override,
            allow_paid,
            settings.normal,
            settings.boundary,
            settings.edge,
            settings.counterfactual,
            42,
        )
        dataset = read_dataset(dataset_dir)
        completed.append("dataset")

    baseline_dir = artifact_directory(task.name, "baseline")
    baseline_path = baseline_dir / "baseline.json"
    baseline: BaselineArtifact | None = None
    if resume and baseline_path.exists():
        baseline = BaselineArtifact.model_validate_json(
            baseline_path.read_text(encoding="utf-8")
        )
        if baseline.provenance.training_corpus_hash != dataset.manifest.corpus_hash:
            baseline = None
    if baseline is None:
        await _build_baseline(
            task_path,
            dataset_dir,
            baseline_dir,
            teacher_override,
            allow_paid,
        )
        baseline = BaselineArtifact.model_validate_json(
            baseline_path.read_text(encoding="utf-8")
        )
        completed.append("baseline")
    else:
        completed.append("baseline (resumed)")

    optimization_dir = artifact_directory(task.name, "optimization")
    optimization_path = optimization_dir / "optimization.json"
    optimization: OptimizationResult | None = None
    if resume and optimization_path.exists():
        optimization = OptimizationResult.model_validate_json(
            optimization_path.read_text(encoding="utf-8")
        )
        if (
            optimization.baseline_candidate_id != program_id(baseline.program)
            or optimization.selection_digest != _split_digest(dataset_dir, "dev")
            or (
                bool(dataset.test)
                and (
                    optimization.held_out is None
                    or optimization.held_out.digest != _split_digest(dataset_dir, "test")
                )
            )
        ):
            optimization = None
    if optimization is None:
        optimization, _ = await _run_optimization(
            program_path=baseline_dir / "program.yaml",
            dataset_path=dataset_dir,
            output=optimization_dir,
            split=SplitName.dev,
            cache_path=DEFAULT_CACHE_PATH,
            cache_mode=CacheMode.read_write,
            thresholds=list(settings.thresholds),
            concurrency=concurrency,
            semantic=settings.semantic,
            task_path=task_path,
            teacher_override=teacher_override,
            allow_paid=allow_paid,
            max_live_calls=settings.max_live_calls,
            max_candidates=settings.max_candidates,
        )
        completed.append("optimization")
    else:
        completed.append("optimization (resumed)")

    frozen_dir = (
        artifact_directory(task.name, "frozen")
        / frozen_artifact_id(optimization)
    )
    if (frozen_dir / "manifest.json").exists():
        manifest = verify_artifact(frozen_dir)
        if manifest.corpus_hash != dataset.manifest.corpus_hash:
            raise ArtifactError("existing frozen artifact uses a different corpus")
        if manifest.selected_candidate_id != optimization.selected_candidate_id:
            raise ArtifactError("existing frozen artifact uses a different candidate")
        completed.append("artifact (verified existing)")
    else:
        freeze_optimization(optimization, dataset, frozen_dir)
        completed.append("artifact")
    return frozen_dir, completed


def build_project(
    task_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    budget: Annotated[BuildBudget, typer.Option()] = BuildBudget.quick,
    resume: Annotated[bool, typer.Option(help="Reuse validated phase outputs.")] = True,
    teacher: Annotated[
        str | None,
        typer.Option(help="Provider or provider:model override."),
    ] = None,
    allow_paid: Annotated[
        bool,
        typer.Option(help="Explicitly allow a non-free teacher model."),
    ] = False,
    concurrency: Annotated[int, typer.Option(min=1, max=100)] = 10,
) -> None:
    """Run dataset, baseline, optimization, and artifact phases in order."""
    try:
        artifact, completed = asyncio.run(
            _build_all(
                task_path,
                budget=budget,
                resume=resume,
                teacher_override=teacher,
                allow_paid=allow_paid,
                concurrency=concurrency,
            )
        )
    except (
        OSError,
        ValueError,
        SpecLoadError,
        ValidationError,
        DatasetBuildError,
        BaselineCompileError,
        CacheError,
        TypeSafeError,
        TeacherError,
        ProposalError,
        ArtifactError,
    ) as exc:
        console.print(f"[red]Build failed:[/red] {exc}")
        raise typer.Exit(1) from None
    console.print(f"Completed: {', '.join(completed)}")
    console.print(f"Frozen artifact: [green]{artifact}[/green]")
