from jevcompiler.providers.discovery import ProviderAvailability, select_teacher


def test_selection_prefers_local_then_free() -> None:
    availability = [
        ProviderAvailability("ollama", False),
        ProviderAvailability("lmstudio", True, models=("local-model",)),
        ProviderAvailability("openrouter-free", True, models=("openrouter/free",)),
        ProviderAvailability("openrouter-paid", True),
    ]
    assert select_teacher(availability) == ("lmstudio", "local-model")


def test_paid_selection_requires_explicit_opt_in() -> None:
    availability = [ProviderAvailability("openrouter-paid", True)]
    try:
        select_teacher(availability, paid_model="anthropic/claude-sonnet")
    except RuntimeError as exc:
        assert "requires --allow-paid" in str(exc)
    else:
        raise AssertionError("paid provider was selected without opt-in")
    assert select_teacher(
        availability, allow_paid=True, paid_model="anthropic/claude-sonnet"
    ) == ("openrouter-paid", "anthropic/claude-sonnet")

