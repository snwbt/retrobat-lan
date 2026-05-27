from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import ControllerPortConfig
from app.controls import ControllerDeviceProvider, RetroArchConfigPatcher
from app.main import create_app
from app.models import ControllerDevice
from tests.conftest import make_config


class FakeControllerProvider(ControllerDeviceProvider):
    def __init__(self, devices: list[ControllerDevice]):
        self._devices = devices

    def list_devices(self) -> list[ControllerDevice]:
        return self._devices


def device(name: str, path: str, index: int | None) -> ControllerDevice:
    return ControllerDevice(
        id=f"{name}-{path}",
        name=name,
        vendor_id="1234",
        product_id="5678",
        instance_id=f"HID\\VID_1234&PID_5678\\{path}",
        container_id=f"container-{path}",
        usb_location_path=path,
        location_info=path,
        joystick_index=index,
    )


def test_assign_uses_usb_location_path_not_device_name(retrobat_root: Path, tmp_path: Path) -> None:
    config = make_config(retrobat_root)
    config.config_path = tmp_path / "config.toml"
    provider = FakeControllerProvider(
        [
            device("Zero Delay Encoder", "USBROOT(0)#USB(1)", 0),
            device("Zero Delay Encoder", "USBROOT(0)#USB(2)", 1),
        ]
    )
    client = TestClient(create_app(config, controls_provider=provider))

    response = client.post(
        "/controls/assign",
        headers={"X-Arcade-Token": "secret"},
        json={"player": "player1", "usb_location_path": "USBROOT(0)#USB(2)"},
    )

    assert response.status_code == 200
    assert config.controller_ports["player1"].usb_location_path == "USBROOT(0)#USB(2)"
    saved = config.config_path.read_text(encoding="utf-8")
    assert "[controller_ports.player1]" in saved
    assert 'usb_location_path = "USBROOT(0)#USB(2)"' in saved


def test_verify_duplicate_same_index_reports_error(retrobat_root: Path) -> None:
    config = make_config(retrobat_root)
    config.controller_ports["player1"] = ControllerPortConfig(label="Player 1", usb_location_path="USBROOT(0)#USB(1)")
    config.controller_ports["player2"] = ControllerPortConfig(label="Player 2", usb_location_path="USBROOT(0)#USB(2)")
    provider = FakeControllerProvider(
        [
            device("Zero Delay Encoder", "USBROOT(0)#USB(1)", 0),
            device("Zero Delay Encoder", "USBROOT(0)#USB(2)", 0),
        ]
    )
    client = TestClient(create_app(config, controls_provider=provider))

    response = client.post("/controls/verify", headers={"X-Arcade-Token": "secret"})

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "Both encoders are being reported as the same controller" in response.text


def test_retroarch_patch_updates_only_player_indexes(tmp_path: Path) -> None:
    cfg = tmp_path / "retroarch.cfg"
    cfg.write_text(
        'video_fullscreen = "true"\ninput_player1_joypad_index = "7"\nmenu_driver = "xmb"\n',
        encoding="utf-8",
    )

    backup = RetroArchConfigPatcher(cfg).patch_player_indexes(0, 1)
    first_backup_text = backup.read_text(encoding="utf-8")  # type: ignore[union-attr]
    RetroArchConfigPatcher(cfg).patch_player_indexes(2, 3)

    text = cfg.read_text(encoding="utf-8")
    assert 'video_fullscreen = "true"' in text
    assert 'menu_driver = "xmb"' in text
    assert 'input_player1_joypad_index = "2"' in text
    assert 'input_player2_joypad_index = "3"' in text
    assert first_backup_text == backup.read_text(encoding="utf-8")  # type: ignore[union-attr]


def test_repair_retroarch_writes_mapping(retrobat_root: Path) -> None:
    retroarch = retrobat_root / "emulators" / "retroarch" / "retroarch.cfg"
    retroarch.parent.mkdir(parents=True)
    retroarch.write_text('input_driver = "dinput"\n', encoding="utf-8")
    config = make_config(retrobat_root)
    config.controller_ports["player1"] = ControllerPortConfig(label="Player 1", usb_location_path="USBROOT(0)#USB(1)")
    config.controller_ports["player2"] = ControllerPortConfig(label="Player 2", usb_location_path="USBROOT(0)#USB(2)")
    provider = FakeControllerProvider(
        [
            device("Zero Delay Encoder", "USBROOT(0)#USB(1)", 0),
            device("Zero Delay Encoder", "USBROOT(0)#USB(2)", 1),
        ]
    )
    client = TestClient(create_app(config, controls_provider=provider))

    response = client.post("/controls/repair-retroarch", headers={"X-Arcade-Token": "secret"})

    assert response.status_code == 200
    assert response.json()["repaired"] is True
    text = retroarch.read_text(encoding="utf-8")
    assert 'input_player1_joypad_index = "0"' in text
    assert 'input_player2_joypad_index = "1"' in text
    assert retroarch.with_name("retroarch.cfg.retrobat-cab-commander.bak").exists()


def test_launch_blocks_when_player1_missing(retrobat_root: Path) -> None:
    windows = retrobat_root / "roms" / "windows"
    windows.mkdir(parents=True)
    launcher = windows / "Good.bat"
    launcher.write_text("echo ok", encoding="utf-8")
    config = make_config(retrobat_root)
    config.controller_ports["player1"] = ControllerPortConfig(label="Player 1", usb_location_path="USBROOT(0)#USB(1)")
    provider = FakeControllerProvider([])
    client = TestClient(create_app(config, controls_provider=provider))

    response = client.post(
        "/launch",
        headers={"X-Arcade-Token": "secret"},
        json={"system": "windows", "path": str(launcher), "dry_run": True},
    )

    assert response.status_code == 409
    assert "Player 1 encoder not detected" in response.text

