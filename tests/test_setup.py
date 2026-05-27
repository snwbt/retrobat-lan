from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import DEFAULT_API_TOKEN, AppConfig, ensure_config_file, load_config
from app.main import create_app
from app.startup import StartupManager


class FakeStartupManager(StartupManager):
    def __init__(self) -> None:
        self.enabled = False
        self.enable_calls = 0
        self.disable_calls = 0

    def is_enabled(self) -> bool:
        return self.enabled

    def enable(self) -> None:
        self.enable_calls += 1
        self.enabled = True

    def disable(self) -> None:
        self.disable_calls += 1
        self.enabled = False


def test_config_creation_when_missing_generates_token(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"

    path, token, created = ensure_config_file(config_path)
    config = load_config(path)

    assert created is True
    assert path == config_path
    assert token != DEFAULT_API_TOKEN
    assert config.api_token == token
    assert config.auto_detect_retrobat is True


def test_generated_token_not_returned_by_public_endpoints(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    _, token, _ = ensure_config_file(config_path)
    config = load_config(config_path)
    client = TestClient(create_app(config, startup_manager=FakeStartupManager()))

    assert token not in client.get("/status").text
    assert token not in client.get("/config/public").text


def test_setup_config_saves_only_allowed_fields(tmp_path: Path) -> None:
    retrobat = tmp_path / "RetroBat"
    (retrobat / "roms").mkdir(parents=True)
    config_path = tmp_path / "config.toml"
    config = AppConfig(
        retrobat_root=retrobat,
        configured_retrobat_root=retrobat,
        retrobat_root_valid=True,
        retrobat_root_source="config",
        api_token="secret",
        config_path=config_path,
        log_dir=tmp_path / "logs",
    )
    client = TestClient(create_app(config, startup_manager=FakeStartupManager()))

    response = client.post(
        "/setup/config",
        headers={"X-Arcade-Token": "secret"},
        json={
            "retrobat_root": str(retrobat),
            "auto_detect_retrobat": False,
            "bind_host": "127.0.0.1",
            "port": 9001,
            "api_token": "attacker",
        },
    )

    assert response.status_code == 200
    saved = config_path.read_text(encoding="utf-8")
    assert "api_token = \"secret\"" in saved
    assert "attacker" not in saved
    assert "port = 9001" in saved


def test_setup_config_rejects_invalid_path_when_auto_detect_disabled(tmp_path: Path) -> None:
    config = AppConfig(api_token="secret", config_path=tmp_path / "config.toml", log_dir=tmp_path / "logs")
    client = TestClient(create_app(config, startup_manager=FakeStartupManager()))

    response = client.post(
        "/setup/config",
        headers={"X-Arcade-Token": "secret"},
        json={"retrobat_root": str(tmp_path / "missing"), "auto_detect_retrobat": False},
    )

    assert response.status_code == 400


def test_setup_config_allows_invalid_path_when_auto_detect_enabled(tmp_path: Path) -> None:
    config = AppConfig(api_token="secret", config_path=tmp_path / "config.toml", log_dir=tmp_path / "logs")
    client = TestClient(create_app(config, startup_manager=FakeStartupManager()))

    response = client.post(
        "/setup/config",
        headers={"X-Arcade-Token": "secret"},
        json={"retrobat_root": str(tmp_path / "missing"), "auto_detect_retrobat": True},
    )

    assert response.status_code == 200


def test_startup_enable_disable_uses_manager(tmp_path: Path) -> None:
    manager = FakeStartupManager()
    config = AppConfig(api_token="secret", config_path=tmp_path / "config.toml", log_dir=tmp_path / "logs")
    client = TestClient(create_app(config, startup_manager=manager))

    enabled = client.post("/setup/startup/enable", headers={"X-Arcade-Token": "secret"})
    status = client.get("/setup/status", headers={"X-Arcade-Token": "secret"})
    disabled = client.post("/setup/startup/disable", headers={"X-Arcade-Token": "secret"})

    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
    assert status.json()["startup_enabled"] is True
    assert disabled.json()["enabled"] is False
    assert manager.enable_calls == 1
    assert manager.disable_calls == 1

