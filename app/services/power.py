from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..config import AppConfig
from ..logging_config import get_logger
from ..models import NowPlayingResponse, PowerActionResponse, PowerProcess, PowerStatusResponse
from ..system_control import reboot as request_reboot
from ..system_control import shutdown as request_shutdown
from .now_playing import NowPlayingService

logger = get_logger("power")


@dataclass
class ProcessQuery:
    processes: list[PowerProcess] = field(default_factory=list)
    available: bool = True
    warnings: list[str] = field(default_factory=list)


class PowerProcessManager:
    def list_processes(self, process_names: list[str]) -> ProcessQuery:
        raise NotImplementedError

    def graceful_close(self, processes: list[PowerProcess]) -> tuple[list[PowerProcess], list[str]]:
        raise NotImplementedError

    def force_kill(self, processes: list[PowerProcess]) -> tuple[list[PowerProcess], list[str]]:
        raise NotImplementedError

    def wait_for_exit(self, process_names: list[str], timeout_seconds: int) -> ProcessQuery:
        deadline = time.monotonic() + max(0, timeout_seconds)
        latest = self.list_processes(process_names)
        while latest.available and latest.processes and time.monotonic() < deadline:
            time.sleep(0.25)
            latest = self.list_processes(process_names)
        return latest


class PsutilPowerProcessManager(PowerProcessManager):
    def _psutil(self):
        try:
            import psutil  # type: ignore
        except Exception:
            return None
        return psutil

    def list_processes(self, process_names: list[str]) -> ProcessQuery:
        wanted = {name.lower() for name in process_names}
        if not wanted:
            return ProcessQuery()
        psutil = self._psutil()
        if psutil is None:
            return ProcessQuery(available=False, warnings=["psutil is not available; process state cannot be confirmed."])
        processes: list[PowerProcess] = []
        try:
            for process in psutil.process_iter(["name", "pid", "exe"]):
                info = getattr(process, "info", {}) or {}
                name = str(info.get("name") or "")
                if name.lower() not in wanted:
                    continue
                processes.append(
                    PowerProcess(
                        name=name,
                        pid=int(info.get("pid") or getattr(process, "pid", 0)),
                        exe=str(info.get("exe") or "") or None,
                    )
                )
        except Exception as exc:
            return ProcessQuery(available=False, warnings=[f"Process detection failed: {exc}"])
        return ProcessQuery(processes=processes)

    def graceful_close(self, processes: list[PowerProcess]) -> tuple[list[PowerProcess], list[str]]:
        psutil = self._psutil()
        if psutil is None:
            return [], ["psutil is not available; emulator processes cannot be closed."]
        closed: list[PowerProcess] = []
        warnings: list[str] = []
        for process in processes:
            try:
                psutil.Process(process.pid).terminate()
                closed.append(process)
            except Exception as exc:
                warnings.append(f"Could not gracefully close {process.name} ({process.pid}): {exc}")
        return closed, warnings

    def force_kill(self, processes: list[PowerProcess]) -> tuple[list[PowerProcess], list[str]]:
        psutil = self._psutil()
        if psutil is None:
            return [], ["psutil is not available; emulator processes cannot be force killed."]
        killed: list[PowerProcess] = []
        warnings: list[str] = []
        for process in processes:
            try:
                psutil.Process(process.pid).kill()
                killed.append(process)
            except Exception as exc:
                warnings.append(f"Could not force kill {process.name} ({process.pid}): {exc}")
        return killed, warnings


class PowerService:
    def __init__(
        self,
        config: AppConfig,
        now_playing: NowPlayingService,
        process_manager: PowerProcessManager | None = None,
    ):
        self.config = config
        self.now_playing = now_playing
        self.process_manager = process_manager or PsutilPowerProcessManager()

    def status(self) -> PowerStatusResponse:
        frontend = self.process_manager.list_processes(self.config.frontend_process_names)
        emulators = self.process_manager.list_processes(self.config.emulator_process_names)
        warnings = [*frontend.warnings, *emulators.warnings]
        if not frontend.available or not emulators.available:
            warnings.append("Process state is unavailable; safe shutdown is blocked.")
        if emulators.processes:
            warnings.append("Emulator process is running; quit the current game before shutdown.")
        safe = frontend.available and emulators.available and not emulators.processes
        return PowerStatusResponse(
            frontend_running=bool(frontend.processes),
            emulator_running=bool(emulators.processes),
            frontend_processes=frontend.processes,
            emulator_processes=emulators.processes,
            now_playing=self.now_playing.current(),
            safe_to_shutdown=safe,
            warnings=warnings,
        )

    def quit_current_game(self) -> PowerActionResponse:
        emulators = self.process_manager.list_processes(self.config.emulator_process_names)
        warnings = list(emulators.warnings)
        if not emulators.available:
            warnings.append("Process state is unavailable; current game cannot be quit safely.")
            return self._action("quit-current-game", False, "Could not confirm emulator process state.", warnings, [], [])
        if not emulators.processes:
            return self._action("quit-current-game", True, "No emulator processes are running.", warnings, [], [])

        closed, close_warnings = self.process_manager.graceful_close(emulators.processes)
        warnings.extend(close_warnings)
        remaining = self.process_manager.wait_for_exit(self.config.emulator_process_names, self.config.safe_power_wait_seconds)
        warnings.extend(remaining.warnings)

        if remaining.processes and self.config.allow_force_kill_emulators:
            killed, kill_warnings = self.process_manager.force_kill(remaining.processes)
            closed.extend(killed)
            warnings.extend(kill_warnings)
            remaining = self.process_manager.wait_for_exit(self.config.emulator_process_names, self.config.safe_power_wait_seconds)
            warnings.extend(remaining.warnings)

        if remaining.processes:
            warnings.append("Emulator processes are still running after graceful close.")
            return self._action("quit-current-game", False, "Emulator processes are still running.", warnings, closed, remaining.processes)

        return self._action("quit-current-game", True, "Emulator processes closed.", warnings, closed, [])

    def shutdown_safe(self, dry_run: bool = False) -> PowerActionResponse:
        return self._safe_power("shutdown-safe", dry_run)

    def reboot_safe(self, dry_run: bool = False) -> PowerActionResponse:
        return self._safe_power("reboot-safe", dry_run)

    def _safe_power(self, action: str, dry_run: bool) -> PowerActionResponse:
        quit_result = self.quit_current_game()
        warnings = list(quit_result.warnings)
        if quit_result.remaining_emulator_processes:
            message = "Blocked because emulator processes are still running."
            logger.warning("safe_power_blocked action=%s warnings=%s", action, warnings)
            return self._action(action, False, message, warnings, quit_result.closed_processes, quit_result.remaining_emulator_processes, dry_run)

        status = self.status()
        warnings.extend(status.warnings)
        if not status.safe_to_shutdown:
            message = "Blocked because safe shutdown conditions were not met."
            logger.warning("safe_power_blocked action=%s warnings=%s", action, warnings)
            return self._action(action, False, message, warnings, quit_result.closed_processes, status.emulator_processes, dry_run)

        if action == "shutdown-safe":
            result = request_shutdown(dry_run=dry_run)
        else:
            result = request_reboot(dry_run=dry_run)
        return self._action(action, result.accepted or dry_run, result.message, warnings, quit_result.closed_processes, [], dry_run)

    @staticmethod
    def _action(
        action: str,
        accepted: bool,
        message: str,
        warnings: list[str],
        closed: list[PowerProcess],
        remaining: list[PowerProcess],
        dry_run: bool = False,
    ) -> PowerActionResponse:
        return PowerActionResponse(
            accepted=accepted,
            action=action,
            safe_to_shutdown=accepted and not remaining,
            message=message,
            warnings=warnings,
            closed_processes=closed,
            remaining_emulator_processes=remaining,
            dry_run=dry_run,
        )
