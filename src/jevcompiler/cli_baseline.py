from __future__ import annotations

import asyncio
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from jevcompiler.baseline import (
    BaselineCompileError,
    BaselineCompiler,
    BaselineEvaluator,
    write_baseline,
)
from jevcompiler.cli_common import teacher_config_for
from jevcompiler.dataset import DatasetBuildError, read_dataset
from jevcompiler.paths import artifact_directory
from jevcompiler.providers.teacher import TeacherError, resolve_teacher
from jevcompiler.providers.typesafe import TypeSafeError, TypeSafeProvider
from jevcompiler.specs import load_program, load_task
from jevcompiler.specs.common import SpecLoadError

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
console = Console()


class SplitName(StrEnum):
    train = "train"
    dev = "dev"
    test = "test"


async def _build_baseline(
    task_path: Path,
    dataset_path: Path,
    output: Path | None,
    teacher_override: str | None,
    allow_paid: bool,
) -> tuple[Path, str, str]:
    task = load_task(task_path)
    dataset = read_dataset(dataset_path)
    if dataset.manifest.task_name != task.name:
        raise BaselineCompileError(
            f"dataset task {dataset.manifest.task_name!r} does not match {task.name!r}"
        )
    config = teacher_config_for(task, teacher_override, allow_paid=allow_paid)
    teacher = await resolve_teacher(config)
    destination = output or artifact_directory(task.name, "baseline")
    try:
        artifact = await BaselineCompiler(teacher).compile(task, dataset)
        write_baseline(artifact, destination)
        return destination, teacher.provider, teacher.model
    finally:
        await teacher.aclose()


@app.command("build")
def build_baseline(
    task_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    dataset_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            readable=True,
            metavar="DATASET_PATH",
        ),
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    teacher: Annotated[
        str | None,
        typer.Option(help="Provider or provider:model override."),
    ] = None,
    allow_paid: Annotated[
        bool,
        typer.Option(help="Explicitly allow a non-free OpenRouter model."),
    ] = False,
) -> None:
    """Compile a constrained baseline from a task and training split."""
    try:
        destination, provider, model = asyncio.run(
            _build_baseline(task_path, dataset_path, output, teacher, allow_paid)
        )
    except (
        SpecLoadError,
        ValidationError,
        DatasetBuildError,
        TeacherError,
        BaselineCompileError,
    ) as exc:
        console.print(f"[red]Baseline build failed:[/red] {exc}")
        raise typer.Exit(1) from None
    console.print(f"Teacher: [green]{provider}[/green] {model}")
    console.print(f"Wrote baseline to [green]{destination}[/green]")


async def _evaluate_baseline(
    program_path: Path,
    dataset_path: Path,
    split: SplitName,
    concurrency: int,
):
    program = load_program(program_path)
    dataset = read_dataset(dataset_path)
    cases = getattr(dataset, split.value)
    async with TypeSafeProvider() as provider:
        return await BaselineEvaluator(provider, concurrency=concurrency).evaluate(program, cases)


@app.command("evaluate")
def evaluate_baseline(
    program_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    dataset_path: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    split: Annotated[SplitName, typer.Option()] = SplitName.dev,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    concurrency: Annotated[int, typer.Option(min=1, max=100)] = 10,
) -> None:
    """Evaluate a compiled program against one labeled split using TypeSafe Jev."""
    try:
        report = asyncio.run(
            _evaluate_baseline(program_path, dataset_path, split, concurrency)
        )
        destination = output or program_path.parent / f"metrics-{split.value}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    except (
        OSError,
        SpecLoadError,
        ValidationError,
        DatasetBuildError,
        TypeSafeError,
    ) as exc:
        console.print(f"[red]Evaluation failed:[/red] {exc}")
        raise typer.Exit(1) from None
    console.print(
        f"{split.value}: [green]{report.correct}/{report.total}[/green] correct "
        f"(accuracy={report.accuracy:.3f})"
    )
    console.print(f"Wrote metrics to {destination}")
