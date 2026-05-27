from __future__ import annotations

import secrets


class BootstrapTokenStore:
    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}

    def issue(self, token: str) -> str:
        code = secrets.token_urlsafe(24)
        self._tokens[code] = token
        return code

    def consume(self, code: str) -> str | None:
        return self._tokens.pop(code, None)

