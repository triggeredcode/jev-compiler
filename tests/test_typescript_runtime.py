import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from jevcompiler.providers.base import SystemOneResult
from jevcompiler.providers.fake import RecordedSystemOneProvider
from jevcompiler.runtime import ProgramRuntime
from jevcompiler.specs.program import DecisionProgram

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "runtime_parity.json"
RUNNER = ROOT / "tests" / "typescript" / "run-runtime-parity.mjs"
TYPESCRIPT_RUNTIME = ROOT / "src" / "jevcompiler" / "freeze" / "runtime.ts"


def _node_22() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    version = subprocess.run(
        [node, "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if int(version.removeprefix("v").split(".", 1)[0]) < 22:
        pytest.skip("Node.js 22+ is required for dependency-free TypeScript execution")
    return node


def _normalized(result: Any) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    for event in payload["trace"]:
        event.pop("started_at")
    return payload


def _python_results(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for test_case in fixture["cases"]:
        responses = [SystemOneResult.from_api(item) for item in test_case["responses"]]
        if not responses:
            responses = [SystemOneResult(model="unused", answers={})]
        runtime = ProgramRuntime(RecordedSystemOneProvider(responses))
        try:
            result = asyncio.run(
                runtime.run(
                    DecisionProgram.model_validate(test_case["program"]),
                    test_case["state"],
                )
            )
        except RuntimeError as exc:
            results.append({"name": test_case["name"], "error": str(exc)})
        else:
            results.append({"name": test_case["name"], "result": _normalized(result)})
    return results


def test_typescript_runtime_matches_python_fixtures() -> None:
    node = _node_22()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    completed = subprocess.run(
        [
            node,
            "--no-warnings",
            "--experimental-strip-types",
            str(RUNNER),
            str(FIXTURE),
            str(TYPESCRIPT_RUNTIME),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    typescript_results = json.loads(completed.stdout)
    python_results = _python_results(fixture)

    assert typescript_results == python_results
    assert typescript_results[0]["result"]["action"] == "billing"
    assert typescript_results[0]["result"]["trace"][1]["output"] == {"skipped": True}
    assert typescript_results[1]["result"]["action"] == "accept"
    assert typescript_results[2]["error"] == "cycle detected at stage again"
