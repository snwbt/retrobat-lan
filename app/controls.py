from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from fastapi import HTTPException, status

from .config import AppConfig, ControllerPortConfig, config_to_writable_data, write_config_data
from .logging_config import get_logger
from .models import (
    ControllerDevice,
    ControllerPortAssignment,
    ControlsAssignRequest,
    ControlsRepairResponse,
    ControlsStatusResponse,
    ControlsVerifyResponse,
    PlayerMapping,
)

logger = get_logger("controls")


VID_PID_RE = re.compile(r"VID_([0-9A-Fa-f]{4}).*PID_([0-9A-Fa-f]{4})")


def parse_vid_pid(instance_id: str | None) -> tuple[str | None, str | None]:
    if not instance_id:
        return None, None
    match = VID_PID_RE.search(instance_id)
    if not match:
        return None, None
    return match.group(1).upper(), match.group(2).upper()


class ControllerDeviceProvider:
    def list_devices(self) -> list[ControllerDevice]:
        raise NotImplementedError


class WindowsControllerDeviceProvider(ControllerDeviceProvider):
    def list_devices(self) -> list[ControllerDevice]:
        if os.name != "nt":
            return []
        script = r"""
$items = Get-CimInstance Win32_PnPEntity |
  Where-Object {
    $_.PNPDeviceID -match 'VID_' -and
    ($_.Name -match 'controller|gamepad|joystick|arcade|HID-compliant game controller|USB Input Device' -or $_.PNPClass -eq 'HIDClass')
  }
$out = @()
$index = 0
foreach ($item in $items) {
  $locationPaths = $null
  $locationInfo = $null
  $containerId = $null
  try { $locationPaths = (Get-PnpDeviceProperty -InstanceId $item.PNPDeviceID -KeyName 'DEVPKEY_Device_LocationPaths' -ErrorAction Stop).Data } catch {}
  try { $locationInfo = (Get-PnpDeviceProperty -InstanceId $item.PNPDeviceID -KeyName 'DEVPKEY_Device_LocationInfo' -ErrorAction Stop).Data } catch {}
  try { $containerId = (Get-PnpDeviceProperty -InstanceId $item.PNPDeviceID -KeyName 'DEVPKEY_Device_ContainerId' -ErrorAction Stop).Data } catch {}
  $locationPath = ''
  if ($locationPaths -is [array] -and $locationPaths.Length -gt 0) { $locationPath = [string]$locationPaths[0] }
  elseif ($locationPaths) { $locationPath = [string]$locationPaths }
  $out += [pscustomobject]@{
    Name = $item.Name
    PNPDeviceID = $item.PNPDeviceID
    ContainerID = [string]$containerId
    LocationPath = $locationPath
    LocationInfo = [string]$locationInfo
    JoystickIndex = $index
  }
  $index++
}
$out | ConvertTo-Json -Depth 4
"""
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                check=False,
                capture_output=True,
                text=True,
                timeout=8,
            )
        except OSError:
            return []
        if result.returncode != 0 or not result.stdout.strip():
            return []
        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning("controls_enumeration_json_failed")
            return []
        items = raw if isinstance(raw, list) else [raw]
        devices: list[ControllerDevice] = []
        for idx, item in enumerate(items):
            instance_id = str(item.get("PNPDeviceID") or "")
            vendor_id, product_id = parse_vid_pid(instance_id)
            location_path = str(item.get("LocationPath") or item.get("LocationInfo") or instance_id)
            if not location_path:
                continue
            devices.append(
                ControllerDevice(
                    id=instance_id or location_path,
                    name=str(item.get("Name") or "Unknown controller"),
                    vendor_id=vendor_id,
                    product_id=product_id,
                    instance_id=instance_id or None,
                    container_id=str(item.get("ContainerID") or "") or None,
                    usb_location_path=location_path,
                    location_info=str(item.get("LocationInfo") or "") or None,
                    joystick_index=item.get("JoystickIndex", idx),
                )
            )
        return devices


class RetroArchConfigPatcher:
    def __init__(self, path: Path):
        self.path = path
        self.backup_path = path.with_name(f"{path.name}.retrobat-cab-commander.bak")

    def patch_player_indexes(self, player1_index: int, player2_index: int | None = None) -> Path | None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and not self.backup_path.exists():
            shutil.copy2(self.path, self.backup_path)

        lines = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
        updates = {"input_player1_joypad_index": str(player1_index)}
        if player2_index is not None:
            updates["input_player2_joypad_index"] = str(player2_index)
        seen: set[str] = set()
        output: list[str] = []
        for line in lines:
            key = line.split("=", 1)[0].strip() if "=" in line else ""
            if key in updates:
                output.append(f'{key} = "{updates[key]}"')
                seen.add(key)
            else:
                output.append(line)
        for key, value in updates.items():
            if key not in seen:
                output.append(f'{key} = "{value}"')
        self.path.write_text("\n".join(output) + "\n", encoding="utf-8")
        return self.backup_path if self.backup_path.exists() else None


class ControlsService:
    def __init__(self, config: AppConfig, provider: ControllerDeviceProvider | None = None):
        self.config = config
        self.provider = provider or WindowsControllerDeviceProvider()

    @property
    def retroarch_config_path(self) -> Path:
        return self.config.retrobat_root / "emulators" / "retroarch" / "retroarch.cfg"

    def is_configured(self) -> bool:
        return any(port.usb_location_path for port in self.config.controller_ports.values())

    def devices(self) -> list[ControllerDevice]:
        return self.provider.list_devices()

    def status(self) -> ControlsStatusResponse:
        devices = self.devices()
        return ControlsStatusResponse(
            enabled=self.config.controls_enabled,
            auto_repair_on_launch=self.config.controls_auto_repair_on_launch,
            retroarch_config_path=str(self.retroarch_config_path),
            retroarch_config_exists=self.retroarch_config_path.exists(),
            assignments=self._assignments(devices),
            devices=devices,
        )

    def assign(self, request: ControlsAssignRequest) -> ControlsStatusResponse:
        player = request.player.lower().strip()
        if player not in {"player1", "player2"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="player must be player1 or player2.")
        matching = [device for device in self.devices() if device.usb_location_path == request.usb_location_path]
        if not matching:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USB location path is not currently detected.")
        current = self.config.controller_ports.get(player) or ControllerPortConfig()
        self.config.controller_ports[player] = ControllerPortConfig(
            label=request.label or current.label or ("Player 1" if player == "player1" else "Player 2"),
            usb_location_path=request.usb_location_path,
        )
        if self.config.config_path:
            write_config_data(self.config.config_path, config_to_writable_data(self.config))
        return self.status()

    def verify(self) -> ControlsVerifyResponse:
        devices = self.devices()
        errors: list[str] = []
        mappings: list[PlayerMapping] = []
        for player in ["player1", "player2"]:
            configured = self.config.controller_ports.get(player)
            if not configured or not configured.usb_location_path:
                continue
            device = self._device_for_path(devices, configured.usb_location_path)
            if not device:
                errors.append(f"{configured.label or player} encoder not detected on configured USB port")
                mappings.append(PlayerMapping(player=player, usb_location_path=configured.usb_location_path))
                continue
            mappings.append(
                PlayerMapping(
                    player=player,
                    usb_location_path=configured.usb_location_path,
                    joystick_index=device.joystick_index,
                    device_name=device.name,
                )
            )
            if device.joystick_index is None:
                errors.append(f"{configured.label or player} joystick index is unavailable")

        player1 = next((mapping for mapping in mappings if mapping.player == "player1"), None)
        player2 = next((mapping for mapping in mappings if mapping.player == "player2"), None)
        if self.config.controller_ports.get("player1", ControllerPortConfig()).usb_location_path and not player1:
            errors.append("Player 1 encoder not detected on configured USB port")
        if player1 and player2 and player1.joystick_index is not None and player1.joystick_index == player2.joystick_index:
            errors.append("Both encoders are being reported as the same controller")
        return ControlsVerifyResponse(ok=not errors, errors=errors, mappings=mappings)

    def repair_retroarch(self) -> ControlsRepairResponse:
        verify = self.verify()
        if not verify.ok:
            return ControlsRepairResponse(
                repaired=False,
                verify=verify,
                retroarch_config_path=str(self.retroarch_config_path),
            )
        player1 = next((mapping for mapping in verify.mappings if mapping.player == "player1"), None)
        player2 = next((mapping for mapping in verify.mappings if mapping.player == "player2"), None)
        if not player1 or player1.joystick_index is None:
            verify.errors.append("Player 1 encoder not detected on configured USB port")
            verify.ok = False
            return ControlsRepairResponse(
                repaired=False,
                verify=verify,
                retroarch_config_path=str(self.retroarch_config_path),
            )
        patcher = RetroArchConfigPatcher(self.retroarch_config_path)
        backup = patcher.patch_player_indexes(
            player1.joystick_index,
            player2.joystick_index if player2 and player2.joystick_index is not None else None,
        )
        logger.info(
            "controls_repair_retroarch player1=%s player2=%s path=%s",
            player1.joystick_index,
            player2.joystick_index if player2 else None,
            self.retroarch_config_path,
        )
        return ControlsRepairResponse(
            repaired=True,
            verify=verify,
            retroarch_config_path=str(self.retroarch_config_path),
            backup_path=str(backup) if backup else None,
        )

    def ensure_launch_ready(self) -> None:
        if not self.config.controls_enabled or not self.config.controls_auto_repair_on_launch or not self.is_configured():
            return
        repair = self.repair_retroarch()
        if not repair.repaired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "Controller port verification failed.", "errors": repair.verify.errors},
            )

    def _assignments(self, devices: list[ControllerDevice]) -> list[ControllerPortAssignment]:
        assignments = []
        for player in ["player1", "player2"]:
            port = self.config.controller_ports.get(player) or ControllerPortConfig(label=player)
            assignments.append(
                ControllerPortAssignment(
                    player=player,
                    label=port.label or player,
                    usb_location_path=port.usb_location_path,
                    device=self._device_for_path(devices, port.usb_location_path) if port.usb_location_path else None,
                )
            )
        return assignments

    @staticmethod
    def _device_for_path(devices: list[ControllerDevice], location_path: str) -> ControllerDevice | None:
        return next((device for device in devices if device.usb_location_path == location_path), None)

