"""Conventional project-local paths for generated runtime data."""

from pathlib import Path

LOCAL_WORKSPACE = Path(".jevcompiler")
ARTIFACTS_ROOT = LOCAL_WORKSPACE / "artifacts"
DEFAULT_CACHE_PATH = LOCAL_WORKSPACE / "cache" / "jev-responses.sqlite3"


def artifact_directory(task_name: str, kind: str) -> Path:
    return ARTIFACTS_ROOT / task_name / kind
