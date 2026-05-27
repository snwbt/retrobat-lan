from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastapi import HTTPException, status

from .config import AppConfig
from .logging_config import get_logger
from .models import Game, LaunchRequest, LaunchResult
from .scanner import WINDOWS_LAUNCH_EXTENSIONS, WINDOWS_NATIVE_SYSTEMS, GameIndex

logger = get_logger("launcher")


def process_running(process_names: list[str]) -> bool:
    wanted = {name.lower() for name in process_names}
    try:
        import psutil  # type: ignore

        for process in psutil.process_iter(["name"]):
            name = (process.info.get("name") or "").lower()
            if name in wanted:
                return True
        return False
    except Exception:
        return False


class LaunchStrategy:
    name = "base"

    def launch(self, request: LaunchRequest, game: Game | None) -> LaunchResult:
        raise NotImplementedError


class WindowsNativeLaunchStrategy(LaunchStrategy):
    name = "windows-native"

    def __init__(self, config: AppConfig):
        self.config = config

    def launch(self, request: LaunchRequest, game: Game | None) -> LaunchResult:
        if game is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found.")
        extension = Path(game.path).suffix.lower()
        if extension not in WINDOWS_LAUNCH_EXTENSIONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported launcher extension.")
        logger.info("launch_request strategy=windows-native system=%s path=%s dry_run=%s", game.system, game.path, request.dry_run)
        if request.dry_run:
            return LaunchResult(launched=False, dry_run=True, strategy=self.name, message="Dry run accepted.", game=game)
        if os.name == "nt":
            os.startfile(game.path)  # type: ignore[attr-defined]
        else:
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Windows native launch requires Windows.")
        return LaunchResult(launched=True, strategy=self.name, message="Launcher opened through Windows shell.", game=game)


class RetroBatLaunchStrategy(LaunchStrategy):
    name = "retrobat-placeholder"

    def __init__(self, config: AppConfig):
        self.config = config

    def launch(self, request: LaunchRequest, game: Game | None) -> LaunchResult:
        logger.info(
            "launch_request strategy=retrobat-placeholder system=%s path=%s dry_run=%s",
            request.system,
            game.path if game else None,
            request.dry_run,
        )
        if request.dry_run:
            return LaunchResult(
                launched=False,
                dry_run=True,
                strategy=self.name,
                message="Dry run accepted. RetroBat would be started if needed.",
                game=game,
            )
        if self.config.experimental_direct_es_launch:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Direct es_systems.cfg command launching is not implemented in the MVP.",
            )
        if self.config.retrobat_exe.exists() and not process_running(self.config.frontend_process_names):
            subprocess.Popen([str(self.config.retrobat_exe)], cwd=str(self.config.retrobat_root))
            return LaunchResult(
                launched=True,
                strategy=self.name,
                message="RetroBat started. Selected ROM metadata was logged but not directly launched.",
                game=game,
            )
        return LaunchResult(
            launched=False,
            strategy=self.name,
            message="RetroBat appears to be running or retrobat.exe was not found. Selected ROM metadata was logged.",
            game=game,
        )


class Launcher:
    def __init__(self, config: AppConfig, index: GameIndex):
        self.config = config
        self.index = index
        self.windows_strategy = WindowsNativeLaunchStrategy(config)
        self.retrobat_strategy = RetroBatLaunchStrategy(config)

    def launch(self, request: LaunchRequest) -> LaunchResult:
        game = self.index.find_game(request.system, request.path)
        if request.path and game is None:
            logger.warning("launch_rejected_missing_or_unsafe system=%s", request.system)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found or path is not indexed.")
        if request.system.lower() in WINDOWS_NATIVE_SYSTEMS:
            return self.windows_strategy.launch(request, game)
        return self.retrobat_strategy.launch(request, game)

