from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("retrobat_cab_commander")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return

    log_path = log_dir / "retrobat-cab-commander.log"
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"retrobat_cab_commander.{name}")

