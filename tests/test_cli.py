import json
from pathlib import Path

from typer.testing import CliRunner

from jevcompiler.cli import app
from jevcompiler.providers.discovery import ProviderAvailability

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


def test_doctor_json_reports_available_provider(monkeypatch) -> None:
    async def discover() -> list[ProviderAvailability]:
        return [
            ProviderAvailability(
                "ollama", True, "http://127.0.0.1:11434/api/tags", ("qwen3:8b",)
            ),
            ProviderAvailability("lmstudio", False, reason="ConnectError"),
            ProviderAvailability(
                "openrouter-free",
                True,
                "https://openrouter.ai/api/v1",
                ("openrouter/free",),
            ),
            ProviderAvailability("openrouter-paid", True, "https://openrouter.ai/api/v1"),
        ]

    monkeypatch.setattr("jevcompiler.cli.discover_teacher_providers", discover)

    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert len(payload["providers"]) == 4
    assert payload["providers"][0] == {
        "available": True,
        "endpoint": "http://127.0.0.1:11434/api/tags",
        "models": ["qwen3:8b"],
        "provider": "ollama",
        "reason": None,
    }
    assert payload["selected"] == {"model": "qwen3:8b", "provider": "ollama"}
    assert payload["selection_error"] is None


def test_doctor_json_reports_selection_failure(monkeypatch) -> None:
    async def discover() -> list[ProviderAvailability]:
        return [
            ProviderAvailability("ollama", False, reason="ConnectError"),
            ProviderAvailability("lmstudio", False, reason="ConnectError"),
            ProviderAvailability(
                "openrouter-free", False, reason="OPENROUTER_API_KEY is not configured"
            ),
            ProviderAvailability(
                "openrouter-paid", False, reason="OPENROUTER_API_KEY is not configured"
            ),
        ]

    monkeypatch.setattr("jevcompiler.cli.discover_teacher_providers", discover)

    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["selected"] is None
    assert "No local or free teacher" in payload["selection_error"]
    assert all(item["available"] is False for item in payload["providers"])


def test_doctor_redacts_credentials_in_both_output_modes(monkeypatch) -> None:
    secret = "doctor-secret-value"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)

    async def discover() -> list[ProviderAvailability]:
        return [
            ProviderAvailability(
                "ollama",
                False,
                f"https://user:{secret}@models.example.test/list?api_key={secret}",
                reason=f"Bearer {secret}",
            )
        ]

    monkeypatch.setattr("jevcompiler.cli.discover_teacher_providers", discover)

    human = runner.invoke(app, ["doctor"])
    machine = runner.invoke(app, ["doctor", "--json"])

    assert human.exit_code == 0, human.output
    assert machine.exit_code == 0, machine.output
    assert secret not in human.output
    assert secret not in machine.output
    provider = json.loads(machine.output)["providers"][0]
    assert provider["endpoint"] == "https://[REDACTED]@models.example.test/list"
    assert provider["reason"] == "Bearer [REDACTED]"
