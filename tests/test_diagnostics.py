from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.diagnostics import redact_text
from app.main import create_app
from tests.conftest import make_config


def test_redact_text_removes_tokens() -> None:
    text = 'api_token = "secret"\nGET /setup/bootstrap?code=abc123\nX-Arcade-Token: secret'

    redacted = redact_text(text)

    assert "secret" not in redacted
    assert "abc123" not in redacted
    assert "[REDACTED]" in redacted


def test_diagnostics_logs_are_redacted(retrobat_root: Path) -> None:
    config = make_config(retrobat_root, token="super-secret-token")
    config.log_dir.mkdir(parents=True, exist_ok=True)
    log = config.log_dir / "retrobat-cab-commander.log"
    log.write_text('api_token = "super-secret-token"\nnormal line\n', encoding="utf-8")
    client = TestClient(create_app(config))

    response = client.get("/diagnostics/logs", headers={"X-Arcade-Token": "super-secret-token"})

    assert response.status_code == 200
    assert "super-secret-token" not in response.text
    assert "normal line" in response.text


def test_diagnostics_bundle_redacts_secrets(retrobat_root: Path) -> None:
    config = make_config(retrobat_root, token="super-secret-token")
    client = TestClient(create_app(config))

    response = client.get("/diagnostics/bundle", headers={"X-Arcade-Token": "super-secret-token"})

    assert response.status_code == 200
    assert "super-secret-token" not in response.text
    assert "diagnostics" in response.text

