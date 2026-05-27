from __future__ import annotations

from pathlib import Path

from app.config import config_to_writable_data, load_config, resolve_retrobat_root, write_config_data


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
    assert config.marquee_enabled is False
    assert config.marquee_refresh_seconds == 5
    assert config.marquee_artwork_preference == ["marquee", "wheel", "boxart", "screenshot"]


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

[launch_rules.Windows]
mode = "shell"

[launch_rules.steam]
mode = "steam_uri"

[controller_ports.player1]
label = "Left controls"
usb_location_path = "USBROOT(0)#USB(1)"
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
    assert config.launch_rules["windows"].mode == "shell"
    assert config.launch_rules["steam"].mode == "steam_uri"
    assert config.controller_ports["player1"].label == "Left controls"
    assert config.controller_ports["player1"].usb_location_path == "USBROOT(0)#USB(1)"


def test_launch_rules_preserved_when_writing_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
retrobat_root = "RetroBat"
api_token = "secret"

[launch_rules.arcade]
mode = "retrobat"

[launch_rules.steam]
mode = "disabled"
""",
        encoding="utf-8",
    )
    (tmp_path / "RetroBat" / "roms").mkdir(parents=True)
    config = load_config(config_path)

    written_path = tmp_path / "written.toml"
    write_config_data(written_path, config_to_writable_data(config))
    written = written_path.read_text(encoding="utf-8")

    assert "[launch_rules.arcade]" in written
    assert 'mode = "retrobat"' in written
    assert "[launch_rules.steam]" in written
    assert 'mode = "disabled"' in written


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
