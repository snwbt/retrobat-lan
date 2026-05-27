from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import token_dependency
from .config import AppConfig, load_config
from .config import config_to_writable_data, is_valid_retrobat_root, resolve_retrobat_root, write_config_data
from .controls import ControllerDeviceProvider, ControlsService
from .launcher import Launcher, process_running
from .logging_config import configure_logging, get_logger
from .models import (
    Game,
    ControllerDevice,
    ControlsAssignRequest,
    ControlsRepairResponse,
    ControlsStatusResponse,
    ControlsVerifyResponse,
    LaunchRequest,
    LaunchResult,
    PowerResult,
    PublicConfigResponse,
    RandomGameRequest,
    SetupConfigRequest,
    SetupStatusResponse,
    StatusResponse,
    StartupResult,
    SystemInfo,
)
from .scanner import GameIndex
from .startup import StartupManager, WindowsRegistryStartupManager
from .system_control import reboot as request_reboot
from .system_control import shutdown as request_shutdown

logger = get_logger("main")


def _normalize_setup_path(value: str | None, base_dir: Path) -> Path | None:
    if value is None or value.strip() == "":
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path


def create_app(
    config: AppConfig | None = None,
    startup_manager: StartupManager | None = None,
    controls_provider: ControllerDeviceProvider | None = None,
) -> FastAPI:
    app_config = config or load_config()
    configure_logging(app_config.log_dir)
    index = GameIndex(app_config)
    index.rescan()
    launcher = Launcher(app_config, index)
    startup = startup_manager or WindowsRegistryStartupManager()
    controls = ControlsService(app_config, controls_provider)

    app = FastAPI(title="RetroBat Cab Commander", version="0.1.0")

    if app_config.cors_enabled:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app_config.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["X-Arcade-Token", "Content-Type"],
        )

    require_token = token_dependency(app_config)

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
        )

    @app.post("/setup/config", response_model=SetupStatusResponse, dependencies=[Depends(require_token)])
    def setup_config_endpoint(request: SetupConfigRequest) -> SetupStatusResponse:
        base_dir = app_config.config_path.parent if app_config.config_path else Path.cwd()
        configured_root = app_config.configured_retrobat_root
        if request.retrobat_root is not None:
            configured_root = _normalize_setup_path(request.retrobat_root, base_dir)
        auto_detect = app_config.auto_detect_retrobat
        if request.auto_detect_retrobat is not None:
            auto_detect = request.auto_detect_retrobat

        if configured_root and not auto_detect and not is_valid_retrobat_root(configured_root):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Configured RetroBat path is not valid and auto-detect is disabled.",
            )

        resolution = resolve_retrobat_root(configured_root, auto_detect)
        if request.bind_host is not None:
            if request.bind_host.strip() == "":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bind_host cannot be blank.")
            app_config.bind_host = request.bind_host.strip()
        if request.port is not None:
            if request.port < 1 or request.port > 65535:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="port must be between 1 and 65535.")
            app_config.port = request.port

        app_config.auto_detect_retrobat = auto_detect
        app_config.configured_retrobat_root = configured_root
        app_config.retrobat_root = resolution.resolved
        app_config.retrobat_root_source = resolution.source
        app_config.retrobat_root_valid = resolution.valid
        if app_config.config_path:
            write_config_data(app_config.config_path, config_to_writable_data(app_config))
        index.rescan()
        return setup_status_endpoint()

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
    def controls_repair_retroarch_endpoint() -> ControlsRepairResponse:
        return controls.repair_retroarch()

    @app.post("/launch", response_model=LaunchResult, dependencies=[Depends(require_token)])
    def launch_endpoint(request: LaunchRequest) -> LaunchResult:
        controls.ensure_launch_ready()
        return launcher.launch(request)

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
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


app = create_app()
