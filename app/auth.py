from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from .config import AppConfig
from .logging_config import get_logger

logger = get_logger("auth")


def verify_arcade_token(config: AppConfig, token: str | None) -> None:
    expected = config.api_token
    if not token or not secrets.compare_digest(token, expected):
        logger.warning("auth_failure")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid arcade token.",
        )


def token_dependency(config: AppConfig):
    def _dependency(x_arcade_token: str | None = Header(default=None)) -> None:
        verify_arcade_token(config, x_arcade_token)

    return _dependency

