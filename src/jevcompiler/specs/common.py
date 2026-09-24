from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class SpecLoadError(ValueError):
    """A configuration file could not be loaded as a mapping."""


def load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SpecLoadError(f"Unable to read {source}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SpecLoadError(f"{source} must contain a YAML object at its top level")
    return raw

