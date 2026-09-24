from jevcompiler.security import redact


def test_redacts_named_and_bearer_secrets(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "super-secret-value")
    value = {
        "api_key": "another-secret",
        "message": "Bearer abc.def and super-secret-value",
        "safe": ["keep me"],
    }
    redacted = redact(value)
    assert redacted["api_key"] == "[REDACTED]"
    assert "abc.def" not in redacted["message"]
    assert "super-secret-value" not in redacted["message"]
    assert redacted["safe"] == ["keep me"]

