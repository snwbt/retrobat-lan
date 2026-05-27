from __future__ import annotations

from pathlib import Path

from app.config import load_config, resolve_retrobat_root


def make_retrobat(path: Path, *, exe: bool = True, roms: bool = True, cfg: bool = False) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    if exe:
        (path / "retrobat.exe").write_text("exe", encoding="utf-8")
    if roms:
        (path / "roms").mkdir(exist_ok=True)
    if cfg:
        cfg_path = path / "emulationstation" / ".emulationstation" / "es_systems.cfg"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text("<systemList />", encoding="utf-8")
    return path


def test_config_loading_defaults() -> None:
    config = load_config("missing-config.toml")

    assert config.bind_host == "127.0.0.1"
    assert config.port == 8765
    assert config.auto_detect_retrobat is True
    assert config.allow_rom_symlinks is True
    assert config.experimental_direct_es_launch is False


def test_config_loading_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
retrobat_root = "RetroBat"
api_token = "top-secret"
bind_host = "0.0.0.0"
port = 9000
favorite_systems = ["nes"]
frontend_process_names = ["retrobat.exe"]
emulator_process_names = ["retroarch.exe"]
es_systems_cfg = "custom/es_systems.cfg"
allow_rom_symlinks = false
experimental_direct_es_launch = true
""",
        encoding="utf-8",
    )
    (tmp_path / "RetroBat" / "roms").mkdir(parents=True)

    config = load_config(config_path)

    assert config.retrobat_root == tmp_path / "RetroBat"
    assert config.configured_retrobat_root == tmp_path / "RetroBat"
    assert config.retrobat_root_source == "config"
    assert config.retrobat_root_valid is True
    assert config.api_token == "top-secret"
    assert config.bind_host == "0.0.0.0"
    assert config.port == 9000
    assert config.favorite_systems == ["nes"]
    assert config.es_systems_cfg == tmp_path / "custom" / "es_systems.cfg"
    assert config.allow_rom_symlinks is False
    assert config.experimental_direct_es_launch is True


def test_configured_path_wins_over_auto_detection(tmp_path: Path) -> None:
    configured = make_retrobat(tmp_path / "configured")
    detected = make_retrobat(tmp_path / "detected", cfg=True)

    resolution = resolve_retrobat_root(
        configured,
        auto_detect=True,
        common_path_candidates=[detected],
        exe_neighbor_candidates=[],
        drive_scan_candidates=[],
    )

    assert resolution.resolved == configured.resolve()
    assert resolution.source == "config"
    assert resolution.valid is True


def test_invalid_configured_path_falls_back_when_auto_detect_enabled(tmp_path: Path) -> None:
    configured = tmp_path / "missing"
    detected = make_retrobat(tmp_path / "detected")

    resolution = resolve_retrobat_root(
        configured,
        auto_detect=True,
        common_path_candidates=[detected],
        exe_neighbor_candidates=[],
        drive_scan_candidates=[],
    )

    assert resolution.configured == configured
    assert resolution.resolved == detected.resolve()
    assert resolution.source == "common-path"


def test_invalid_configured_path_does_not_fallback_when_auto_detect_disabled(tmp_path: Path) -> None:
    configured = tmp_path / "missing"
    detected = make_retrobat(tmp_path / "detected")

    resolution = resolve_retrobat_root(
        configured,
        auto_detect=False,
        common_path_candidates=[detected],
    )

    assert resolution.resolved == configured
    assert resolution.source == "config"
    assert resolution.valid is False


def test_env_detection_works(tmp_path: Path) -> None:
    env_root = make_retrobat(tmp_path / "env-root")

    resolution = resolve_retrobat_root(
        None,
        auto_detect=True,
        env_root=str(env_root),
        exe_neighbor_candidates=[],
        common_path_candidates=[],
        drive_scan_candidates=[],
    )

    assert resolution.resolved == env_root.resolve()
    assert resolution.source == "env"


def test_common_path_detection_works(tmp_path: Path) -> None:
    common = make_retrobat(tmp_path / "RetroBat")

    resolution = resolve_retrobat_root(
        None,
        auto_detect=True,
        exe_neighbor_candidates=[],
        common_path_candidates=[common],
        drive_scan_candidates=[],
    )

    assert resolution.resolved == common.resolve()
    assert resolution.source == "common-path"


def test_drive_scan_detection_works(tmp_path: Path) -> None:
    drive_candidate = make_retrobat(tmp_path / "DriveRoot" / "RetroBat")

    resolution = resolve_retrobat_root(
        None,
        auto_detect=True,
        exe_neighbor_candidates=[],
        common_path_candidates=[],
        drive_scan_candidates=[drive_candidate],
    )

    assert resolution.resolved == drive_candidate.resolve()
    assert resolution.source == "drive-scan"


def test_best_candidate_prefers_es_systems_cfg(tmp_path: Path) -> None:
    basic = make_retrobat(tmp_path / "basic", exe=True, roms=True, cfg=False)
    richer = make_retrobat(tmp_path / "richer", exe=True, roms=True, cfg=True)

    resolution = resolve_retrobat_root(
        None,
        auto_detect=True,
        exe_neighbor_candidates=[basic, richer],
        common_path_candidates=[],
        drive_scan_candidates=[],
    )

    assert resolution.resolved == richer.resolve()
    assert resolution.source == "exe-neighbor"
