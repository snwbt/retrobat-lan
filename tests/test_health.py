from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import AppConfig, ControllerPortConfig
from app.controls import ControllerDeviceProvider
from app.main import create_app
from app.models import ControllerDevice, PowerProcess
from app.services.power import PowerProcessManager, ProcessQuery
from app.startup import StartupManager
from tests.conftest import make_config


class FakeStartupManager(StartupManager):
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def is_enabled(self) -> bool:
        return self.enabled

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False


class FakeControllerProvider(ControllerDeviceProvider):
    def __init__(self, devices: list[ControllerDevice] | None = None, error: str | None = None) -> None:
        self._devices = devices or []
        self.last_error = error

    def list_devices(self) -> list[ControllerDevice]:
        return self._devices


class FakePowerProcessManager(PowerProcessManager):
    def __init__(self, available: bool = True) -> None:
        self.available = available

    def list_processes(self, process_names: list[str]) -> ProcessQuery:
        if not self.available:
            return ProcessQuery(available=False, warnings=["process detection unavailable"])
        return ProcessQuery()

    def graceful_close(self, processes: list[PowerProcess]) -> tuple[list[PowerProcess], list[str]]:
        return processes, []

    def force_kill(self, processes: list[PowerProcess]) -> tuple[list[PowerProcess], list[str]]:
        return processes, []


def device(path: str) -> ControllerDevice:
    return ControllerDevice(
        id=f"device-{path}",
        name="Zero Delay Encoder",
        usb_location_path=path,
        joystick_index=0,
        joystick_index_source="verified",
    )


def test_health_endpoint_redacts_secrets_and_reports_fields(retrobat_root: Path) -> None:
    config = make_config(retrobat_root, token="super-secret-token")
    client = TestClient(
        create_app(
            config,
            startup_manager=FakeStartupManager(enabled=True),
            controls_provider=FakeControllerProvider(),
            power_process_manager=FakePowerProcessManager(),
        )
    )

    response = client.get("/health")
    body = response.json()

    assert response.status_code == 200
    assert body["version"]
    assert body["resolved_retrobat_root"] == str(retrobat_root)
    assert body["last_scan_time"] is not None
    assert body["startup_available"] is True
    assert body["startup_enabled"] is True
    assert "super-secret-token" not in response.text


def test_health_missing_retrobat_root_produces_warning_or_error(tmp_path: Path) -> None:
    missing_root = tmp_path / "MissingRetroBat"
    config = AppConfig(
        retrobat_root=missing_root,
        configured_retrobat_root=missing_root,
        retrobat_root_source="config",
        retrobat_root_valid=False,
        auto_detect_retrobat=False,
        api_token="secret",
        log_dir=tmp_path / "logs",
    )
    client = TestClient(
        create_app(
            config,
            startup_manager=FakeStartupManager(),
            controls_provider=FakeControllerProvider(),
            power_process_manager=FakePowerProcessManager(),
        )
    )

    response = client.get("/health")
    body = response.json()

    assert response.status_code == 200
    assert body["severity"] == "error"
    assert any(check["key"] == "retrobat_root" and check["severity"] == "error" for check in body["checks"])


def test_health_last_scan_time_updates_after_rescan(retrobat_root: Path) -> None:
    client = TestClient(
        create_app(
            make_config(retrobat_root),
            startup_manager=FakeStartupManager(),
            controls_provider=FakeControllerProvider(),
            power_process_manager=FakePowerProcessManager(),
        )
    )
    before = client.get("/health").json()["last_scan_time"]
    time.sleep(0.01)

    rescan = client.post("/rescan", headers={"X-Arcade-Token": "secret"})
    after = client.get("/health").json()["last_scan_time"]

    assert rescan.status_code == 200
    assert before is not None
    assert after is not None
    assert after != before


def test_health_process_checks_degrade_when_process_detection_unavailable(retrobat_root: Path) -> None:
    client = TestClient(
        create_app(
            make_config(retrobat_root),
            startup_manager=FakeStartupManager(),
            controls_provider=FakeControllerProvider(),
            power_process_manager=FakePowerProcessManager(available=False),
        )
    )

    body = client.get("/health").json()

    assert body["process_detection_available"] is False
    assert any(check["key"] == "processes" and check["severity"] == "warning" for check in body["checks"])


def test_health_disk_check_degrades_when_disk_usage_fails(retrobat_root: Path) -> None:
    def failing_disk_usage(path):
        raise OSError("disk unavailable")

    client = TestClient(
        create_app(
            make_config(retrobat_root),
            startup_manager=FakeStartupManager(),
            controls_provider=FakeControllerProvider(),
            power_process_manager=FakePowerProcessManager(),
            health_disk_usage=failing_disk_usage,
        )
    )

    body = client.get("/health").json()

    assert body["disk_free_bytes"] is None
    assert any(check["key"] == "disk_space" and check["severity"] == "error" for check in body["checks"])


def test_health_controller_summary_hides_usb_paths_and_token(retrobat_root: Path) -> None:
    config = make_config(retrobat_root, token="super-secret-token")
    config.controller_ports["player1"] = ControllerPortConfig(label="Player 1", usb_location_path="USBROOT(0)#USB(1)")
    config.controller_ports["player2"] = ControllerPortConfig(label="Player 2", usb_location_path="USBROOT(0)#USB(2)")
    provider = FakeControllerProvider([device("USBROOT(0)#USB(1)")])
    client = TestClient(
        create_app(
            config,
            startup_manager=FakeStartupManager(),
            controls_provider=provider,
            power_process_manager=FakePowerProcessManager(),
        )
    )

    response = client.get("/health")
    body = response.json()

    assert response.status_code == 200
    assert body["controller_lock_available"] is True
    assert body["controller_configured_players"] == 2
    assert body["controller_connected_players"] == 1
    assert "USBROOT" not in response.text
    assert "super-secret-token" not in response.text
