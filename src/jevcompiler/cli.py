from __future__ import annotations

import asyncio
import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from jevcompiler.cli_baseline import app as baseline_app
from jevcompiler.cli_dataset import app as dataset_app
from jevcompiler.cli_optimize import app as optimize_app
from jevcompiler.providers.base import SystemOneResult
from jevcompiler.providers.discovery import discover_teacher_providers, select_teacher
from jevcompiler.providers.fake import RecordedSystemOneProvider
from jevcompiler.providers.typesafe import TypeSafeError, TypeSafeProvider
from jevcompiler.runtime import ProgramRuntime
from jevcompiler.specs import load_program, load_task
from jevcompiler.specs.common import SpecLoadError

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
app.add_typer(dataset_app, name="dataset", help="Build reproducible evaluation datasets.")
app.add_typer(baseline_app, name="baseline", help="Compile and evaluate baseline programs.")
app.add_typer(optimize_app, name="optimize", help="Optimize programs with cached evidence.")
console = Console()


class SpecKind(StrEnum):
    task = "task"
    program = "program"


@app.command()
def validate(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    kind: Annotated[SpecKind, typer.Option("--kind")],
) -> None:
    """Validate a TaskSpec or DecisionProgram YAML file."""
    try:
        document = load_task(path) if kind is SpecKind.task else load_program(path)
    except (SpecLoadError, ValidationError) as exc:
        console.print(f"[red]Invalid {kind.value}:[/red] {exc}")
        raise typer.Exit(1) from None
    console.print(
        f"[green]Valid {kind.value}[/green] name={document.name!r} version={document.version}"
    )


def _load_recorded_answers(path: Path) -> RecordedSystemOneProvider:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"unable to read recorded answers: {exc}") from None
    payloads = raw if isinstance(raw, list) else [raw]
    try:
        responses = [SystemOneResult.from_api(payload) for payload in payloads]
    except (TypeError, ValidationError) as exc:
        raise typer.BadParameter(f"invalid recorded answers: {exc}") from None
    return RecordedSystemOneProvider(responses)


async def _run_live(program_path: Path, state: object) -> object:
    program = load_program(program_path)
    async with TypeSafeProvider() as provider:
        return await ProgramRuntime(provider).run(program, state)


@app.command()
def run(
    program_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    state_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    answers: Annotated[
        Path | None,
        typer.Option("--answers", exists=True, dir_okay=False, readable=True),
    ] = None,
) -> None:
    """Execute a compiled decision program with live or recorded Jev answers."""
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        program = load_program(program_path)
        if answers is not None:
            provider = _load_recorded_answers(answers)
            result = asyncio.run(ProgramRuntime(provider).run(program, state))
        else:
            result = asyncio.run(_run_live(program_path, state))
    except (OSError, json.JSONDecodeError, SpecLoadError, ValidationError, TypeSafeError) as exc:
        console.print(f"[red]Run failed:[/red] {exc}")
        raise typer.Exit(1) from None
    console.print_json(result.model_dump_json())


@app.command()
def doctor(
    allow_paid: Annotated[bool, typer.Option(help="Allow selection of a paid fallback.")] = False,
    paid_model: Annotated[
        str | None, typer.Option(help="Paid OpenRouter model; requires --allow-paid.")
    ] = None,
) -> None:
    """Probe local/free teacher availability without making generation requests."""
    availability = asyncio.run(discover_teacher_providers())
    table = Table("Provider", "Available", "Models / reason")
    for item in availability:
        detail = ", ".join(item.models) or item.reason or "configured"
        table.add_row(item.provider, "yes" if item.available else "no", detail)
    console.print(table)
    try:
        provider, model = select_teacher(
            availability, allow_paid=allow_paid, paid_model=paid_model
        )
        console.print(f"Selected teacher: [green]{provider}[/green] {model or '(default model)'}")
    except RuntimeError as exc:
        console.print(f"[yellow]{exc}[/yellow]")


if __name__ == "__main__":
    app()
