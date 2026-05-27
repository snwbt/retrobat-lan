from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .auth import token_dependency
from .bootstrap import BootstrapTokenStore
from .config import AppConfig, ControllerPortConfig, load_config
from .config import config_to_writable_data, is_valid_retrobat_root, resolve_retrobat_root, write_config_data
from .config import create_config_backup, latest_config_backup, revert_latest_config_backup
from .controls import ControllerDeviceProvider, ControlsService
from .diagnostics import diagnostics_bundle, log_path, redact_text, tail_log
from .launcher import Launcher, process_running
from .launch_rules import launch_rule_warnings
from .logging_config import configure_logging, get_logger
from .models import (
    Game,
    ControllerDevice,
    ControlsAssignRequest,
    ControlsRepairRequest,
    ControlsRepairResponse,
    ControlsStatusResponse,
    ControlsVerifyResponse,
    DiagnosticsLogsResponse,
    DiagnosticsStatusResponse,
    FolderBrowserResponse,
    FolderCandidate,
    HealthResponse,
    LaunchRequest,
    LaunchResult,
    MarqueeStateResponse,
    NowPlayingResponse,
    PowerActionResponse,
    PowerStatusResponse,
    PowerResult,
    PublicConfigResponse,
    RandomGameRequest,
    SetupConfigActionResponse,
    SetupConfigCurrentResponse,
    SetupConfigRequest,
    SetupConfigValidationResponse,
    SetupControllerPortConfig,
    SetupStatusResponse,
    StatusResponse,
    StartupResult,
    SystemInfo,
    VersionResponse,
)
from .scanner import GameIndex
from .scanner import resolve_es_systems_cfg
from .services.health import DiskUsage, HealthService
from .services.marquee import MarqueeService
from .services.now_playing import NowPlayingService
from .services.power import PowerProcessManager, PowerService
from .setup_browser import browse_folders, folder_indicators
from .startup import StartupManager, WindowsRegistryStartupManager
from .system_control import reboot as request_reboot
from .system_control import shutdown as request_shutdown
from .version import APP_VERSION, BUILD_NAME

logger = get_logger("main")


def _normalize_setup_path(value: str | None, base_dir: Path) -> Path | None:
    if value is None or value.strip() == "":
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path


def _no_games_reason(config: AppConfig, index: GameIndex) -> str | None:
    if len(index.games) > 0:
        return None
    if not config.retrobat_root_valid:
        return "RetroBat root is not valid. Choose the folder that contains retrobat.exe or roms."
    if not config.roms_root.exists():
        return "The selected RetroBat folder does not contain a roms folder."
    if index.es_systems_cfg_path and not index.systems:
        return "es_systems.cfg was found, but it did not contain any systems."
    if not index.systems:
        return "No systems were indexed. Check es_systems.cfg or the roms folder."
    return "Systems were indexed, but no matching ROM files were found."


def _folder_candidate(path: Path) -> FolderCandidate:
    indicators = folder_indicators(path)
    return FolderCandidate(path=str(path), name=path.name or str(path), **indicators)


def _safe_controller_ports(data: dict[str, SetupControllerPortConfig] | None) -> dict[str, ControllerPortConfig]:
    ports: dict[str, ControllerPortConfig] = {}
    for player in ["player1", "player2"]:
        incoming = data.get(player) if data else None
        if incoming:
            ports[player] = ControllerPortConfig(
                label=incoming.label or ("Player 1" if player == "player1" else "Player 2"),
                usb_location_path=incoming.usb_location_path,
            )
    return ports


def _copy_config_state(target: AppConfig, source: AppConfig) -> None:
    for field in AppConfig.model_fields:
        setattr(target, field, getattr(source, field))


def create_app(
    config: AppConfig | None = None,
    startup_manager: StartupManager | None = None,
    controls_provider: ControllerDeviceProvider | None = None,
    bootstrap_store: BootstrapTokenStore | None = None,
    now_playing_service: NowPlayingService | None = None,
    power_process_manager: PowerProcessManager | None = None,
    health_disk_usage: DiskUsage | None = None,
) -> FastAPI:
    app_config = config or load_config()
    configure_logging(app_config.log_dir)
    index = GameIndex(app_config)
    index.rescan()
    launcher = Launcher(app_config, index)
    startup = startup_manager or WindowsRegistryStartupManager()
    controls = ControlsService(app_config, controls_provider)
    bootstrap = bootstrap_store or BootstrapTokenStore()
    now_playing = now_playing_service or NowPlayingService(app_config)
    power = PowerService(app_config, now_playing, process_manager=power_process_manager)
    health = HealthService(app_config, index, power, startup, controls, disk_usage=health_disk_usage or None)
    marquee = MarqueeService(app_config, index, now_playing)

    app = FastAPI(title="RetroBat Cab Commander", version=APP_VERSION)

    if app_config.cors_enabled:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app_config.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["X-Arcade-Token", "Content-Type"],
        )

    require_token = token_dependency(app_config)

    def current_config_response() -> SetupConfigCurrentResponse:
        return SetupConfigCurrentResponse(
            retrobat_root=str(app_config.configured_retrobat_root or ""),
            auto_detect_retrobat=app_config.auto_detect_retrobat,
            bind_host=app_config.bind_host,
            port=app_config.port,
            controls_enabled=app_config.controls_enabled,
            controls_auto_repair_on_launch=app_config.controls_auto_repair_on_launch,
            safe_power_wait_seconds=app_config.safe_power_wait_seconds,
            allow_force_kill_emulators=app_config.allow_force_kill_emulators,
            controller_ports={
                key: SetupControllerPortConfig(label=value.label, usb_location_path=value.usb_location_path)
                for key, value in app_config.controller_ports.items()
                if key in {"player1", "player2"}
            },
            backup_available=bool(app_config.config_path and latest_config_backup(app_config.config_path)),
            config_path=str(app_config.config_path) if app_config.config_path else None,
        )

    def validate_setup_config(request: SetupConfigRequest) -> SetupConfigValidationResponse:
        base_dir = app_config.config_path.parent if app_config.config_path else Path.cwd()
        configured_root = app_config.configured_retrobat_root
        if request.retrobat_root is not None:
            configured_root = _normalize_setup_path(request.retrobat_root, base_dir)

        auto_detect = app_config.auto_detect_retrobat
        if request.auto_detect_retrobat is not None:
            auto_detect = request.auto_detect_retrobat

        errors: list[str] = []
        warnings: list[str] = []
        if configured_root and not auto_detect and not is_valid_retrobat_root(configured_root):
            errors.append("Configured RetroBat path is not valid and auto-detect is disabled.")

        bind_host = app_config.bind_host if request.bind_host is None else request.bind_host.strip()
        if not bind_host:
            errors.append("bind_host cannot be blank.")

        port = app_config.port if request.port is None else request.port
        if port < 1 or port > 65535:
            errors.append("port must be between 1 and 65535.")
        safe_power_wait = app_config.safe_power_wait_seconds if request.safe_power_wait_seconds is None else request.safe_power_wait_seconds
        if safe_power_wait < 0 or safe_power_wait > 120:
            errors.append("safe_power_wait_seconds must be between 0 and 120.")

        resolution = resolve_retrobat_root(configured_root, auto_detect)
        draft_config = AppConfig(
            **{
                **app_config.model_dump(),
                "configured_retrobat_root": configured_root,
                "retrobat_root": resolution.resolved,
                "retrobat_root_source": resolution.source,
                "retrobat_root_valid": resolution.valid,
                "auto_detect_retrobat": auto_detect,
                "bind_host": bind_host or app_config.bind_host,
                "port": port,
            }
        )
        es_systems_cfg = resolve_es_systems_cfg(draft_config)
        if not resolution.valid:
            warnings.append("RetroBat was not found. Save is allowed only when auto-detect remains enabled.")
        elif not draft_config.roms_root.exists():
            warnings.append("The selected RetroBat folder does not contain a roms folder.")

        return SetupConfigValidationResponse(
            ok=not errors,
            errors=errors,
            warnings=warnings,
            resolved_retrobat_root=str(resolution.resolved),
            retrobat_root_source=resolution.source,
            retrobat_root_valid=resolution.valid,
            retrobat_exe_exists=draft_config.retrobat_exe.exists(),
            roms_root_exists=draft_config.roms_root.exists(),
            es_systems_cfg_path=str(es_systems_cfg) if es_systems_cfg else None,
            restart_required=bind_host != app_config.bind_host or port != app_config.port,
        )

    def apply_setup_config_request(request: SetupConfigRequest) -> bool:
        base_dir = app_config.config_path.parent if app_config.config_path else Path.cwd()
        configured_root = app_config.configured_retrobat_root
        if request.retrobat_root is not None:
            configured_root = _normalize_setup_path(request.retrobat_root, base_dir)

        auto_detect = app_config.auto_detect_retrobat
        if request.auto_detect_retrobat is not None:
            auto_detect = request.auto_detect_retrobat
        resolution = resolve_retrobat_root(configured_root, auto_detect)

        restart_required = False
        if request.bind_host is not None:
            bind_host = request.bind_host.strip()
            restart_required = restart_required or bind_host != app_config.bind_host
            app_config.bind_host = bind_host
        if request.port is not None:
            restart_required = restart_required or request.port != app_config.port
            app_config.port = request.port
        if request.controls_enabled is not None:
            app_config.controls_enabled = request.controls_enabled
        if request.controls_auto_repair_on_launch is not None:
            app_config.controls_auto_repair_on_launch = request.controls_auto_repair_on_launch
        if request.safe_power_wait_seconds is not None:
            app_config.safe_power_wait_seconds = request.safe_power_wait_seconds
        if request.allow_force_kill_emulators is not None:
            app_config.allow_force_kill_emulators = request.allow_force_kill_emulators
        if request.controller_ports is not None:
            current_ports = dict(app_config.controller_ports)
            current_ports.update(_safe_controller_ports(request.controller_ports))
            app_config.controller_ports = current_ports

        app_config.auto_detect_retrobat = auto_detect
        app_config.configured_retrobat_root = configured_root
        app_config.retrobat_root = resolution.resolved
        app_config.retrobat_root_source = resolution.source
        app_config.retrobat_root_valid = resolution.valid
        return restart_required

    @app.middleware("http")
    async def no_cache_dashboard_assets(request, call_next):
        response = await call_next(request)
        if request.url.path in {
            "/",
            "/index.html",
            "/app.js",
            "/style.css",
            "/kiosk",
            "/kiosk.html",
            "/kiosk.js",
            "/kiosk.css",
            "/marquee",
            "/marquee.html",
            "/marquee.js",
            "/marquee.css",
        }:
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.get("/setup/bootstrap", response_class=HTMLResponse)
    def setup_bootstrap_endpoint(code: str) -> str:
        token = bootstrap.consume(code)
        if token is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bootstrap code is invalid or expired.")
        escaped = token.replace("\\", "\\\\").replace("'", "\\'")
        return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>RetroBat Cab Commander</title></head>
<body>
<script>
localStorage.setItem('arcadeToken', '{escaped}');
window.location.replace('/');
</script>
Token saved. Redirecting to dashboard...
</body></html>"""

    @app.get("/version", response_model=VersionResponse)
    def version_endpoint() -> VersionResponse:
        return VersionResponse(name=BUILD_NAME, version=APP_VERSION)

    @app.get("/status", response_model=StatusResponse)
    def status_endpoint() -> StatusResponse:
        return StatusResponse(
            configured_retrobat_root=str(app_config.configured_retrobat_root)
            if app_config.configured_retrobat_root
            else None,
            resolved_retrobat_root=str(app_config.retrobat_root),
            retrobat_root_source=app_config.retrobat_root_source,
            retrobat_root_valid=app_config.retrobat_root_valid,
            retrobat_root_exists=app_config.retrobat_root.exists(),
            retrobat_exe_exists=app_config.retrobat_exe.exists(),
            roms_root_exists=app_config.roms_root.exists(),
            es_systems_cfg_path=str(index.es_systems_cfg_path) if index.es_systems_cfg_path else None,
            indexed_game_count=len(index.games),
            frontend_running=process_running(app_config.frontend_process_names),
            emulator_running=process_running(app_config.emulator_process_names),
        )

    @app.get("/config/public", response_model=PublicConfigResponse)
    def public_config_endpoint() -> PublicConfigResponse:
        return PublicConfigResponse(
            bind_host=app_config.bind_host,
            port=app_config.port,
            retrobat_root=app_config.redacted_retrobat_root(),
            favorite_systems=app_config.favorite_systems,
            indexed_game_count=len(index.games),
        )

    @app.get("/systems", response_model=list[SystemInfo])
    def systems_endpoint() -> list[SystemInfo]:
        return index.systems_info()

    @app.get("/games/{system}", response_model=list[Game])
    def games_endpoint(system: str) -> list[Game]:
        if system not in index.systems:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown system.")
        return index.games_for_system(system)

    @app.get("/search", response_model=list[Game])
    def search_endpoint(q: str = Query(default="", min_length=0)) -> list[Game]:
        return index.search(q)

    @app.get("/now-playing", response_model=NowPlayingResponse)
    def now_playing_endpoint() -> NowPlayingResponse:
        return now_playing.current()

    @app.get("/power/status", response_model=PowerStatusResponse)
    def power_status_endpoint() -> PowerStatusResponse:
        return power.status()

    @app.get("/health", response_model=HealthResponse)
    def health_endpoint() -> HealthResponse:
        return health.status()

    @app.get("/marquee/state", response_model=MarqueeStateResponse)
    def marquee_state_endpoint() -> MarqueeStateResponse:
        return marquee.state()

    @app.post("/rescan", response_model=dict[str, int], dependencies=[Depends(require_token)])
    def rescan_endpoint() -> dict[str, int]:
        index.rescan()
        return {"systems": len(index.systems), "games": len(index.games)}

    @app.get("/setup/status", response_model=SetupStatusResponse, dependencies=[Depends(require_token)])
    def setup_status_endpoint() -> SetupStatusResponse:
        return SetupStatusResponse(
            configured_retrobat_root=str(app_config.configured_retrobat_root)
            if app_config.configured_retrobat_root
            else None,
            resolved_retrobat_root=str(app_config.retrobat_root),
            retrobat_root_source=app_config.retrobat_root_source,
            retrobat_root_valid=app_config.retrobat_root_valid,
            auto_detect_retrobat=app_config.auto_detect_retrobat,
            bind_host=app_config.bind_host,
            port=app_config.port,
            startup_enabled=startup.is_enabled(),
            config_path=str(app_config.config_path) if app_config.config_path else None,
            retrobat_exe_exists=app_config.retrobat_exe.exists(),
            roms_root_exists=app_config.roms_root.exists(),
            es_systems_cfg_path=str(index.es_systems_cfg_path) if index.es_systems_cfg_path else None,
            indexed_system_count=len(index.systems),
            indexed_game_count=len(index.games),
            no_games_reason=_no_games_reason(app_config, index),
        )

    @app.get("/setup/folders", response_model=FolderBrowserResponse, dependencies=[Depends(require_token)])
    def setup_folders_endpoint(path: str | None = None) -> FolderBrowserResponse:
        current, parent, drives, directories, error, truncated = browse_folders(path)
        return FolderBrowserResponse(
            current_path=str(current) if current else None,
            parent_path=parent,
            drives=[_folder_candidate(drive) for drive in drives],
            directories=[_folder_candidate(directory) for directory in directories],
            error=error,
            truncated=truncated,
        )

    @app.get("/setup/config/current", response_model=SetupConfigCurrentResponse, dependencies=[Depends(require_token)])
    def setup_config_current_endpoint() -> SetupConfigCurrentResponse:
        return current_config_response()

    @app.post("/setup/config/validate", response_model=SetupConfigValidationResponse, dependencies=[Depends(require_token)])
    def setup_config_validate_endpoint(request: SetupConfigRequest) -> SetupConfigValidationResponse:
        return validate_setup_config(request)

    def save_setup_config(request: SetupConfigRequest, message: str = "Configuration saved.") -> SetupConfigActionResponse:
        validation = validate_setup_config(request)
        if not validation.ok:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": "Configuration is invalid.", "errors": validation.errors})
        backup = create_config_backup(app_config.config_path) if app_config.config_path else None
        restart_required = apply_setup_config_request(request)
        if app_config.config_path:
            write_config_data(app_config.config_path, config_to_writable_data(app_config))
        index.rescan()
        logger.info("configuration_saved backup=%s restart_required=%s", backup, restart_required)
        return SetupConfigActionResponse(
            message=message,
            setup=setup_status_endpoint(),
            backup_available=bool(app_config.config_path and latest_config_backup(app_config.config_path)),
            backup_path=str(backup) if backup else None,
            restart_required=restart_required,
        )

    @app.post("/setup/config/save", response_model=SetupConfigActionResponse, dependencies=[Depends(require_token)])
    def setup_config_save_endpoint(request: SetupConfigRequest) -> SetupConfigActionResponse:
        return save_setup_config(request)

    @app.post("/setup/config", response_model=SetupStatusResponse, dependencies=[Depends(require_token)])
    def setup_config_endpoint(request: SetupConfigRequest) -> SetupStatusResponse:
        return save_setup_config(request).setup

    @app.post("/setup/config/revert", response_model=SetupConfigActionResponse, dependencies=[Depends(require_token)])
    def setup_config_revert_endpoint() -> SetupConfigActionResponse:
        if not app_config.config_path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No config file is available.")
        try:
            backup = revert_latest_config_backup(app_config.config_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No backup available.") from exc
        fresh = load_config(app_config.config_path)
        _copy_config_state(app_config, fresh)
        index.rescan()
        logger.info("configuration_reverted backup=%s", backup)
        return SetupConfigActionResponse(
            message="Previous configuration restored.",
            setup=setup_status_endpoint(),
            backup_available=bool(latest_config_backup(app_config.config_path)),
            backup_path=str(backup),
            restart_required=True,
        )

    @app.post("/setup/startup/enable", response_model=StartupResult, dependencies=[Depends(require_token)])
    def setup_startup_enable_endpoint() -> StartupResult:
        try:
            startup.enable()
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return StartupResult(enabled=startup.is_enabled(), message="Start with Windows enabled.")

    @app.post("/setup/startup/disable", response_model=StartupResult, dependencies=[Depends(require_token)])
    def setup_startup_disable_endpoint() -> StartupResult:
        try:
            startup.disable()
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return StartupResult(enabled=startup.is_enabled(), message="Start with Windows disabled.")

    @app.get("/controls/status", response_model=ControlsStatusResponse, dependencies=[Depends(require_token)])
    def controls_status_endpoint() -> ControlsStatusResponse:
        return controls.status()

    @app.get("/controls/devices", response_model=list[ControllerDevice], dependencies=[Depends(require_token)])
    def controls_devices_endpoint() -> list[ControllerDevice]:
        return controls.devices()

    @app.post("/controls/assign", response_model=ControlsStatusResponse, dependencies=[Depends(require_token)])
    def controls_assign_endpoint(request: ControlsAssignRequest) -> ControlsStatusResponse:
        return controls.assign(request)

    @app.post("/controls/verify", response_model=ControlsVerifyResponse, dependencies=[Depends(require_token)])
    def controls_verify_endpoint() -> ControlsVerifyResponse:
        return controls.verify()

    @app.post("/controls/repair-retroarch", response_model=ControlsRepairResponse, dependencies=[Depends(require_token)])
    def controls_repair_retroarch_endpoint(request: ControlsRepairRequest | None = None) -> ControlsRepairResponse:
        return controls.repair_retroarch(request)

    def diagnostics_status() -> DiagnosticsStatusResponse:
        control_status = controls.status()
        warnings = []
        if control_status.detection_error:
            warnings.append(control_status.detection_error)
        warnings.extend(launch_rule_warnings(app_config))
        if _no_games_reason(app_config, index):
            warnings.append(_no_games_reason(app_config, index) or "")
        return DiagnosticsStatusResponse(
            version=APP_VERSION,
            config_path=str(app_config.config_path) if app_config.config_path else None,
            log_path=str(log_path(app_config)),
            retrobat_root_valid=app_config.retrobat_root_valid,
            resolved_retrobat_root=str(app_config.retrobat_root),
            es_systems_cfg_path=str(index.es_systems_cfg_path) if index.es_systems_cfg_path else None,
            indexed_system_count=len(index.systems),
            indexed_game_count=len(index.games),
            controls_enabled=app_config.controls_enabled,
            controls_detection_error=control_status.detection_error,
            warnings=warnings,
        )

    @app.get("/diagnostics/status", response_model=DiagnosticsStatusResponse, dependencies=[Depends(require_token)])
    def diagnostics_status_endpoint() -> DiagnosticsStatusResponse:
        return diagnostics_status()

    @app.get("/diagnostics/logs", response_model=DiagnosticsLogsResponse, dependencies=[Depends(require_token)])
    def diagnostics_logs_endpoint(lines: int = 200) -> DiagnosticsLogsResponse:
        max_lines = max(1, min(lines, 1000))
        return DiagnosticsLogsResponse(log_path=str(log_path(app_config)), lines=tail_log(app_config, max_lines=max_lines))

    @app.get("/diagnostics/bundle", response_class=PlainTextResponse, dependencies=[Depends(require_token)])
    def diagnostics_bundle_endpoint() -> str:
        data = {
            "version": version_endpoint().model_dump(),
            "diagnostics": diagnostics_status().model_dump(),
            "status": status_endpoint().model_dump(),
            "setup": setup_status_endpoint().model_dump(),
            "health": health_endpoint().model_dump(),
            "marquee": marquee_state_endpoint().model_dump(),
            "systems": [system.model_dump() for system in index.systems_info()],
            "controls": controls.status().model_dump(),
            "now_playing": now_playing.current().model_dump(),
            "power": power.status().model_dump(),
            "logs": tail_log(app_config, max_lines=500),
        }
        return diagnostics_bundle(data)

    @app.get("/diagnostics/config-backup", response_class=PlainTextResponse, dependencies=[Depends(require_token)])
    def diagnostics_config_backup_endpoint() -> str:
        if not app_config.config_path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No config file is available.")
        backup = latest_config_backup(app_config.config_path)
        if not backup:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No backup available.")
        return redact_text(backup.read_text(encoding="utf-8", errors="replace"))

    @app.post("/launch", response_model=LaunchResult, dependencies=[Depends(require_token)])
    def launch_endpoint(request: LaunchRequest) -> LaunchResult:
        controls.ensure_launch_ready()
        result = launcher.launch(request)
        now_playing.record_launch(result)
        return result

    @app.post("/now-playing/clear", response_model=NowPlayingResponse, dependencies=[Depends(require_token)])
    def now_playing_clear_endpoint() -> NowPlayingResponse:
        return now_playing.clear()

    @app.post("/power/quit-current-game", response_model=PowerActionResponse, dependencies=[Depends(require_token)])
    def power_quit_current_game_endpoint() -> PowerActionResponse:
        return power.quit_current_game()

    @app.post("/power/shutdown-safe", response_model=PowerActionResponse, dependencies=[Depends(require_token)])
    def power_shutdown_safe_endpoint(dry_run: bool = False) -> PowerActionResponse:
        return power.shutdown_safe(dry_run=dry_run)

    @app.post("/power/reboot-safe", response_model=PowerActionResponse, dependencies=[Depends(require_token)])
    def power_reboot_safe_endpoint(dry_run: bool = False) -> PowerActionResponse:
        return power.reboot_safe(dry_run=dry_run)

    @app.post("/game/random", response_model=Game, dependencies=[Depends(require_token)])
    def random_game_endpoint(request: RandomGameRequest) -> Game:
        game = index.random_game(system=request.system, favorite_only=request.favorite_only)
        if not game:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No matching games found.")
        return game

    @app.post("/shutdown", response_model=PowerResult, dependencies=[Depends(require_token)])
    def shutdown_endpoint(dry_run: bool = False) -> PowerResult:
        return request_shutdown(dry_run=dry_run)

    @app.post("/reboot", response_model=PowerResult, dependencies=[Depends(require_token)])
    def reboot_endpoint(dry_run: bool = False) -> PowerResult:
        return request_reboot(dry_run=dry_run)

    web_dir = Path(__file__).parent / "web"

    @app.get("/kiosk", response_class=FileResponse)
    def kiosk_endpoint() -> FileResponse:
        return FileResponse(web_dir / "kiosk.html")

    @app.get("/marquee", response_class=FileResponse)
    def marquee_endpoint() -> FileResponse:
        return FileResponse(web_dir / "marquee.html")

    @app.get("/marquee/artwork/{artwork_id}", response_class=FileResponse)
    def marquee_artwork_endpoint(artwork_id: str) -> FileResponse:
        path = marquee.artwork_path(artwork_id)
        if not path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artwork not found.")
        return FileResponse(path)

    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


app = create_app()
