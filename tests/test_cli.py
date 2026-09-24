from pathlib import Path

from typer.testing import CliRunner

from jevcompiler.cli import app

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def test_validate_and_offline_run() -> None:
    example = ROOT / "examples" / "support-routing"
    validation = runner.invoke(
        app, ["validate", str(example / "program.yaml"), "--kind", "program"]
    )
    assert validation.exit_code == 0, validation.output
    result = runner.invoke(
        app,
        [
            "run",
            str(example / "program.yaml"),
            str(example / "state.json"),
            "--answers",
            str(example / "answers.json"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"action": "billing"' in result.output
