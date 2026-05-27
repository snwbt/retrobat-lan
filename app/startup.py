from __future__ import annotations

import os
import sys
from pathlib import Path


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_RUN_VALUE = "RetroBat Cab Commander"


def default_startup_command() -> str:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        return f'"{exe}"'
    return f'"{Path(sys.executable)}" -m app.cli'


class StartupManager:
    def is_enabled(self) -> bool:
        raise NotImplementedError

    def enable(self) -> None:
        raise NotImplementedError

    def disable(self) -> None:
        raise NotImplementedError


class WindowsRegistryStartupManager(StartupManager):
    def __init__(self, command: str | None = None):
        self.command = command or default_startup_command()

    def is_enabled(self) -> bool:
        if os.name != "nt":
            return False
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, APP_RUN_VALUE)
            return value == self.command
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def enable(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Start with Windows is only available on Windows.")
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_RUN_VALUE, 0, winreg.REG_SZ, self.command)

    def disable(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Start with Windows is only available on Windows.")
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP_RUN_VALUE)
        except FileNotFoundError:
            return
