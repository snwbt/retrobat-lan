from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import LaunchRuleConfig
from app.main import create_app
from tests.conftest import make_config


def write_game(retrobat_root: Path, system: str = "arcade", name: str = "Game.zip") -> Path:
    folder = retrobat_root / "roms" / system
    folder.mkdir(parents=True, exist_ok=True)
    game = folder / name
    game.write_text("game", encoding="utf-8")
    return game


def launch(client: TestClient, system: str, path: Path | None, dry_run: bool = True):
    payload = {"system": system, "dry_run": dry_run}
    if path is not None:
        payload["path"] = str(path)
    return client.post("/launch", headers={"X-Arcade-Token": "secret"}, json=payload)


def test_per_system_shell_launch_selected(retrobat_root: Path) -> None:
    game = write_game(retrobat_root)
    config = make_config(retrobat_root)
    config.launch_rules["arcade"] = LaunchRuleConfig(mode="shell")
    client = TestClient(create_app(config))

    response = launch(client, "arcade", game)

    assert response.status_code == 200
    assert response.json()["strategy"] == "windows-native"
    assert response.json()["dry_run"] is True


def test_disabled_mode_blocks_launch(retrobat_root: Path) -> None:
    game = write_game(retrobat_root)
    config = make_config(retrobat_root)
    config.launch_rules["arcade"] = LaunchRuleConfig(mode="disabled")
    client = TestClient(create_app(config))

    response = launch(client, "arcade", game)

    assert response.status_code == 403
    assert "disabled" in response.text


def test_unknown_launch_mode_warns_and_blocks(retrobat_root: Path) -> None:
    game = write_game(retrobat_root, system="steam", name="Game.url")
    config = make_config(retrobat_root)
    config.launch_rules["steam"] = LaunchRuleConfig(mode="steam_uri")
    client = TestClient(create_app(config))

    launch_response = launch(client, "steam", game)
    systems = client.get("/systems").json()
    diagnostics = client.get("/diagnostics/status", headers={"X-Arcade-Token": "secret"}).json()
    health = client.get("/health").json()

    assert launch_response.status_code == 400
    assert "steam_uri" in launch_response.text
    assert next(system for system in systems if system["name"] == "steam")["launch_warning"]
    assert any("steam_uri" in warning for warning in diagnostics["warnings"])
    assert any(check["key"] == "launch_rules" and "steam_uri" in check["message"] for check in health["checks"])


def test_dry_run_only_accepts_dry_run_and_blocks_real_launch(retrobat_root: Path) -> None:
    game = write_game(retrobat_root)
    config = make_config(retrobat_root)
    config.launch_rules["arcade"] = LaunchRuleConfig(mode="dry_run_only")
    client = TestClient(create_app(config))

    dry_run = launch(client, "arcade", game, dry_run=True)
    real = launch(client, "arcade", game, dry_run=False)

    assert dry_run.status_code == 200
    assert dry_run.json()["strategy"] == "dry-run-only"
    assert dry_run.json()["dry_run"] is True
    assert real.status_code == 403


def test_default_launch_behavior_unchanged(retrobat_root: Path) -> None:
    windows_game = write_game(retrobat_root, system="windows", name="Game.bat")
    arcade_game = write_game(retrobat_root, system="arcade", name="Game.zip")
    client = TestClient(create_app(make_config(retrobat_root)))

    windows = launch(client, "windows", windows_game)
    arcade = launch(client, "arcade", arcade_game)

    assert windows.status_code == 200
    assert windows.json()["strategy"] == "windows-native"
    assert arcade.status_code == 200
    assert arcade.json()["strategy"] == "retrobat-placeholder"


def test_shell_launch_blocks_missing_indexed_target(retrobat_root: Path) -> None:
    game = write_game(retrobat_root, system="arcade", name="Game.zip")
    config = make_config(retrobat_root)
    config.launch_rules["arcade"] = LaunchRuleConfig(mode="shell")
    client = TestClient(create_app(config))
    game.unlink()

    response = launch(client, "arcade", game)

    assert response.status_code == 404
    assert "does not exist" in response.text
