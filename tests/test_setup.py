from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import DEFAULT_API_TOKEN, AppConfig, ensure_config_file, load_config
from app.bootstrap import BootstrapTokenStore
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


def test_bootstrap_page_can_store_token_without_public_leak(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    _, token, _ = ensure_config_file(config_path)
    config = load_config(config_path)
    bootstrap_store = BootstrapTokenStore()
    code = bootstrap_store.issue(token)
    client = TestClient(create_app(config, startup_manager=FakeStartupManager(), bootstrap_store=bootstrap_store))

    bootstrap = client.get(f"/setup/bootstrap?code={code}")

    assert bootstrap.status_code == 200
    assert "localStorage.setItem" in bootstrap.text
    assert token in bootstrap.text
    assert code not in bootstrap.text
    assert token not in client.get("/status").text
    assert token not in client.get("/config/public").text


def test_bootstrap_code_reuse_fails(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    _, token, _ = ensure_config_file(config_path)
    config = load_config(config_path)
    bootstrap_store = BootstrapTokenStore()
    code = bootstrap_store.issue(token)
    client = TestClient(create_app(config, startup_manager=FakeStartupManager(), bootstrap_store=bootstrap_store))

    assert client.get(f"/setup/bootstrap?code={code}").status_code == 200
    assert client.get(f"/setup/bootstrap?code={code}").status_code == 404


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


def test_setup_config_rescans_selected_retrobat_root(tmp_path: Path) -> None:
    retrobat = tmp_path / "RetroBat"
    (retrobat / "roms" / "arcade").mkdir(parents=True)
    (retrobat / "roms" / "arcade" / "pacman.zip").write_text("rom", encoding="utf-8")
    config = AppConfig(api_token="secret", config_path=tmp_path / "config.toml", log_dir=tmp_path / "logs")
    client = TestClient(create_app(config, startup_manager=FakeStartupManager()))

    response = client.post(
        "/setup/config",
        headers={"X-Arcade-Token": "secret"},
        json={"retrobat_root": str(retrobat), "auto_detect_retrobat": False},
    )

    assert response.status_code == 200
    assert response.json()["indexed_game_count"] == 1
    assert response.json()["indexed_system_count"] == 1


def test_folder_browser_lists_directories_only(tmp_path: Path) -> None:
    root = tmp_path / "browse"
    (root / "RetroBat" / "roms").mkdir(parents=True)
    (root / "file.txt").write_text("ignore", encoding="utf-8")
    config = AppConfig(api_token="secret", config_path=tmp_path / "config.toml", log_dir=tmp_path / "logs")
    client = TestClient(create_app(config, startup_manager=FakeStartupManager()))

    response = client.get("/setup/folders", headers={"X-Arcade-Token": "secret"}, params={"path": str(root)})

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["directories"]]
    assert names == ["RetroBat"]
    assert response.json()["directories"][0]["valid_retrobat_root"] is True


def test_folder_browser_handles_missing_path(tmp_path: Path) -> None:
    config = AppConfig(api_token="secret", config_path=tmp_path / "config.toml", log_dir=tmp_path / "logs")
    client = TestClient(create_app(config, startup_manager=FakeStartupManager()))

    response = client.get(
        "/setup/folders",
        headers={"X-Arcade-Token": "secret"},
        params={"path": str(tmp_path / "missing")},
    )

    assert response.status_code == 200
    assert response.json()["directories"] == []
    assert response.json()["error"]


def test_folder_browser_caps_large_directory_listing(tmp_path: Path) -> None:
    root = tmp_path / "many"
    root.mkdir()
    for index in range(210):
        (root / f"folder-{index:03d}").mkdir()
    config = AppConfig(api_token="secret", config_path=tmp_path / "config.toml", log_dir=tmp_path / "logs")
    client = TestClient(create_app(config, startup_manager=FakeStartupManager()))

    response = client.get("/setup/folders", headers={"X-Arcade-Token": "secret"}, params={"path": str(root)})

    assert response.status_code == 200
    assert len(response.json()["directories"]) == 200
    assert response.json()["truncated"] is True


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
