"""Freeze and verify immutable, optimizer-free deployment artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import yaml

from jevcompiler import __version__
from jevcompiler.dataset.models import DatasetBundle
from jevcompiler.freeze.models import FrozenManifest
from jevcompiler.freeze.report import render_report
from jevcompiler.optimizer.models import OptimizationResult
from jevcompiler.runs import content_digest


class ArtifactError(RuntimeError):
    """A frozen artifact is incomplete, mutable, or fails integrity checks."""


_RUNTIME_SOURCE = '''"""Minimal runtime entrypoint for a frozen Jev decision program."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jevcompiler.providers.base import SystemOneProvider
from jevcompiler.runtime import DecisionResult, ProgramRuntime
from jevcompiler.specs import load_program


async def decide(state: Any, provider: SystemOneProvider) -> DecisionResult:
    program = load_program(Path(__file__).with_name("program.yaml"))
    return await ProgramRuntime(provider).run(program, state)
'''


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def freeze_optimization(
    result: OptimizationResult,
    dataset: DatasetBundle,
    output: Path,
) -> FrozenManifest:
    if output.exists():
        raise ArtifactError(f"refusing to overwrite frozen artifact: {output}")
    selected = next(
        (
            candidate
            for candidate in result.candidates
            if candidate.candidate_id == result.selected_candidate_id
        ),
        None,
    )
    if selected is None or selected.metrics is None or selected.evaluation is None:
        raise ArtifactError("selected candidate is missing its program or measurements")
    if dataset.manifest.task_name != selected.program.name:
        raise ArtifactError("dataset and selected program names do not match")

    output.mkdir(parents=True)
    program_data = selected.program.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    (output / "program.yaml").write_text(
        yaml.safe_dump(program_data, sort_keys=False),
        encoding="utf-8",
    )
    _write_json(output / "metrics.json", selected.evaluation.model_dump(mode="json"))
    _write_json(
        output / "lineage.json",
        [
            candidate.model_dump(
                mode="json",
                exclude={"program", "evaluation"},
            )
            for candidate in result.candidates
        ],
    )
    _write_json(
        output / "provenance.json",
        {
            "selected_candidate_id": selected.candidate_id,
            "parent_id": selected.parent_id,
            "mutation_type": selected.mutation_type,
            "hypothesis": selected.hypothesis,
            "semantic_diff": selected.semantic_diff,
            "pareto_frontier": result.pareto_frontier,
            "cache": {
                "hits": result.cache_hits,
                "misses": result.cache_misses,
                "live_calls": result.live_calls,
            },
        },
    )
    _write_json(output / "dataset-manifest.json", dataset.manifest.model_dump(mode="json"))
    (output / "runtime.py").write_text(_RUNTIME_SOURCE, encoding="utf-8")
    (output / "report.html").write_text(render_report(result), encoding="utf-8")

    payload_files = sorted(path for path in output.iterdir() if path.is_file())
    file_hashes = {path.name: _sha256(path) for path in payload_files}
    metrics = selected.metrics.model_dump(mode="json")
    manifest = FrozenManifest(
        task_name=selected.program.name,
        created_at=datetime.now(UTC),
        compiler_version=__version__,
        selected_candidate_id=selected.candidate_id,
        program_digest=content_digest(program_data),
        corpus_hash=dataset.manifest.corpus_hash,
        jev_model=selected.program.jev_model,
        actions=selected.program.actions,
        selection_metrics={
            "accuracy": metrics["accuracy"],
            "macro_f1": metrics["macro_f1"],
            "jev_calls": metrics["jev_calls"],
            "question_tokens": metrics["question_tokens"],
            "graph_complexity": metrics["graph_complexity"],
        },
        files=file_hashes,
    )
    (output / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def verify_artifact(root: Path) -> FrozenManifest:
    try:
        manifest = FrozenManifest.model_validate_json(
            (root / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise ArtifactError(f"unable to read frozen manifest: {exc}") from None

    for relative, expected in manifest.files.items():
        safe_path = PurePosixPath(relative)
        if safe_path.is_absolute() or ".." in safe_path.parts:
            raise ArtifactError(f"unsafe manifest path: {relative}")
        path = root / safe_path
        if not path.is_file():
            raise ArtifactError(f"artifact file is missing: {relative}")
        actual = _sha256(path)
        if actual != expected:
            raise ArtifactError(f"artifact hash mismatch: {relative}")

    try:
        program_data = yaml.safe_load((root / "program.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ArtifactError(f"unable to validate frozen program: {exc}") from None
    if content_digest(program_data) != manifest.program_digest:
        raise ArtifactError("frozen program digest does not match the manifest")
    return manifest
