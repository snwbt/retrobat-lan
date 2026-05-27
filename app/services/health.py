from __future__ import annotations

import shutil
from os import PathLike
from pathlib import Path
from typing import Callable

from ..config import AppConfig
from ..controls import ControlsService
from ..launch_rules import launch_rule_warnings
from ..models import HealthCheck, HealthResponse, HealthSeverity
from ..scanner import GameIndex
from ..services.power import PowerService, ProcessQuery
from ..startup import StartupManager
from ..version import APP_VERSION

LOW_DISK_WARNING_BYTES = 5 * 1024 * 1024 * 1024

DiskUsage = Callable[[str | bytes | PathLike[str] | PathLike[bytes]], shutil._ntuple_diskusage]


def _worst_severity(checks: list[HealthCheck]) -> HealthSeverity:
    order = {"ok": 0, "warning": 1, "error": 2}
    severity: HealthSeverity = "ok"
    for check in checks:
        if order[check.severity] > order[severity]:
            severity = check.severity
    return severity


def _check(key: str, label: str, severity: HealthSeverity, message: str) -> HealthCheck:
    return HealthCheck(key=key, label=label, severity=severity, message=message)


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


class HealthService:
    def __init__(
        self,
        config: AppConfig,
        index: GameIndex,
        power: PowerService,
        startup: StartupManager,
        controls: ControlsService,
        disk_usage: DiskUsage | None = None,
    ):
        self.config = config
        self.index = index
        self.power = power
        self.startup = startup
        self.controls = controls
        self.disk_usage = disk_usage or shutil.disk_usage

    def status(self) -> HealthResponse:
        checks: list[HealthCheck] = []
        checks.append(self._retrobat_root_check())
        checks.append(self._es_systems_check())
        checks.extend(self._index_checks())

        frontend = self.power.process_manager.list_processes(self.config.frontend_process_names)
        emulators = self.power.process_manager.list_processes(self.config.emulator_process_names)
        process_available = frontend.available and emulators.available
        checks.append(self._process_check(frontend, emulators))
        checks.append(self._launch_rules_check())

        disk_free, disk_total, disk_check = self._disk_check()
        checks.append(disk_check)

        startup_available, startup_enabled, startup_check = self._startup_check()
        checks.append(startup_check)

        (
            controller_available,
            controller_enabled,
            configured_players,
            connected_players,
            controller_check,
        ) = self._controller_check()
        checks.append(controller_check)

        return HealthResponse(
            severity=_worst_severity(checks),
            version=APP_VERSION,
            configured_retrobat_root=str(self.config.configured_retrobat_root)
            if self.config.configured_retrobat_root
            else None,
            resolved_retrobat_root=str(self.config.retrobat_root),
            retrobat_root_source=self.config.retrobat_root_source,
            retrobat_root_valid=self.config.retrobat_root_valid,
            retrobat_exe_exists=self.config.retrobat_exe.exists(),
            roms_root_exists=self.config.roms_root.exists(),
            es_systems_cfg_path=str(self.index.es_systems_cfg_path) if self.index.es_systems_cfg_path else None,
            es_systems_cfg_exists=bool(self.index.es_systems_cfg_path and self.index.es_systems_cfg_path.exists()),
            indexed_system_count=len(self.index.systems),
            indexed_game_count=len(self.index.games),
            last_scan_time=self.index.last_scan_time,
            frontend_running=bool(frontend.processes),
            emulator_running=bool(emulators.processes),
            process_detection_available=process_available,
            disk_free_bytes=disk_free,
            disk_total_bytes=disk_total,
            startup_available=startup_available,
            startup_enabled=startup_enabled,
            controller_lock_available=controller_available,
            controller_lock_enabled=controller_enabled,
            controller_configured_players=configured_players,
            controller_connected_players=connected_players,
            checks=checks,
        )

    def _retrobat_root_check(self) -> HealthCheck:
        if not self.config.retrobat_root_valid:
            severity: HealthSeverity = "warning" if self.config.auto_detect_retrobat else "error"
            return _check("retrobat_root", "RetroBat root", severity, "RetroBat root was not found or is not valid.")
        return _check("retrobat_root", "RetroBat root", "ok", "RetroBat folder is valid.")

    def _es_systems_check(self) -> HealthCheck:
        if self.index.es_systems_cfg_path:
            return _check("es_systems_cfg", "es_systems.cfg", "ok", "es_systems.cfg was found.")
        if not self.config.retrobat_root_valid:
            return _check("es_systems_cfg", "es_systems.cfg", "warning", "Cannot check es_systems.cfg until RetroBat is found.")
        if self.index.systems:
            return _check("es_systems_cfg", "es_systems.cfg", "warning", "es_systems.cfg was not found; using roms folder fallback.")
        return _check("es_systems_cfg", "es_systems.cfg", "error", "es_systems.cfg was not found and no systems were discovered.")

    def _index_checks(self) -> list[HealthCheck]:
        checks: list[HealthCheck] = []
        if self.index.systems:
            checks.append(_check("indexed_systems", "Indexed systems", "ok", f"{len(self.index.systems)} systems indexed."))
        else:
            checks.append(_check("indexed_systems", "Indexed systems", "warning", _no_games_reason(self.config, self.index) or "No systems indexed."))
        if self.index.games:
            checks.append(_check("indexed_games", "Indexed games", "ok", f"{len(self.index.games)} games indexed."))
        else:
            checks.append(_check("indexed_games", "Indexed games", "warning", _no_games_reason(self.config, self.index) or "No games indexed."))
        return checks

    @staticmethod
    def _process_check(frontend: ProcessQuery, emulators: ProcessQuery) -> HealthCheck:
        warnings = [*frontend.warnings, *emulators.warnings]
        if not frontend.available or not emulators.available:
            message = "Process state is unavailable."
            if warnings:
                message = f"{message} {' '.join(warnings)}"
            return _check("processes", "Process detection", "warning", message)
        if emulators.processes:
            return _check("processes", "Process detection", "warning", "Emulator process is running.")
        if frontend.processes:
            return _check("processes", "Process detection", "ok", "Frontend is running and no emulator is active.")
        return _check("processes", "Process detection", "ok", "No configured frontend or emulator processes are running.")

    def _launch_rules_check(self) -> HealthCheck:
        warnings = launch_rule_warnings(self.config)
        if warnings:
            return _check("launch_rules", "Launch rules", "warning", " ".join(warnings))
        if self.config.launch_rules:
            return _check("launch_rules", "Launch rules", "ok", "Per-system launch rules are valid.")
        return _check("launch_rules", "Launch rules", "ok", "Using default launch rules.")

    def _disk_check(self) -> tuple[int | None, int | None, HealthCheck]:
        disk_path = self.config.retrobat_root if self.config.retrobat_root.exists() else self.config.retrobat_root.anchor or str(self.config.retrobat_root)
        try:
            usage = self.disk_usage(disk_path)
        except Exception as exc:
            severity: HealthSeverity = "error" if self.config.retrobat_root_valid else "warning"
            return None, None, _check("disk_space", "Disk space", severity, f"Could not read RetroBat drive free space: {exc}")
        if usage.free < LOW_DISK_WARNING_BYTES:
            return usage.free, usage.total, _check("disk_space", "Disk space", "warning", "RetroBat drive has less than 5 GB free.")
        return usage.free, usage.total, _check("disk_space", "Disk space", "ok", "RetroBat drive has enough free space.")

    def _startup_check(self) -> tuple[bool, bool, HealthCheck]:
        try:
            enabled = self.startup.is_enabled()
        except Exception as exc:
            return False, False, _check("startup", "Start with Windows", "warning", f"Startup status is unavailable: {exc}")
        return True, enabled, _check(
            "startup",
            "Start with Windows",
            "ok" if enabled else "warning",
            "Start with Windows is enabled." if enabled else "Start with Windows is not enabled.",
        )

    def _controller_check(self) -> tuple[bool, bool, int, int, HealthCheck]:
        try:
            status = self.controls.status()
        except Exception as exc:
            return False, self.config.controls_enabled, 0, 0, _check("controllers", "Controller lock", "warning", f"Controller status is unavailable: {exc}")
        configured = sum(1 for assignment in status.assignments if assignment.usb_location_path)
        connected = sum(1 for assignment in status.assignments if assignment.usb_location_path and assignment.device)
        if status.detection_error:
            return True, status.enabled, configured, connected, _check("controllers", "Controller lock", "warning", status.detection_error)
        if not status.enabled:
            return True, False, configured, connected, _check("controllers", "Controller lock", "warning", "Controller lock is disabled.")
        if configured == 0:
            return True, True, configured, connected, _check("controllers", "Controller lock", "warning", "No player USB ports are assigned.")
        if connected < configured:
            return True, True, configured, connected, _check("controllers", "Controller lock", "warning", "One or more assigned player controls are not detected.")
        return True, True, configured, connected, _check("controllers", "Controller lock", "ok", "Assigned player controls are detected.")
