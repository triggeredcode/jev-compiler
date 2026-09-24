from __future__ import annotations

import ast
import operator
from collections.abc import Mapping
from typing import Any


class ExpressionError(ValueError):
    """The expression is invalid or uses a forbidden operation."""


_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_COMPARE = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}
_FUNCTIONS = {"min": min, "max": max, "abs": abs}


def _resolve_attribute(node: ast.Attribute, context: Mapping[str, Any]) -> Any:
    parts: list[str] = [node.attr]
    value: ast.expr = node.value
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if not isinstance(value, ast.Name):
        raise ExpressionError("attributes may only reference named result fields")
    parts.append(value.id)
    current: Any = context
    for part in reversed(parts):
        if not isinstance(current, Mapping) or part not in current:
            raise ExpressionError(f"unknown variable: {'.'.join(reversed(parts))}")
        current = current[part]
    return current


def _evaluate(node: ast.AST, context: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, context)
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in context:
            raise ExpressionError(f"unknown variable: {node.id}")
        return context[node.id]
    if isinstance(node, ast.Attribute):
        return _resolve_attribute(node, context)
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        values = [_evaluate(item, context) for item in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _evaluate(node.operand, context)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _evaluate(node.operand, context)
        return -value if isinstance(node.op, ast.USub) else +value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        return _BINARY[type(node.op)](_evaluate(node.left, context), _evaluate(node.right, context))
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, context)
        for operation, comparator in zip(node.ops, node.comparators, strict=True):
            function = _COMPARE.get(type(operation))
            if function is None:
                raise ExpressionError(f"comparison {type(operation).__name__} is not allowed")
            right = _evaluate(comparator, context)
            if not function(left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        function = _FUNCTIONS.get(node.func.id)
        if function is None or node.keywords:
            raise ExpressionError(f"function {node.func.id} is not allowed")
        return function(*(_evaluate(argument, context) for argument in node.args))
    raise ExpressionError(f"syntax {type(node).__name__} is not allowed")


def evaluate_expression(expression: str, context: Mapping[str, Any]) -> Any:
    normalized = expression.replace("&&", " and ").replace("||", " or ")
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"invalid expression: {exc.msg}") from None
    try:
        return _evaluate(tree, context)
    except ExpressionError:
        raise
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ExpressionError(f"expression failed: {exc}") from None

