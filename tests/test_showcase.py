import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from jevcompiler.cli import app
from jevcompiler.freeze import verify_artifact

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "expense-approval"
runner = CliRunner()


def test_showcase_replays_freezes_and_verifies_without_credentials(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    artifact = tmp_path / "expense-artifact"

    completed = runner.invoke(
        app,
        ["showcase", str(EXAMPLE), "--output", str(artifact)],
    )

    assert completed.exit_code == 0, completed.output
    payload = json.loads(completed.output)
    assert payload["action"] == payload["expected_action"] == "approve"
    assert payload["live_calls"] == 0
    assert payload["verified"] is True
    assert payload["artifact_files"] == 10
    manifest = verify_artifact(artifact)
    assert manifest.task_name == "expense-approval"
    assert manifest.selected_candidate_id == payload["candidate_id"]
    assert manifest.held_out_metrics is not None


def test_showcase_rejects_a_replay_that_disagrees_with_its_expectation(tmp_path) -> None:
    source = tmp_path / "mismatch"
    shutil.copytree(EXAMPLE, source)
    spec_path = source / "showcase.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["expected_action"] = "manual_review"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    artifact = tmp_path / "artifact"

    completed = runner.invoke(
        app,
        ["showcase", str(source), "--output", str(artifact)],
    )

    assert completed.exit_code == 1
    assert "recorded replay action mismatch" in completed.output
    assert not artifact.exists()
