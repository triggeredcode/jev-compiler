"""Utilities that keep provider credentials out of logs and artifacts."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any

_SECRET_NAME = re.compile(r"(?:api[_-]?key|token|secret|authorization)", re.IGNORECASE)
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")


def redact(value: Any) -> Any:
    """Return a recursively redacted copy suitable for logs and reports."""
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _SECRET_NAME.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        text = _BEARER.sub("Bearer [REDACTED]", value)
        for name, secret in os.environ.items():
            if _SECRET_NAME.search(name) and secret and len(secret) >= 8:
                text = text.replace(secret, "[REDACTED]")
        return text
    return value

