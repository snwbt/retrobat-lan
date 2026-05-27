from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

from ..config import AppConfig
from ..models import Game, MarqueeStateResponse, PlaySession
from ..scanner import GameIndex, is_relative_to
from .now_playing import NowPlayingService

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
ARTWORK_TAGS = {
    "marquee": ["marquee"],
    "wheel": ["wheel"],
    "boxart": ["image"],
    "screenshot": ["thumbnail", "image", "video"],
}
MEDIA_FOLDERS = {
    "marquee": ["marquees"],
    "wheel": ["wheels"],
    "boxart": ["boxart"],
    "screenshot": ["screenshots"],
}


class MarqueeService:
    def __init__(self, config: AppConfig, index: GameIndex, now_playing: NowPlayingService):
        self.config = config
        self.index = index
        self.now_playing = now_playing
        self._artwork_registry: dict[str, Path] = {}

    def state(self) -> MarqueeStateResponse:
        refresh_seconds = max(1, int(self.config.marquee_refresh_seconds or 5))
        if not self.config.marquee_enabled:
            return MarqueeStateResponse(
                enabled=False,
                refresh_seconds=refresh_seconds,
                source="disabled",
                fallback_text="Marquee disabled",
            )

        session, source = self._session_source()
        game = self._game_for_session(session) if session else None
        current_system = (game.system if game else session.system) if session else None
        current_game = self._game_title(session, game) if session else None
        fallback = current_game or current_system or "RetroBat Cab Commander"
        artwork_urls = self._artwork_urls(game) if game else {}
        selected = next(iter(artwork_urls.values()), None)
        return MarqueeStateResponse(
            enabled=True,
            refresh_seconds=refresh_seconds,
            source=source,
            current_system=current_system,
            current_game=current_game,
            artwork_urls=artwork_urls,
            selected_artwork_url=selected,
            fallback_text=fallback,
        )

    def artwork_path(self, artwork_id: str) -> Path | None:
        path = self._artwork_registry.get(artwork_id)
        if not path or not self._is_safe_artwork(path):
            return None
        return path

    def _session_source(self) -> tuple[PlaySession | None, str]:
        current = self.now_playing.current()
        if current.active and current.session and (current.session.system or current.session.game_title):
            return current.session, "now_playing"
        last = self.now_playing.last_session()
        if last and (last.system or last.game_title):
            return last, "last_launch"
        return None, "fallback"

    def _game_for_session(self, session: PlaySession) -> Game | None:
        if session.system and session.rom_path:
            return self.index.find_game(session.system, session.rom_path)
        return None

    @staticmethod
    def _game_title(session: PlaySession | None, game: Game | None) -> str | None:
        if session and session.game_title:
            return session.game_title
        if game:
            return game.likely_display_name or game.name
        return None

    def _artwork_urls(self, game: Game) -> dict[str, str]:
        artwork: dict[str, Path] = {}
        gamelist_artwork = self._gamelist_artwork(game)
        for kind in self._preferences():
            path = gamelist_artwork.get(kind) or self._media_artwork(game, kind)
            if path and self._is_safe_artwork(path):
                artwork[kind] = path
        return {kind: f"/marquee/artwork/{self._register_artwork(path)}" for kind, path in artwork.items()}

    def _preferences(self) -> list[str]:
        result = []
        for item in self.config.marquee_artwork_preference:
            kind = str(item).strip().lower()
            if kind in ARTWORK_TAGS and kind not in result:
                result.append(kind)
        return result or ["marquee", "wheel", "boxart", "screenshot"]

    def _system_root(self, game: Game) -> Path:
        definition = self.index.systems.get(game.system)
        if definition and definition.resolved_path:
            return Path(definition.resolved_path)
        return self.config.roms_root / game.system

    def _gamelist_artwork(self, game: Game) -> dict[str, Path]:
        system_root = self._system_root(game)
        gamelist = system_root / "gamelist.xml"
        if not gamelist.exists():
            return {}
        try:
            root = ET.parse(gamelist).getroot()
        except ET.ParseError:
            return {}
        game_path = Path(game.path).resolve(strict=False)
        for item in root.findall(".//game"):
            raw_path = (item.findtext("path") or "").strip()
            if not raw_path:
                continue
            candidate = self._resolve_media_path(raw_path, system_root)
            if candidate.resolve(strict=False) != game_path:
                continue
            artwork: dict[str, Path] = {}
            for kind, tags in ARTWORK_TAGS.items():
                for tag in tags:
                    raw_media = (item.findtext(tag) or "").strip()
                    if not raw_media:
                        continue
                    media_path = self._resolve_media_path(raw_media, system_root)
                    if media_path.suffix.lower() in IMAGE_EXTENSIONS:
                        artwork[kind] = media_path
                        break
            return artwork
        return {}

    @staticmethod
    def _resolve_media_path(value: str, system_root: Path) -> Path:
        path = Path(value.replace("/", "\\"))
        if path.is_absolute():
            return path
        cleaned = value.replace("/", "\\")
        if cleaned.startswith(f".\\"):
            cleaned = cleaned[2:]
        return system_root / cleaned

    def _media_artwork(self, game: Game, kind: str) -> Path | None:
        system_root = self._system_root(game)
        stems = {Path(game.path).stem.lower(), game.name.lower()}
        folders: list[Path] = []
        for folder_name in MEDIA_FOLDERS.get(kind, []):
            folders.append(system_root / "media" / folder_name)
            folders.append(self.config.retrobat_root / "downloaded_media" / game.system / folder_name)
        for folder in folders:
            if not folder.exists() or not folder.is_dir():
                continue
            for child in sorted(folder.iterdir()):
                if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS and child.stem.lower() in stems:
                    return child
        return None

    def _register_artwork(self, path: Path) -> str:
        resolved = path.resolve(strict=False)
        digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:20]
        self._artwork_registry[digest] = resolved
        return digest

    def _is_safe_artwork(self, path: Path) -> bool:
        try:
            if path.suffix.lower() not in IMAGE_EXTENSIONS or not path.exists() or not path.is_file():
                return False
            resolved = path.resolve(strict=False)
            roots = [self.config.retrobat_root.resolve(strict=False), self.config.roms_root.resolve(strict=False)]
            roots.extend(
                Path(definition.resolved_path).resolve(strict=False)
                for definition in self.index.systems.values()
                if definition.resolved_path
            )
            return any(is_relative_to(resolved, root) for root in roots)
        except OSError:
            return False
