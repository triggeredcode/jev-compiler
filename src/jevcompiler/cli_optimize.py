from __future__ import annotations

import asyncio
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from jevcompiler.cli_common import teacher_config_for
from jevcompiler.dataset import DatasetBuildError, read_dataset
from jevcompiler.optimizer import Optimizer, ProposalError, propose_question_rewrites
from jevcompiler.optimizer.artifacts import write_optimization
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
from jevcompiler.specs import load_program, load_task
from jevcompiler.specs.common import SpecLoadError

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
console = Console()


class SplitName(StrEnum):
    train = "train"
    dev = "dev"


def parse_thresholds(value: str) -> list[float]:
    try:
        thresholds = sorted({float(item.strip()) for item in value.split(",") if item.strip()})
    except ValueError:
        raise ValueError("thresholds must be comma-separated numbers") from None
    if not thresholds or any(threshold < 0 or threshold > 1 for threshold in thresholds):
        raise ValueError("thresholds must contain values between 0 and 1")
    return thresholds


async def _optimize_with_provider(
    provider: CachingSystemOneProvider,
    *,
    program_path: Path,
    dataset_path: Path,
    split: SplitName,
    thresholds: list[float],
    concurrency: int,
    semantic: bool,
    task_path: Path | None,
    teacher_override: str | None,
    allow_paid: bool,
) -> OptimizationResult:
    program = load_program(program_path)
    dataset = read_dataset(dataset_path)
    if dataset.manifest.task_name != program.name:
        raise ValueError(
            f"dataset task {dataset.manifest.task_name!r} does not match program {program.name!r}"
        )
    cases = getattr(dataset, split.value)
    optimizer = Optimizer(provider, concurrency=concurrency)
    result = await optimizer.optimize(program, cases, thresholds=thresholds)
    if not semantic:
        return result
    if task_path is None:
        raise ValueError("--semantic requires --task")

    task = load_task(task_path)
    if task.name != program.name:
        raise ValueError(f"task {task.name!r} does not match program {program.name!r}")
    config = teacher_config_for(task, teacher_override, allow_paid=allow_paid)
    teacher = await resolve_teacher(config)
    try:
        proposals = await propose_question_rewrites(
            teacher,
            program,
            result.baseline_failures,
        )
    finally:
        await teacher.aclose()
    return await optimizer.optimize(
        program,
        cases,
        thresholds=thresholds,
        mutations=proposals,
    )


async def _run_optimization(
    *,
    program_path: Path,
    dataset_path: Path,
    output: Path | None,
    split: SplitName,
    cache_path: Path,
    cache_mode: CacheMode,
    thresholds: list[float],
    concurrency: int,
    semantic: bool,
    task_path: Path | None,
    teacher_override: str | None,
    allow_paid: bool,
) -> tuple[OptimizationResult, Path]:
    program = load_program(program_path)
    destination = output or artifact_directory(program.name, "optimization")
    with JevCache(cache_path) as cache:
        if cache_mode is CacheMode.replay_only:
            provider = CachingSystemOneProvider(cache, mode=cache_mode)
            result = await _optimize_with_provider(
                provider,
                program_path=program_path,
                dataset_path=dataset_path,
                split=split,
                thresholds=thresholds,
                concurrency=concurrency,
                semantic=semantic,
                task_path=task_path,
                teacher_override=teacher_override,
                allow_paid=allow_paid,
            )
        else:
            async with TypeSafeProvider() as live_provider:
                provider = CachingSystemOneProvider(
                    cache,
                    live_provider,
                    mode=cache_mode,
                )
                result = await _optimize_with_provider(
                    provider,
                    program_path=program_path,
                    dataset_path=dataset_path,
                    split=split,
                    thresholds=thresholds,
                    concurrency=concurrency,
                    semantic=semantic,
                    task_path=task_path,
                    teacher_override=teacher_override,
                    allow_paid=allow_paid,
                )
    write_optimization(result, destination)
    return result, destination


@app.command("run")
def optimize_run(
    program_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    dataset_path: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    split: Annotated[SplitName, typer.Option()] = SplitName.dev,
    cache_path: Annotated[Path, typer.Option()] = DEFAULT_CACHE_PATH,
    cache_mode: Annotated[CacheMode, typer.Option()] = CacheMode.read_write,
    thresholds: Annotated[str, typer.Option()] = "0.5,0.6,0.7,0.8,0.9",
    concurrency: Annotated[int, typer.Option(min=1, max=100)] = 10,
    semantic: Annotated[bool, typer.Option(help="Ask a teacher for bounded rewrites.")] = False,
    task: Annotated[
        Path | None,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = None,
    teacher: Annotated[
        str | None,
        typer.Option(help="Provider or provider:model for semantic rewrites."),
    ] = None,
    allow_paid: Annotated[
        bool,
        typer.Option(help="Explicitly allow a non-free rewrite teacher."),
    ] = False,
) -> None:
    """Optimize thresholds on one selection split while preserving complete lineage."""
    try:
        parsed_thresholds = parse_thresholds(thresholds)
        result, destination = asyncio.run(
            _run_optimization(
                program_path=program_path,
                dataset_path=dataset_path,
                output=output,
                split=split,
                cache_path=cache_path,
                cache_mode=cache_mode,
                thresholds=parsed_thresholds,
                concurrency=concurrency,
                semantic=semantic,
                task_path=task,
                teacher_override=teacher,
                allow_paid=allow_paid,
            )
        )
    except (
        OSError,
        ValueError,
        SpecLoadError,
        ValidationError,
        DatasetBuildError,
        CacheError,
        TypeSafeError,
        TeacherError,
        ProposalError,
    ) as exc:
        console.print(f"[red]Optimization failed:[/red] {exc}")
        raise typer.Exit(1) from None

    selected = next(
        candidate
        for candidate in result.candidates
        if candidate.candidate_id == result.selected_candidate_id
    )
    assert selected.metrics is not None
    console.print(
        f"Selected [green]{selected.candidate_id}[/green] "
        f"accuracy={selected.metrics.accuracy:.3f} "
        f"from {len(result.candidates)} candidates"
    )
    console.print(
        f"Cache: {result.cache_hits} hits, {result.cache_misses} misses, "
        f"{result.live_calls} live calls"
    )
    console.print(f"Wrote optimization artifacts to {destination}")
