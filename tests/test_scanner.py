from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config import AppConfig
from app.scanner import GameIndex, parse_es_systems_cfg, resolve_es_systems_cfg
from tests.conftest import make_config


def write_es_systems(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"<systemList>{body}</systemList>", encoding="utf-8")


def test_es_systems_precedence_and_parsing(retrobat_root: Path) -> None:
    default_cfg = retrobat_root / "emulationstation" / ".emulationstation" / "es_systems.cfg"
    custom_cfg = retrobat_root / "custom.cfg"
    write_es_systems(
        default_cfg,
        """
<system><name>ignored</name><path>./roms/ignored</path></system>
""",
    )
    write_es_systems(
        custom_cfg,
        """
<system>
  <name>nes</name>
  <fullname>Nintendo Entertainment System</fullname>
  <path>./roms/nes</path>
  <extension>.nes .zip</extension>
  <command>retroarch %ROM%</command>
  <platform>nes</platform>
  <theme>nes</theme>
</system>
""",
    )
    config = AppConfig(retrobat_root=retrobat_root, es_systems_cfg=custom_cfg)

    resolved = resolve_es_systems_cfg(config)
    systems = parse_es_systems_cfg(resolved, config)  # type: ignore[arg-type]

    assert resolved == custom_cfg.resolve()
    assert systems[0].name == "nes"
    assert systems[0].fullname == "Nintendo Entertainment System"
    assert systems[0].extensions == [".nes", ".zip"]
    assert systems[0].resolved_path == str(retrobat_root / "roms" / "nes")


def test_parse_absolute_rom_path(retrobat_root: Path, tmp_path: Path) -> None:
    absolute_roms = tmp_path / "external" / "snes"
    cfg = retrobat_root / "emulationstation" / "es_systems.cfg"
    write_es_systems(
        cfg,
        f"""
<system><name>snes</name><path>{absolute_roms}</path><extension>.sfc</extension></system>
""",
    )

    systems = parse_es_systems_cfg(cfg, make_config(retrobat_root))

    assert systems[0].resolved_path == str(absolute_roms)


def test_scanner_uses_es_extensions_and_ignores_folders(retrobat_root: Path) -> None:
    (retrobat_root / "roms" / "nes").mkdir(parents=True)
    (retrobat_root / "roms" / "nes" / "Mario.nes").write_text("rom", encoding="utf-8")
    (retrobat_root / "roms" / "nes" / "Mario.png").write_text("art", encoding="utf-8")
    (retrobat_root / "roms" / "nes" / "Other.sfc").write_text("rom", encoding="utf-8")
    cfg = retrobat_root / "emulationstation" / ".emulationstation" / "es_systems.cfg"
    write_es_systems(
        cfg,
        """
<system><name>nes</name><path>./roms/nes</path><extension>.nes</extension></system>
""",
    )

    index = GameIndex(make_config(retrobat_root))
    index.rescan()

    assert [game.path for game in index.games] == [str(retrobat_root / "roms" / "nes" / "Mario.nes")]


def test_folder_fallback_without_es_systems(retrobat_root: Path) -> None:
    (retrobat_root / "roms" / "arcade").mkdir()
    (retrobat_root / "roms" / "arcade" / "pacman.zip").write_text("rom", encoding="utf-8")

    index = GameIndex(make_config(retrobat_root))
    index.rescan()

    assert "arcade" in index.systems
    assert len(index.games) == 1


def test_windows_launcher_allowlist(retrobat_root: Path) -> None:
    windows = retrobat_root / "roms" / "windows"
    windows.mkdir(parents=True)
    for name in ["Game.bat", "Game.cmd", "Game.exe", "Game.txt"]:
        (windows / name).write_text("x", encoding="utf-8")

    index = GameIndex(make_config(retrobat_root))
    index.rescan()

    assert {Path(game.path).suffix.lower() for game in index.games} == {".bat", ".cmd", ".exe"}


def test_random_game_selection(retrobat_root: Path) -> None:
    for system in ["nes", "snes"]:
        folder = retrobat_root / "roms" / system
        folder.mkdir(parents=True)
        (folder / f"{system}.zip").write_text("rom", encoding="utf-8")
    index = GameIndex(AppConfig(retrobat_root=retrobat_root, favorite_systems=["snes"]))
    index.rescan()

    assert index.random_game(system="nes").system == "nes"  # type: ignore[union-attr]
    assert index.random_game(favorite_only=True).system == "snes"  # type: ignore[union-attr]


def test_symlinked_rom_folder_can_be_indexed(retrobat_root: Path, tmp_path: Path) -> None:
    target = tmp_path / "external-roms"
    target.mkdir()
    (target / "linked.zip").write_text("rom", encoding="utf-8")
    link = retrobat_root / "roms" / "arcade"
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlink creation is unavailable: {exc}")

    index = GameIndex(make_config(retrobat_root))
    index.rescan()

    assert len(index.games) == 1
    assert index.games[0].system == "arcade"

