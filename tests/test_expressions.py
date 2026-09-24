import pytest

from jevcompiler.runtime.expressions import ExpressionError, evaluate_expression


def test_safe_arithmetic_boolean_and_attributes() -> None:
    context = {
        "risk": 0.82,
        "route": {"choice": "billing", "confidence": 0.91},
    }
    assert evaluate_expression(
        'risk >= 0.8 and route.choice == "billing" and max(risk, route.confidence) > 0.9',
        context,
    )


@pytest.mark.parametrize(
    "expression",
    [
        '__import__("os").system("whoami")',
        "open('/tmp/nope')",
        "(1).__class__",
        "[x for x in [1]]",
    ],
)
def test_unsafe_syntax_is_rejected(expression: str) -> None:
    with pytest.raises(ExpressionError):
        evaluate_expression(expression, {})


def test_unknown_variable_is_clear() -> None:
    with pytest.raises(ExpressionError, match="unknown variable"):
        evaluate_expression("missing > 0.5", {})

