from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from jevcompiler.freeze import ArtifactError
from jevcompiler.showcase import ShowcaseError, run_showcase
from jevcompiler.specs.common import SpecLoadError

console = Console()


def showcase(
    source: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ] = Path("examples/expense-approval"),
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Frozen artifact destination."),
    ] = None,
) -> None:
    """Replay a committed example offline, then freeze and verify its artifact."""
    try:
        result, _ = asyncio.run(run_showcase(source, output=output))
    except (
        ArtifactError,
        OSError,
        SpecLoadError,
        ShowcaseError,
        ValidationError,
        ValueError,
    ) as exc:
        console.print(f"[red]Showcase failed:[/red] {exc}")
        raise typer.Exit(1) from None
    console.print_json(result.model_dump_json())
