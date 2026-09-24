from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from jevcompiler.baseline import (
    BaselineArtifact,
    BaselineCompileError,
    write_baseline,
)
from jevcompiler.cli_baseline import _build_baseline
from jevcompiler.cli_common import teacher_config_for
from jevcompiler.cli_dataset import _build_dataset
from jevcompiler.cli_optimize import SplitName, _run_optimization
from jevcompiler.dataset import DatasetBuildError, read_dataset, write_dataset
from jevcompiler.dataset.models import DatasetBundle
from jevcompiler.freeze import (
    ArtifactError,
    freeze_optimization,
    frozen_artifact_id,
    verify_artifact,
)
from jevcompiler.optimizer import (
    Optimizer,
    ProposalError,
    program_id,
    run_adaptive_round,
    write_failure_corpus,
    write_optimization,
)
from jevcompiler.optimizer.adaptive_loop import AdaptiveOptimizationRound
from jevcompiler.optimizer.models import OptimizationResult
from jevcompiler.paths import DEFAULT_CACHE_PATH, artifact_directory
from jevcompiler.providers.cache import (
    CacheError,
    CacheMode,
    CachingSystemOneProvider,
    JevCache,
)
from jevcompiler.providers.teacher import TeacherError, resolve_teacher
from jevcompiler.providers.typesafe import TypeSafeError, TypeSafeProvider
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
    semantic_variation: int
    thresholds: tuple[float, ...]
    semantic: bool
    max_live_calls: int
    max_candidates: int


BUDGETS = {
    BuildBudget.quick: BudgetSettings(4, 2, 1, 1, 0, (0.5, 0.65, 0.8), False, 50, 12),
    BuildBudget.standard: BudgetSettings(
        8,
        4,
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


def _optimization_matches(
    optimization: OptimizationResult,
    baseline: BaselineArtifact,
    dataset_path: Path,
) -> bool:
    dataset = read_dataset(dataset_path)
    return (
        optimization.baseline_candidate_id == program_id(baseline.program)
        and optimization.selection_digest == _split_digest(dataset_path, "dev")
        and (
            not dataset.test
            or (
                optimization.held_out is not None
                and optimization.held_out.digest == _split_digest(dataset_path, "test")
            )
        )
    )


async def _run_adaptive_build_round(
    *,
    task_path: Path,
    dataset: DatasetBundle,
    baseline: BaselineArtifact,
    optimization: OptimizationResult,
    settings: BudgetSettings,
    adaptive_cases: int,
    teacher_override: str | None,
    allow_paid: bool,
    concurrency: int,
) -> AdaptiveOptimizationRound:
    task = load_task(task_path)
    config = teacher_config_for(task, teacher_override, allow_paid=allow_paid)
    teacher = await resolve_teacher(config)
    remaining_live_calls = max(settings.max_live_calls - optimization.live_calls, 0)
    try:
        with JevCache(DEFAULT_CACHE_PATH) as cache:
            async with TypeSafeProvider() as live_provider:
                provider = CachingSystemOneProvider(
                    cache,
                    live_provider,
                    mode=CacheMode.read_write,
                    max_live_calls=remaining_live_calls,
                )
                adaptive = await run_adaptive_round(
                    task=task,
                    dataset=dataset,
                    baseline=baseline,
                    initial_result=optimization,
                    optimizer=Optimizer(provider, concurrency=concurrency),
                    teacher=teacher,
                    thresholds=settings.thresholds,
                    adaptive_cases=adaptive_cases,
                    seed=43,
                    max_candidates=settings.max_candidates,
                )
                stats = provider.stats
    finally:
        await teacher.aclose()

    cumulative = adaptive.result.model_copy(
        update={
            "cache_hits": optimization.cache_hits + stats.hits,
            "cache_misses": optimization.cache_misses + stats.misses,
            "live_calls": optimization.live_calls + stats.live_calls,
        }
    )
    return replace(adaptive, result=cumulative)


async def _build_all(
    task_path: Path,
    *,
    budget: BuildBudget,
    resume: bool,
    teacher_override: str | None,
    allow_paid: bool,
    concurrency: int,
    adaptive_cases: int,
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
            settings.semantic_variation,
            42,
        )
        dataset = read_dataset(dataset_dir)
        completed.append("dataset")

    baseline_dir = artifact_directory(task.name, "baseline")
    baseline_path = baseline_dir / "baseline.json"
    baseline: BaselineArtifact | None = None
    if resume and baseline_path.exists():
        baseline = BaselineArtifact.model_validate_json(baseline_path.read_text(encoding="utf-8"))
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
        baseline = BaselineArtifact.model_validate_json(baseline_path.read_text(encoding="utf-8"))
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
        if not _optimization_matches(optimization, baseline, dataset_dir):
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

    if adaptive_cases > 0:
        adaptive_dataset_dir = artifact_directory(task.name, "adaptive-dataset")
        adaptive_baseline_dir = artifact_directory(task.name, "adaptive-baseline")
        adaptive_optimization_dir = artifact_directory(task.name, "adaptive-optimization")
        adaptive_baseline_path = adaptive_baseline_dir / "baseline.json"
        adaptive_optimization_path = adaptive_optimization_dir / "optimization.json"
        adaptive_round_path = optimization_dir / "adaptive-round.json"
        resumed_adaptive = False
        if (
            resume
            and (adaptive_dataset_dir / "manifest.json").exists()
            and adaptive_baseline_path.exists()
            and adaptive_optimization_path.exists()
            and adaptive_round_path.exists()
        ):
            try:
                round_manifest = json.loads(adaptive_round_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                round_manifest = {}
            candidate_dataset = read_dataset(adaptive_dataset_dir)
            candidate_baseline = BaselineArtifact.model_validate_json(
                adaptive_baseline_path.read_text(encoding="utf-8")
            )
            candidate_optimization = OptimizationResult.model_validate_json(
                adaptive_optimization_path.read_text(encoding="utf-8")
            )
            if (
                round_manifest.get("source_corpus_hash") == dataset.manifest.corpus_hash
                and round_manifest.get("source_candidate_id") == optimization.selected_candidate_id
                and round_manifest.get("requested_cases") == adaptive_cases
                and round_manifest.get("adaptive_corpus_hash")
                == candidate_dataset.manifest.corpus_hash
                and candidate_baseline.provenance.training_corpus_hash
                == candidate_dataset.manifest.corpus_hash
                and _optimization_matches(
                    candidate_optimization,
                    candidate_baseline,
                    adaptive_dataset_dir,
                )
            ):
                dataset = candidate_dataset
                baseline = candidate_baseline
                optimization = candidate_optimization
                dataset_dir = adaptive_dataset_dir
                completed.append("adaptive round (resumed)")
                resumed_adaptive = True

        if not resumed_adaptive:
            adaptive = await _run_adaptive_build_round(
                task_path=task_path,
                dataset=dataset,
                baseline=baseline,
                optimization=optimization,
                settings=settings,
                adaptive_cases=adaptive_cases,
                teacher_override=teacher_override,
                allow_paid=allow_paid,
                concurrency=concurrency,
            )
            write_failure_corpus(
                adaptive.source_failures,
                optimization_dir / "training-failures",
            )
            round_manifest = {
                "version": 1,
                "adapted": adaptive.adapted,
                "stop_reason": adaptive.stop_reason,
                "source_candidate_id": adaptive.source_candidate_id,
                "source_corpus_hash": dataset.manifest.corpus_hash,
                "adaptive_corpus_hash": adaptive.dataset.manifest.corpus_hash,
                "requested_cases": adaptive_cases,
                "added_case_ids": list(adaptive.added_case_ids),
                "source_failure_count": adaptive.source_failures.total_failures,
            }
            optimization_dir.mkdir(parents=True, exist_ok=True)
            (optimization_dir / "adaptive-round.json").write_text(
                json.dumps(round_manifest, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            if adaptive.adapted:
                write_dataset(adaptive.dataset, adaptive_dataset_dir)
                write_baseline(adaptive.baseline, adaptive_baseline_dir)
                write_optimization(adaptive.result, adaptive_optimization_dir)
                dataset = adaptive.dataset
                baseline = adaptive.baseline
                optimization = adaptive.result
                dataset_dir = adaptive_dataset_dir
            completed.append(f"adaptive round ({adaptive.stop_reason})")

    frozen_dir = artifact_directory(task.name, "frozen") / frozen_artifact_id(optimization)
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
    adaptive_cases: Annotated[
        int,
        typer.Option(
            min=0,
            help="Run one train-only adaptive round with this many new cases.",
        ),
    ] = 0,
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
                adaptive_cases=adaptive_cases,
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
