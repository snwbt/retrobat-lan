from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SystemDefinition(BaseModel):
    name: str
    fullname: Optional[str] = None
    path: Optional[str] = None
    extension: Optional[str] = None
    command: Optional[str] = None
    platform: Optional[str] = None
    theme: Optional[str] = None
    resolved_path: Optional[str] = None
    extensions: list[str] = Field(default_factory=list)


class Game(BaseModel):
    system: str
    name: str
    path: str
    extension: str
    likely_display_name: str


class SystemInfo(BaseModel):
    name: str
    rom_path: str
    game_count: int
    favorite: bool = False
    fullname: Optional[str] = None
    platform: Optional[str] = None
    theme: Optional[str] = None
    launch_mode: str = "retrobat"
    launch_warning: Optional[str] = None


class LaunchRequest(BaseModel):
    system: str
    path: Optional[str] = None
    dry_run: bool = False


class LaunchResult(BaseModel):
    launched: bool
    dry_run: bool = False
    strategy: str
    message: str
    game: Optional[Game] = None


class PlaySession(BaseModel):
    session_id: str
    system: Optional[str] = None
    game_title: Optional[str] = None
    rom_path: Optional[str] = None
    launcher_type: str
    process_name: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: str
    source: str


class DetectedProcess(BaseModel):
    name: str
    pid: int
    exe: Optional[str] = None
    started_at: Optional[datetime] = None


class NowPlayingResponse(BaseModel):
    active: bool
    session: Optional[PlaySession] = None
    detected_processes: list[DetectedProcess] = Field(default_factory=list)
    confidence: str


class MarqueeStateResponse(BaseModel):
    enabled: bool
    refresh_seconds: int
    source: str
    current_system: Optional[str] = None
    current_game: Optional[str] = None
    artwork_urls: dict[str, str] = Field(default_factory=dict)
    selected_artwork_url: Optional[str] = None
    fallback_text: str


class RandomGameRequest(BaseModel):
    system: Optional[str] = None
    favorite_only: bool = False


class StatusResponse(BaseModel):
    configured_retrobat_root: Optional[str] = None
    resolved_retrobat_root: str
    retrobat_root_source: str
    retrobat_root_valid: bool
    retrobat_root_exists: bool
    retrobat_exe_exists: bool
    roms_root_exists: bool
    es_systems_cfg_path: Optional[str]
    indexed_game_count: int
    frontend_running: bool
    emulator_running: bool


class PublicConfigResponse(BaseModel):
    bind_host: str
    port: int
    retrobat_root: str
    favorite_systems: list[str]
    indexed_game_count: int


class SetupStatusResponse(BaseModel):
    configured_retrobat_root: Optional[str] = None
    resolved_retrobat_root: str
    retrobat_root_source: str
    retrobat_root_valid: bool
    auto_detect_retrobat: bool
    bind_host: str
    port: int
    startup_enabled: bool
    config_path: Optional[str] = None
    retrobat_exe_exists: bool = False
    roms_root_exists: bool = False
    es_systems_cfg_path: Optional[str] = None
    indexed_system_count: int = 0
    indexed_game_count: int = 0
    no_games_reason: Optional[str] = None


class SetupControllerPortConfig(BaseModel):
    label: str = ""
    usb_location_path: str = ""


class SetupConfigRequest(BaseModel):
    retrobat_root: Optional[str] = None
    auto_detect_retrobat: Optional[bool] = None
    bind_host: Optional[str] = None
    port: Optional[int] = None
    controls_enabled: Optional[bool] = None
    controls_auto_repair_on_launch: Optional[bool] = None
    safe_power_wait_seconds: Optional[int] = None
    allow_force_kill_emulators: Optional[bool] = None
    controller_ports: Optional[dict[str, SetupControllerPortConfig]] = None


class SetupConfigCurrentResponse(BaseModel):
    retrobat_root: str = ""
    auto_detect_retrobat: bool
    bind_host: str
    port: int
    controls_enabled: bool
    controls_auto_repair_on_launch: bool
    safe_power_wait_seconds: int
    allow_force_kill_emulators: bool
    controller_ports: dict[str, SetupControllerPortConfig]
    backup_available: bool = False
    config_path: Optional[str] = None


class SetupConfigValidationResponse(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    resolved_retrobat_root: str
    retrobat_root_source: str
    retrobat_root_valid: bool
    retrobat_exe_exists: bool = False
    roms_root_exists: bool = False
    es_systems_cfg_path: Optional[str] = None
    restart_required: bool = False


class SetupConfigActionResponse(BaseModel):
    message: str
    setup: SetupStatusResponse
    backup_available: bool = False
    backup_path: Optional[str] = None
    restart_required: bool = False


class FolderCandidate(BaseModel):
    path: str
    name: str
    retrobat_exe: bool = False
    roms_root: bool = False
    es_systems_cfg: bool = False
    valid_retrobat_root: bool = False


class FolderBrowserResponse(BaseModel):
    current_path: Optional[str] = None
    parent_path: Optional[str] = None
    drives: list[FolderCandidate] = Field(default_factory=list)
    directories: list[FolderCandidate] = Field(default_factory=list)
    error: Optional[str] = None
    truncated: bool = False


class StartupResult(BaseModel):
    enabled: bool
    message: str


class VersionResponse(BaseModel):
    name: str
    version: str


class DiagnosticsLogsResponse(BaseModel):
    log_path: str
    lines: list[str] = Field(default_factory=list)


class DiagnosticsStatusResponse(BaseModel):
    version: str
    config_path: Optional[str] = None
    log_path: str
    retrobat_root_valid: bool
    resolved_retrobat_root: str
    es_systems_cfg_path: Optional[str] = None
    indexed_system_count: int
    indexed_game_count: int
    controls_enabled: bool
    controls_detection_error: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class ControllerDevice(BaseModel):
    id: str
    name: str
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    instance_id: Optional[str] = None
    container_id: Optional[str] = None
    usb_location_path: str
    location_info: Optional[str] = None
    joystick_index: Optional[int] = None
    joystick_index_source: str = "unavailable"


class ControllerPortAssignment(BaseModel):
    player: str
    label: str
    usb_location_path: str = ""
    device: Optional[ControllerDevice] = None


class ControlsStatusResponse(BaseModel):
    enabled: bool
    auto_repair_on_launch: bool
    retroarch_config_path: str
    retroarch_config_exists: bool
    assignments: list[ControllerPortAssignment]
    devices: list[ControllerDevice]
    detection_error: Optional[str] = None


class ControlsAssignRequest(BaseModel):
    player: str
    usb_location_path: str
    label: Optional[str] = None


class PlayerMapping(BaseModel):
    player: str
    usb_location_path: str
    joystick_index: Optional[int] = None
    joystick_index_source: str = "unavailable"
    device_name: Optional[str] = None


class ControlsVerifyResponse(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    mappings: list[PlayerMapping] = Field(default_factory=list)


class ControlsRepairRequest(BaseModel):
    force_estimated_indexes: bool = False


class ControlsRepairResponse(BaseModel):
    repaired: bool
    verify: ControlsVerifyResponse
    retroarch_config_path: str
    backup_path: Optional[str] = None


class PowerResult(BaseModel):
    accepted: bool
    action: str
    dry_run: bool = False
    message: str


class PowerProcess(BaseModel):
    name: str
    pid: int
    exe: Optional[str] = None


class PowerStatusResponse(BaseModel):
    frontend_running: bool
    emulator_running: bool
    frontend_processes: list[PowerProcess] = Field(default_factory=list)
    emulator_processes: list[PowerProcess] = Field(default_factory=list)
    now_playing: NowPlayingResponse
    safe_to_shutdown: bool
    warnings: list[str] = Field(default_factory=list)


class PowerActionResponse(BaseModel):
    accepted: bool
    action: str
    safe_to_shutdown: bool
    message: str
    warnings: list[str] = Field(default_factory=list)
    closed_processes: list[PowerProcess] = Field(default_factory=list)
    remaining_emulator_processes: list[PowerProcess] = Field(default_factory=list)
    dry_run: bool = False


HealthSeverity = Literal["ok", "warning", "error"]


class HealthCheck(BaseModel):
    key: str
    label: str
    severity: HealthSeverity
    message: str


class HealthResponse(BaseModel):
    severity: HealthSeverity
    version: str
    configured_retrobat_root: Optional[str] = None
    resolved_retrobat_root: str
    retrobat_root_source: str
    retrobat_root_valid: bool
    retrobat_exe_exists: bool
    roms_root_exists: bool
    es_systems_cfg_path: Optional[str] = None
    es_systems_cfg_exists: bool
    indexed_system_count: int
    indexed_game_count: int
    last_scan_time: Optional[datetime] = None
    frontend_running: bool
    emulator_running: bool
    process_detection_available: bool
    disk_free_bytes: Optional[int] = None
    disk_total_bytes: Optional[int] = None
    startup_available: bool
    startup_enabled: bool
    controller_lock_available: bool
    controller_lock_enabled: bool
    controller_configured_players: int
    controller_connected_players: int
    checks: list[HealthCheck] = Field(default_factory=list)


def display_name_for_path(path: Path) -> str:
    name = path.stem
    for suffix in (" (USA)", " (Europe)", " (World)"):
        name = name.replace(suffix, "")
    return name.replace("_", " ").replace(".", " ").strip() or path.name
