from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from jevcompiler.cli_common import teacher_config_for
from jevcompiler.dataset import (
    DatasetBuilder,
    DatasetBuildError,
    read_dataset,
    write_dataset,
)
from jevcompiler.optimizer.adaptive import AdaptiveDatasetBuilder
from jevcompiler.optimizer.models import FailureCorpus
from jevcompiler.paths import artifact_directory
from jevcompiler.providers.teacher import TeacherError, resolve_teacher
from jevcompiler.specs import load_task
from jevcompiler.specs.common import SpecLoadError

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
console = Console()


async def _build_dataset(
    task_path: Path,
    output: Path | None,
    teacher_override: str | None,
    allow_paid: bool,
    normal: int,
    boundary: int,
    edge: int,
    counterfactual: int,
    semantic_variation: int,
    seed: int,
) -> tuple[Path, int, str, str]:
    task = load_task(task_path)
    config = teacher_config_for(task, teacher_override, allow_paid=allow_paid)
    teacher = await resolve_teacher(config)
    destination = output or artifact_directory(task.name, "dataset")
    try:
        bundle = await DatasetBuilder(teacher).build(
            task,
            normal=normal,
            boundary=boundary,
            edge=edge,
            counterfactual=counterfactual,
            semantic_variation=semantic_variation,
            seed=seed,
        )
        write_dataset(bundle, destination)
        return destination, len(bundle.all_cases), teacher.provider, teacher.model
    finally:
        await teacher.aclose()


async def _adapt_dataset(
    task_path: Path,
    dataset_path: Path,
    failures_path: Path,
    output: Path | None,
    teacher_override: str | None,
    allow_paid: bool,
    count: int,
    seed: int,
) -> tuple[Path, int, str, str]:
    task = load_task(task_path)
    dataset = read_dataset(dataset_path)
    failures = FailureCorpus.model_validate_json(failures_path.read_text(encoding="utf-8"))
    config = teacher_config_for(task, teacher_override, allow_paid=allow_paid)
    teacher = await resolve_teacher(config)
    destination = output or artifact_directory(task.name, "adaptive-dataset")
    try:
        result = await AdaptiveDatasetBuilder(teacher).extend(
            task,
            dataset,
            failures,
            count=count,
            seed=seed,
        )
        write_dataset(result.bundle, destination)
        return destination, len(result.added_case_ids), teacher.provider, teacher.model
    finally:
        await teacher.aclose()


@app.command("build")
def build_dataset(
    task_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    teacher: Annotated[
        str | None,
        typer.Option(help="Provider or provider:model override."),
    ] = None,
    allow_paid: Annotated[
        bool,
        typer.Option(help="Explicitly allow a non-free OpenRouter model."),
    ] = False,
    normal: Annotated[int, typer.Option(min=0)] = 8,
    boundary: Annotated[int, typer.Option(min=0)] = 4,
    edge: Annotated[int, typer.Option(min=0)] = 4,
    counterfactual: Annotated[int, typer.Option(min=0)] = 4,
    semantic_variation: Annotated[
        int,
        typer.Option(
            help="Number of semantics-preserving parent/variant pairs to generate.",
            min=0,
        ),
    ] = 0,
    seed: Annotated[int, typer.Option()] = 42,
) -> None:
    """Generate, label, validate, and deterministically split a dataset."""
    try:
        destination, count, provider, model = asyncio.run(
            _build_dataset(
                task_path,
                output,
                teacher,
                allow_paid,
                normal,
                boundary,
                edge,
                counterfactual,
                semantic_variation,
                seed,
            )
        )
    except (SpecLoadError, ValidationError, TeacherError, DatasetBuildError) as exc:
        console.print(f"[red]Dataset build failed:[/red] {exc}")
        raise typer.Exit(1) from None

    location = "local machine" if provider in {"ollama", "lmstudio"} else provider
    console.print(f"Teacher: [green]{provider}[/green] {model} (data processed by {location})")
    console.print(f"Wrote [green]{count} cases[/green] to {destination}")


@app.command("adapt")
def adapt_dataset(
    task_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    dataset_path: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    failures_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    teacher: Annotated[
        str | None,
        typer.Option(help="Provider or provider:model override."),
    ] = None,
    allow_paid: Annotated[
        bool,
        typer.Option(help="Explicitly allow a non-free OpenRouter model."),
    ] = False,
    count: Annotated[int, typer.Option(min=1)] = 4,
    seed: Annotated[int, typer.Option()] = 42,
) -> None:
    """Append failure-directed cases to train while preserving held-out splits."""
    try:
        destination, added, provider, model = asyncio.run(
            _adapt_dataset(
                task_path,
                dataset_path,
                failures_path,
                output,
                teacher,
                allow_paid,
                count,
                seed,
            )
        )
    except (
        OSError,
        SpecLoadError,
        ValidationError,
        TeacherError,
        DatasetBuildError,
    ) as exc:
        console.print(f"[red]Dataset adaptation failed:[/red] {exc}")
        raise typer.Exit(1) from None

    location = "local machine" if provider in {"ollama", "lmstudio"} else provider
    console.print(f"Teacher: [green]{provider}[/green] {model} (data processed by {location})")
    console.print(f"Added [green]{added} training cases[/green] in {destination}")
