from __future__ import annotations

import subprocess

from .logging_config import get_logger
from .models import PowerResult

logger = get_logger("system_control")


def shutdown(dry_run: bool = False) -> PowerResult:
    logger.warning("power_request action=shutdown dry_run=%s", dry_run)
    if dry_run:
        return PowerResult(accepted=False, action="shutdown", dry_run=True, message="Dry run accepted.")
    subprocess.Popen(["shutdown", "/s", "/t", "0"])
    return PowerResult(accepted=True, action="shutdown", message="Shutdown requested.")


def reboot(dry_run: bool = False) -> PowerResult:
    logger.warning("power_request action=reboot dry_run=%s", dry_run)
    if dry_run:
        return PowerResult(accepted=False, action="reboot", dry_run=True, message="Dry run accepted.")
    subprocess.Popen(["shutdown", "/r", "/t", "0"])
    return PowerResult(accepted=True, action="reboot", message="Reboot requested.")

