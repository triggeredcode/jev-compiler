from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from jevcompiler.cli_common import teacher_config_for
from jevcompiler.dataset import DatasetBuilder, DatasetBuildError, write_dataset
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
    seed: int,
) -> tuple[Path, int, str, str]:
    task = load_task(task_path)
    config = teacher_config_for(task, teacher_override, allow_paid=allow_paid)
    teacher = await resolve_teacher(config)
    destination = output or Path("dist") / task.name / "dataset"
    try:
        bundle = await DatasetBuilder(teacher).build(
            task,
            normal=normal,
            boundary=boundary,
            edge=edge,
            counterfactual=counterfactual,
            seed=seed,
        )
        write_dataset(bundle, destination)
        return destination, len(bundle.all_cases), teacher.provider, teacher.model
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
                seed,
            )
        )
    except (SpecLoadError, ValidationError, TeacherError, DatasetBuildError) as exc:
        console.print(f"[red]Dataset build failed:[/red] {exc}")
        raise typer.Exit(1) from None

    location = "local machine" if provider in {"ollama", "lmstudio"} else provider
    console.print(f"Teacher: [green]{provider}[/green] {model} (data processed by {location})")
    console.print(f"Wrote [green]{count} cases[/green] to {destination}")
