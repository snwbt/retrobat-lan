from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import PowerProcess
from app.services.power import PowerProcessManager, ProcessQuery
from tests.conftest import make_config


class FakePowerProcessManager(PowerProcessManager):
    def __init__(
        self,
        emulators: list[PowerProcess] | None = None,
        frontends: list[PowerProcess] | None = None,
        available: bool = True,
        stubborn: bool = False,
    ) -> None:
        self.emulators = emulators or []
        self.frontends = frontends or []
        self.available = available
        self.stubborn = stubborn
        self.graceful_closed: list[PowerProcess] = []
        self.force_killed: list[PowerProcess] = []

    def list_processes(self, process_names: list[str]) -> ProcessQuery:
        if not self.available:
            return ProcessQuery(available=False, warnings=["process manager unavailable"])
        wanted = {name.lower() for name in process_names}
        processes = [process for process in [*self.emulators, *self.frontends] if process.name.lower() in wanted]
        return ProcessQuery(processes=processes)

    def graceful_close(self, processes: list[PowerProcess]) -> tuple[list[PowerProcess], list[str]]:
        self.graceful_closed.extend(processes)
        if not self.stubborn:
            closed_pids = {process.pid for process in processes}
            self.emulators = [process for process in self.emulators if process.pid not in closed_pids]
        return processes, []

    def force_kill(self, processes: list[PowerProcess]) -> tuple[list[PowerProcess], list[str]]:
        self.force_killed.extend(processes)
        killed_pids = {process.pid for process in processes}
        self.emulators = [process for process in self.emulators if process.pid not in killed_pids]
        return processes, []


def emulator() -> PowerProcess:
    return PowerProcess(name="retroarch.exe", pid=123, exe="C:/RetroBat/retroarch.exe")


def frontend() -> PowerProcess:
    return PowerProcess(name="emulationstation.exe", pid=456, exe="C:/RetroBat/emulationstation.exe")


def test_power_config_defaults_are_safe(retrobat_root: Path) -> None:
    config = make_config(retrobat_root)

    assert config.safe_power_wait_seconds == 10
    assert config.allow_force_kill_emulators is False


def test_power_status_reports_safe_when_no_emulator_running(retrobat_root: Path) -> None:
    client = TestClient(create_app(make_config(retrobat_root), power_process_manager=FakePowerProcessManager()))

    response = client.get("/power/status")
    body = response.json()

    assert response.status_code == 200
    assert body["safe_to_shutdown"] is True
    assert body["emulator_running"] is False


def test_shutdown_safe_allows_dry_run_when_no_emulator_running(retrobat_root: Path) -> None:
    client = TestClient(create_app(make_config(retrobat_root), power_process_manager=FakePowerProcessManager()))

    response = client.post("/power/shutdown-safe?dry_run=true", headers={"X-Arcade-Token": "secret"})

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["dry_run"] is True


def test_shutdown_and_reboot_safe_block_when_emulator_remains_and_force_kill_disabled(retrobat_root: Path) -> None:
    config = make_config(retrobat_root)
    config.safe_power_wait_seconds = 0
    manager = FakePowerProcessManager(emulators=[emulator()], stubborn=True)
    client = TestClient(create_app(config, power_process_manager=manager))

    shutdown = client.post("/power/shutdown-safe?dry_run=true", headers={"X-Arcade-Token": "secret"})
    manager.emulators = [emulator()]
    reboot = client.post("/power/reboot-safe?dry_run=true", headers={"X-Arcade-Token": "secret"})

    assert shutdown.status_code == 200
    assert shutdown.json()["accepted"] is False
    assert shutdown.json()["remaining_emulator_processes"]
    assert reboot.json()["accepted"] is False
    assert manager.force_killed == []


def test_quit_current_game_closes_only_emulator_processes(retrobat_root: Path) -> None:
    manager = FakePowerProcessManager(emulators=[emulator()], frontends=[frontend()])
    client = TestClient(create_app(make_config(retrobat_root), power_process_manager=manager))

    response = client.post("/power/quit-current-game", headers={"X-Arcade-Token": "secret"})

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert [process.pid for process in manager.graceful_closed] == [123]
    assert manager.frontends == [frontend()]


def test_force_kill_path_requires_config_flag(retrobat_root: Path) -> None:
    config = make_config(retrobat_root)
    config.allow_force_kill_emulators = True
    config.safe_power_wait_seconds = 0
    manager = FakePowerProcessManager(emulators=[emulator()], stubborn=True)
    client = TestClient(create_app(config, power_process_manager=manager))

    response = client.post("/power/quit-current-game", headers={"X-Arcade-Token": "secret"})

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert [process.pid for process in manager.force_killed] == [123]


def test_power_responses_do_not_expose_token(retrobat_root: Path) -> None:
    config = make_config(retrobat_root, token="super-secret-token")
    client = TestClient(create_app(config, power_process_manager=FakePowerProcessManager()))

    status = client.get("/power/status")
    action = client.post("/power/quit-current-game", headers={"X-Arcade-Token": "super-secret-token"})

    assert "super-secret-token" not in status.text
    assert "super-secret-token" not in action.text
