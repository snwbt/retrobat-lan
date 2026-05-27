from __future__ import annotations

from pathlib import Path

import pytest

from app.config import AppConfig


@pytest.fixture
def retrobat_root(tmp_path: Path) -> Path:
    root = tmp_path / "RetroBat"
    (root / "roms").mkdir(parents=True)
    return root


def make_config(root: Path, token: str = "secret") -> AppConfig:
    return AppConfig(
        retrobat_root=root,
        configured_retrobat_root=root,
        retrobat_root_source="config",
        retrobat_root_valid=(root / "retrobat.exe").is_file() or (root / "roms").is_dir(),
        api_token=token,
        log_dir=root / "logs",
    )
