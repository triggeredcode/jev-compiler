from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from jevcompiler.dataset import DatasetBuildError, read_dataset
from jevcompiler.freeze import ArtifactError, freeze_optimization, verify_artifact
from jevcompiler.optimizer.models import OptimizationResult
from jevcompiler.paths import artifact_directory

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
console = Console()


@app.command("freeze")
def freeze_artifact(
    optimization_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    dataset_path: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Freeze a selected optimization result into an immutable artifact."""
    try:
        result = OptimizationResult.model_validate_json(
            optimization_path.read_text(encoding="utf-8")
        )
        dataset = read_dataset(dataset_path)
        selected = next(
            candidate
            for candidate in result.candidates
            if candidate.candidate_id == result.selected_candidate_id
        )
        destination = output or (
            artifact_directory(selected.program.name, "frozen")
            / result.selected_candidate_id
        )
        manifest = freeze_optimization(result, dataset, destination)
    except (
        OSError,
        StopIteration,
        ValueError,
        ValidationError,
        DatasetBuildError,
        ArtifactError,
    ) as exc:
        console.print(f"[red]Artifact freeze failed:[/red] {exc}")
        raise typer.Exit(1) from None
    console.print(
        f"Frozen [green]{manifest.selected_candidate_id}[/green] to {destination}"
    )


@app.command("verify")
def verify_frozen_artifact(
    artifact_path: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
) -> None:
    """Verify every payload hash and the canonical program digest."""
    try:
        manifest = verify_artifact(artifact_path)
    except ArtifactError as exc:
        console.print(f"[red]Artifact verification failed:[/red] {exc}")
        raise typer.Exit(1) from None
    console.print(
        f"[green]Verified[/green] {manifest.task_name} "
        f"candidate={manifest.selected_candidate_id} files={len(manifest.files)}"
    )
