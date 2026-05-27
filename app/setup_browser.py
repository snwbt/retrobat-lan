from __future__ import annotations

import os
from pathlib import Path

from .config import AppConfig, is_valid_retrobat_root
from .scanner import resolve_es_systems_cfg


def existing_drive_roots() -> list[Path]:
    if os.name != "nt":
        return [Path("/")]
    roots = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = Path(f"{letter}:/")
        if root.exists():
            roots.append(root)
    return roots


def folder_indicators(path: Path) -> dict[str, bool]:
    retrobat_exe = (path / "retrobat.exe").is_file()
    roms_root = (path / "roms").is_dir()
    config = AppConfig(retrobat_root=path)
    es_systems = resolve_es_systems_cfg(config) is not None
    return {
        "retrobat_exe": retrobat_exe,
        "roms_root": roms_root,
        "es_systems_cfg": es_systems,
        "valid_retrobat_root": is_valid_retrobat_root(path),
    }


def browse_folders(path: str | None = None) -> tuple[Path | None, str | None, list[Path], list[Path], str | None]:
    drives = existing_drive_roots()
    if not path:
        return None, None, drives, [], None

    current = Path(path).expanduser()
    try:
        current = current.resolve()
    except OSError:
        return current, None, drives, [], "Folder does not exist or cannot be resolved."
    if not current.exists() or not current.is_dir():
        return current, None, drives, [], "Folder does not exist or is not a directory."

    children: list[Path] = []
    error = None
    try:
        for child in current.iterdir():
            try:
                if child.is_dir():
                    children.append(child)
            except OSError:
                continue
    except PermissionError:
        error = "Permission denied while listing this folder."
    except OSError as exc:
        error = str(exc)
    return current, str(current.parent) if current.parent != current else None, drives, sorted(children, key=lambda item: item.name.lower()), error

