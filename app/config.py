from __future__ import annotations

import os
import secrets
import sys
import tomllib
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


DEFAULT_FRONTEND_PROCESSES = ["retrobat.exe", "emulationstation.exe"]
DEFAULT_EMULATOR_PROCESSES = ["retroarch.exe"]
DEFAULT_RETROBAT_ROOT = Path("C:/RetroBat")
DEFAULT_API_TOKEN = "change-this-token"
LEGACY_DEFAULT_API_TOKEN = "change-me"
RETROBAT_ROOT_SOURCES = {"config", "env", "exe-neighbor", "common-path", "drive-scan", "default"}


class RetroBatRootResolution(BaseModel):
    configured: Optional[Path] = None
    resolved: Path
    source: str
    valid: bool = False


class AppConfig(BaseModel):
    retrobat_root: Path = DEFAULT_RETROBAT_ROOT
    configured_retrobat_root: Optional[Path] = None
    retrobat_root_source: str = "default"
    retrobat_root_valid: bool = False
    config_path: Optional[Path] = None
    auto_detect_retrobat: bool = True
    api_token: str = DEFAULT_API_TOKEN
    bind_host: str = "127.0.0.1"
    port: int = 8765
    favorite_systems: list[str] = Field(default_factory=list)
    frontend_process_names: list[str] = Field(default_factory=lambda: list(DEFAULT_FRONTEND_PROCESSES))
    emulator_process_names: list[str] = Field(default_factory=lambda: list(DEFAULT_EMULATOR_PROCESSES))
    es_systems_cfg: Optional[Path] = None
    allow_rom_symlinks: bool = True
    experimental_direct_es_launch: bool = False
    cors_enabled: bool = False
    cors_origins: list[str] = Field(default_factory=list)
    log_dir: Path = Path("logs")

    @property
    def roms_root(self) -> Path:
        return self.retrobat_root / "roms"

    @property
    def retrobat_exe(self) -> Path:
        return self.retrobat_root / "retrobat.exe"

    def redacted_retrobat_root(self) -> str:
        return self.retrobat_root.name or str(self.retrobat_root)


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _normalize_path(value: Any, base_dir: Path) -> Any:
    if _is_blank(value):
        return None
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path


def resolve_config_path(config_path: str | Path | None = None) -> Path:
    env_path = os.environ.get("RETROBAT_CAB_CONFIG")
    path = Path(config_path or env_path or "config.toml").expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _es_systems_candidates(root: Path) -> list[Path]:
    return [
        root / "emulationstation" / ".emulationstation" / "es_systems.cfg",
        root / "emulationstation" / "es_systems.cfg",
    ]


def retrobat_candidate_score(path: Path) -> int:
    score = 0
    if (path / "retrobat.exe").is_file():
        score += 4
    if (path / "roms").is_dir():
        score += 3
    if any(candidate.is_file() for candidate in _es_systems_candidates(path)):
        score += 2
    return score


def is_valid_retrobat_root(path: Path) -> bool:
    return (path / "retrobat.exe").is_file() or (path / "roms").is_dir()


def _exe_neighbor_candidates() -> list[Path]:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
    else:
        exe_dir = Path.cwd().resolve()
    return [exe_dir, exe_dir / "RetroBat", exe_dir.parent / "RetroBat"]


def _common_path_candidates() -> list[Path]:
    candidates = [Path("C:/RetroBat"), Path("D:/RetroBat"), Path("E:/RetroBat")]
    system_drive = os.environ.get("SystemDrive")
    if system_drive:
        candidates.append(Path(system_drive) / "RetroBat")
    return candidates


def _drive_scan_candidates() -> list[Path]:
    candidates = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = Path(f"{letter}:/")
        candidate = root / "RetroBat"
        if candidate.exists():
            candidates.append(candidate)
    return candidates


def _best_valid_candidate(candidates: list[Path], source: str) -> Optional[RetroBatRootResolution]:
    best_path: Optional[Path] = None
    best_score = -1
    for candidate in candidates:
        if not is_valid_retrobat_root(candidate):
            continue
        score = retrobat_candidate_score(candidate)
        if score > best_score:
            best_path = candidate
            best_score = score
    if best_path is None:
        return None
    return RetroBatRootResolution(resolved=best_path.resolve(), source=source, valid=True)


def resolve_retrobat_root(
    configured: Optional[Path],
    auto_detect: bool,
    env_root: str | None = None,
    exe_neighbor_candidates: Optional[list[Path]] = None,
    common_path_candidates: Optional[list[Path]] = None,
    drive_scan_candidates: Optional[list[Path]] = None,
) -> RetroBatRootResolution:
    if configured and is_valid_retrobat_root(configured):
        return RetroBatRootResolution(
            configured=configured,
            resolved=configured.resolve(),
            source="config",
            valid=True,
        )
    if configured and not auto_detect:
        return RetroBatRootResolution(
            configured=configured,
            resolved=configured,
            source="config",
            valid=False,
        )
    if not auto_detect:
        return RetroBatRootResolution(resolved=DEFAULT_RETROBAT_ROOT, source="default", valid=False)

    candidate_groups = [
        (exe_neighbor_candidates if exe_neighbor_candidates is not None else _exe_neighbor_candidates(), "exe-neighbor"),
        (common_path_candidates if common_path_candidates is not None else _common_path_candidates(), "common-path"),
        (drive_scan_candidates if drive_scan_candidates is not None else _drive_scan_candidates(), "drive-scan"),
    ]
    for candidates, source in candidate_groups:
        resolved = _best_valid_candidate(candidates, source)
        if resolved:
            resolved.configured = configured
            return resolved

    env_value = env_root if env_root is not None else os.environ.get("RETROBAT_ROOT")
    env_path = _normalize_path(env_value, Path.cwd()) if env_value else None
    if env_path:
        resolved = _best_valid_candidate([env_path], "env")
        if resolved:
            resolved.configured = configured
            return resolved

    fallback = configured or DEFAULT_RETROBAT_ROOT
    return RetroBatRootResolution(
        configured=configured,
        resolved=fallback,
        source="default",
        valid=is_valid_retrobat_root(fallback),
    )


def generate_api_token() -> str:
    return secrets.token_urlsafe(32)


def default_config_data(api_token: str | None = None) -> dict[str, Any]:
    return {
        "auto_detect_retrobat": True,
        "retrobat_root": "",
        "api_token": api_token or generate_api_token(),
        "bind_host": "127.0.0.1",
        "port": 8765,
        "favorite_systems": ["arcade", "nes", "snes", "windows"],
        "frontend_process_names": list(DEFAULT_FRONTEND_PROCESSES),
        "emulator_process_names": list(DEFAULT_EMULATOR_PROCESSES),
        "allow_rom_symlinks": True,
        "experimental_direct_es_launch": False,
        "cors_enabled": False,
        "cors_origins": [],
        "log_dir": "logs",
    }


def _toml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Path):
        return _toml_quote(str(value).replace("\\", "/"))
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if value is None:
        return '""'
    return _toml_quote(str(value))


def write_config_data(path: Path, data: dict[str, Any]) -> None:
    ordered_keys = [
        "auto_detect_retrobat",
        "retrobat_root",
        "api_token",
        "bind_host",
        "port",
        "favorite_systems",
        "frontend_process_names",
        "emulator_process_names",
        "es_systems_cfg",
        "allow_rom_symlinks",
        "experimental_direct_es_launch",
        "cors_enabled",
        "cors_origins",
        "log_dir",
    ]
    lines = [
        "# RetroBat Cab Commander configuration",
        "# Leave retrobat_root blank for auto-detection, or set auto_detect_retrobat=false to force a path.",
        "",
    ]
    for key in ordered_keys:
        if key in data and data[key] is not None:
            lines.append(f"{key} = {_toml_value(data[key])}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_config_file(config_path: str | Path | None = None) -> tuple[Path, str, bool]:
    path = resolve_config_path(config_path)
    if path.exists():
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        token = str(raw.get("api_token") or "")
        if token and token not in {DEFAULT_API_TOKEN, LEGACY_DEFAULT_API_TOKEN}:
            return path, token, False
        token = generate_api_token()
        raw["api_token"] = token
        write_config_data(path, {**default_config_data(api_token=token), **raw})
        return path, token, True

    token = generate_api_token()
    write_config_data(path, default_config_data(api_token=token))
    return path, token, True


def load_config(config_path: str | Path | None = None) -> AppConfig:
    path = resolve_config_path(config_path)
    base_dir = path.parent.resolve()
    raw: dict[str, Any] = {}
    if path.exists():
        with path.open("rb") as handle:
            raw = tomllib.load(handle)

    configured_root = _normalize_path(raw.get("retrobat_root"), base_dir)
    if "es_systems_cfg" in raw:
        raw["es_systems_cfg"] = _normalize_path(raw["es_systems_cfg"], base_dir)
    if "log_dir" in raw:
        raw["log_dir"] = _normalize_path(raw["log_dir"], base_dir)

    auto_detect = bool(raw.get("auto_detect_retrobat", True))
    resolution = resolve_retrobat_root(configured_root, auto_detect)
    raw["retrobat_root"] = resolution.resolved
    raw["configured_retrobat_root"] = resolution.configured
    raw["retrobat_root_source"] = resolution.source
    raw["retrobat_root_valid"] = resolution.valid
    raw["auto_detect_retrobat"] = auto_detect
    raw["config_path"] = path

    return AppConfig(**raw)


def config_to_writable_data(config: AppConfig) -> dict[str, Any]:
    return {
        "auto_detect_retrobat": config.auto_detect_retrobat,
        "retrobat_root": str(config.configured_retrobat_root or ""),
        "api_token": config.api_token,
        "bind_host": config.bind_host,
        "port": config.port,
        "favorite_systems": config.favorite_systems,
        "frontend_process_names": config.frontend_process_names,
        "emulator_process_names": config.emulator_process_names,
        "es_systems_cfg": config.es_systems_cfg,
        "allow_rom_symlinks": config.allow_rom_symlinks,
        "experimental_direct_es_launch": config.experimental_direct_es_launch,
        "cors_enabled": config.cors_enabled,
        "cors_origins": config.cors_origins,
        "log_dir": config.log_dir,
    }
