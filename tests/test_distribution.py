from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.verify_distribution import DistributionError, verify_distributions


def _write_wheel(path: Path, *, private_member: str | None = None) -> None:
    metadata = (
        "Metadata-Version: 2.4\n"
        "Name: jevcompiler\n"
        "Version: 0.1.0\n"
        "Requires-Python: >=3.11\n"
    )
    members = {
        "jevcompiler/py.typed": b"",
        "jevcompiler/freeze/runtime.ts": b"export {};\n",
        "jevcompiler-0.1.0.dist-info/METADATA": metadata.encode(),
        "jevcompiler-0.1.0.dist-info/entry_points.txt": (
            b"[console_scripts]\njevcompiler = jevcompiler.cli:app\n"
        ),
    }
    if private_member is not None:
        members[private_member] = b"private"
    with zipfile.ZipFile(path, mode="w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def _write_sdist(path: Path) -> None:
    root = "jevcompiler-0.1.0"
    members = {
        f"{root}/LICENSE": b"MIT\n",
        f"{root}/README.md": b"# Jev Compiler\n",
        f"{root}/pyproject.toml": b"[project]\nname = 'jevcompiler'\n",
        f"{root}/src/jevcompiler/freeze/runtime.ts": b"export {};\n",
        f"{root}/src/jevcompiler/py.typed": b"",
    }
    with tarfile.open(path, mode="w:gz") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def test_distribution_verifier_accepts_release_archives(tmp_path) -> None:
    _write_wheel(tmp_path / "jevcompiler-0.1.0-py3-none-any.whl")
    _write_sdist(tmp_path / "jevcompiler-0.1.0.tar.gz")

    wheel, wheel_count, sdist, sdist_count = verify_distributions(tmp_path)

    assert wheel.suffix == ".whl"
    assert wheel_count == 4
    assert sdist.name.endswith(".tar.gz")
    assert sdist_count == 5


def test_distribution_verifier_rejects_private_files(tmp_path) -> None:
    _write_wheel(
        tmp_path / "jevcompiler-0.1.0-py3-none-any.whl",
        private_member=".jevcompiler/private/keys.env",
    )
    _write_sdist(tmp_path / "jevcompiler-0.1.0.tar.gz")

    with pytest.raises(DistributionError, match="private path"):
        verify_distributions(tmp_path)
