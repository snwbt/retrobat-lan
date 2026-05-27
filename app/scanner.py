from __future__ import annotations

import os
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .config import AppConfig
from .launch_rules import WINDOWS_NATIVE_SYSTEMS, effective_launch_mode, launch_mode_warning
from .logging_config import get_logger
from .models import Game, SystemDefinition, SystemInfo, display_name_for_path

logger = get_logger("scanner")

MEDIA_METADATA_EXTENSIONS = {
    ".art",
    ".bak",
    ".cfg",
    ".db",
    ".gif",
    ".ini",
    ".jpeg",
    ".jpg",
    ".json",
    ".log",
    ".md",
    ".mp3",
    ".mp4",
    ".nfo",
    ".old",
    ".png",
    ".sav",
    ".srm",
    ".state",
    ".txt",
    ".xml",
}

CONSERVATIVE_ROM_EXTENSIONS = {
    ".7z",
    ".a26",
    ".a52",
    ".a78",
    ".bin",
    ".cdi",
    ".chd",
    ".cue",
    ".d64",
    ".elf",
    ".fds",
    ".gb",
    ".gba",
    ".gbc",
    ".gdi",
    ".gen",
    ".iso",
    ".lnk",
    ".m3u",
    ".md",
    ".nes",
    ".n64",
    ".nds",
    ".pbp",
    ".rom",
    ".rvz",
    ".sfc",
    ".smc",
    ".sms",
    ".wad",
    ".wbfs",
    ".wsquashfs",
    ".zip",
}

WINDOWS_LAUNCH_EXTENSIONS = {
    ".exe",
    ".bat",
    ".cmd",
    ".lnk",
    ".game",
    ".url",
    ".pc",
    ".win",
    ".windows",
    ".wine",
    ".7z",
    ".zip",
    ".rar",
    ".wsquashfs",
    ".uwp",
}


def parse_extension_list(value: str | None) -> list[str]:
    if not value:
        return []
    extensions = []
    for item in value.replace(",", " ").split():
        normalized = item.strip().lower()
        if not normalized:
            continue
        if not normalized.startswith("."):
            normalized = f".{normalized}"
        extensions.append(normalized)
    return sorted(set(extensions))


def resolve_es_systems_cfg(config: AppConfig) -> Optional[Path]:
    candidates: list[Path] = []
    if config.es_systems_cfg:
        candidates.append(config.es_systems_cfg)
    candidates.extend(
        [
            config.retrobat_root / "emulationstation" / ".emulationstation" / "es_systems.cfg",
            config.retrobat_root / "emulationstation" / "es_systems.cfg",
        ]
    )
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    return None


def _read_child_text(element: ET.Element, name: str) -> Optional[str]:
    child = element.find(name)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _resolve_system_path(raw_path: str | None, config: AppConfig, system_name: str) -> Path:
    if not raw_path:
        return config.roms_root / system_name

    expanded = raw_path.replace("%ROMPATH%", str(config.roms_root)).replace("~", str(Path.home()))
    path = Path(expanded)
    if path.is_absolute():
        return path

    cleaned = expanded.replace("/", os.sep).replace("\\", os.sep)
    if cleaned.startswith(f".{os.sep}"):
        cleaned = cleaned[2:]
    if cleaned.startswith(f"roms{os.sep}") or cleaned == "roms":
        return config.retrobat_root / cleaned
    return config.roms_root / cleaned


def parse_es_systems_cfg(path: Path, config: AppConfig) -> list[SystemDefinition]:
    tree = ET.parse(path)
    root = tree.getroot()
    systems: list[SystemDefinition] = []
    for system in root.findall(".//system"):
        name = _read_child_text(system, "name")
        if not name:
            continue
        raw_path = _read_child_text(system, "path")
        resolved_path = _resolve_system_path(raw_path, config, name)
        extension = _read_child_text(system, "extension")
        systems.append(
            SystemDefinition(
                name=name,
                fullname=_read_child_text(system, "fullname"),
                path=raw_path,
                extension=extension,
                command=_read_child_text(system, "command"),
                platform=_read_child_text(system, "platform"),
                theme=_read_child_text(system, "theme"),
                resolved_path=str(resolved_path),
                extensions=parse_extension_list(extension),
            )
        )
    return systems


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


class GameIndex:
    def __init__(self, config: AppConfig):
        self.config = config
        self.es_systems_cfg_path: Optional[Path] = None
        self.systems: dict[str, SystemDefinition] = {}
        self.games: list[Game] = []
        self.last_scan_time: Optional[datetime] = None

    def rescan(self) -> None:
        self.es_systems_cfg_path = resolve_es_systems_cfg(self.config)
        if self.es_systems_cfg_path:
            definitions = parse_es_systems_cfg(self.es_systems_cfg_path, self.config)
        else:
            definitions = self._folder_definitions()

        self.systems = {definition.name: definition for definition in definitions}
        self.games = []
        for definition in definitions:
            self.games.extend(self._scan_system(definition))
        self.last_scan_time = datetime.now(timezone.utc)
        logger.info("rescan_complete systems=%s games=%s", len(self.systems), len(self.games))

    def _folder_definitions(self) -> list[SystemDefinition]:
        if not self.config.roms_root.exists():
            return []
        definitions = []
        for child in sorted(self.config.roms_root.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                definitions.append(
                    SystemDefinition(
                        name=child.name,
                        resolved_path=str(child),
                        extensions=[],
                    )
                )
        return definitions

    def _allowed_extensions(self, definition: SystemDefinition) -> set[str]:
        if definition.name.lower() in WINDOWS_NATIVE_SYSTEMS:
            return set(WINDOWS_LAUNCH_EXTENSIONS)
        if definition.extensions:
            return set(definition.extensions)
        return set(CONSERVATIVE_ROM_EXTENSIONS) - MEDIA_METADATA_EXTENSIONS

    def _scan_system(self, definition: SystemDefinition) -> list[Game]:
        if not definition.resolved_path:
            return []
        root = Path(definition.resolved_path)
        if not root.exists() or not root.is_dir():
            return []
        allowed = self._allowed_extensions(definition)
        games: list[Game] = []
        for file_path in self._walk_files(root):
            if file_path.name.startswith("."):
                continue
            extension = file_path.suffix.lower()
            if extension in MEDIA_METADATA_EXTENSIONS:
                continue
            if allowed and extension not in allowed:
                continue
            if not self.is_allowed_rom_path(file_path, scan_root=root):
                logger.warning("skipped_unsafe_path path=%s", file_path)
                continue
            games.append(
                Game(
                    system=definition.name,
                    name=file_path.stem,
                    path=str(file_path),
                    extension=extension,
                    likely_display_name=display_name_for_path(file_path),
                )
            )
        return sorted(games, key=lambda item: (item.system.lower(), item.likely_display_name.lower()))

    def _walk_files(self, root: Path) -> Iterable[Path]:
        for current_root, dirs, files in os.walk(root, followlinks=self.config.allow_rom_symlinks):
            dirs[:] = [directory for directory in dirs if not directory.startswith(".")]
            for file_name in files:
                yield Path(current_root) / file_name

    def is_allowed_rom_path(self, path: Path, scan_root: Path | None = None) -> bool:
        try:
            absolute = path.expanduser().absolute()
            configured_roms = self.config.roms_root.expanduser().absolute()
            scan_root_abs = scan_root.expanduser().absolute() if scan_root else None
            lexical_ok = is_relative_to(absolute, configured_roms)
            if scan_root_abs:
                lexical_ok = lexical_ok or is_relative_to(absolute, scan_root_abs)
            if not lexical_ok:
                return False

            resolved = path.resolve(strict=False)
            real_roots = [configured_roms.resolve(strict=False)]
            if scan_root:
                real_roots.append(scan_root.resolve(strict=False))
            if self.config.allow_rom_symlinks:
                return any(is_relative_to(resolved, real_root) for real_root in real_roots)
            return is_relative_to(resolved, real_roots[0])
        except OSError:
            return False

    def systems_info(self) -> list[SystemInfo]:
        counts: dict[str, int] = {}
        for game in self.games:
            counts[game.system] = counts.get(game.system, 0) + 1
        favorites = {system.lower() for system in self.config.favorite_systems}
        result = []
        for name, definition in sorted(self.systems.items()):
            result.append(
                SystemInfo(
                    name=name,
                    rom_path=definition.resolved_path or "",
                    game_count=counts.get(name, 0),
                    favorite=name.lower() in favorites,
                    fullname=definition.fullname,
                    platform=definition.platform,
                    theme=definition.theme,
                    launch_mode=effective_launch_mode(self.config, name),
                    launch_warning=launch_mode_warning(self.config, name),
                )
            )
        return result

    def games_for_system(self, system: str) -> list[Game]:
        wanted = system.lower()
        return [game for game in self.games if game.system.lower() == wanted]

    def search(self, query: str) -> list[Game]:
        needle = query.strip().lower()
        if not needle:
            return []
        return [
            game
            for game in self.games
            if needle in game.likely_display_name.lower() or needle in game.system.lower()
        ]

    def find_game(self, system: str, path: str | None) -> Optional[Game]:
        candidates = self.games_for_system(system)
        if path is None:
            return candidates[0] if candidates else None
        try:
            requested = Path(path).expanduser().absolute()
        except OSError:
            return None
        for game in candidates:
            if Path(game.path).expanduser().absolute() == requested:
                return game
        return None

    def random_game(self, system: str | None = None, favorite_only: bool = False) -> Optional[Game]:
        games = self.games
        if system:
            games = self.games_for_system(system)
        elif favorite_only:
            favorites = {item.lower() for item in self.config.favorite_systems}
            games = [game for game in games if game.system.lower() in favorites]
        if not games:
            return None
        return random.choice(games)
