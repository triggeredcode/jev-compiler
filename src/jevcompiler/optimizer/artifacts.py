"""Write inspectable optimization artifacts without runtime secrets."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from jevcompiler.optimizer.failures import write_failure_corpus
from jevcompiler.optimizer.models import OptimizationResult


def write_optimization(result: OptimizationResult, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    selected = next(
        candidate
        for candidate in result.candidates
        if candidate.candidate_id == result.selected_candidate_id
    )
    (output / "optimization.json").write_text(
        result.model_dump_json(indent=2, by_alias=True),
        encoding="utf-8",
    )
    lineage = [
        candidate.model_dump(
            mode="json",
            exclude={"program", "evaluation"},
        )
        for candidate in result.candidates
    ]
    (output / "lineage.json").write_text(
        json.dumps(lineage, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    program_data = selected.program.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    (output / "selected-program.yaml").write_text(
        yaml.safe_dump(program_data, sort_keys=False),
        encoding="utf-8",
    )
    if selected.evaluation is not None:
        (output / "selected-metrics.json").write_text(
            selected.evaluation.model_dump_json(indent=2),
            encoding="utf-8",
        )
    if result.held_out is not None:
        (output / "held-out.json").write_text(
            result.held_out.model_dump_json(indent=2),
            encoding="utf-8",
        )
    write_failure_corpus(result.baseline_failures, output / "baseline-failures")
    write_failure_corpus(result.selected_failures, output / "selected-failures")
