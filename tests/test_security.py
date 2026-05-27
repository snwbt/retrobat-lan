from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_config


def test_public_endpoints_do_not_return_api_token(retrobat_root: Path) -> None:
    config = make_config(retrobat_root, token="super-secret-token")
    client = TestClient(create_app(config))

    status_body = client.get("/status").text
    public_body = client.get("/config/public").text

    assert "super-secret-token" not in status_body
    assert "super-secret-token" not in public_body


def test_status_reports_resolved_retrobat_root_metadata(retrobat_root: Path) -> None:
    config = make_config(retrobat_root, token="super-secret-token")
    client = TestClient(create_app(config))

    response = client.get("/status")
    body = response.json()

    assert response.status_code == 200
    assert body["configured_retrobat_root"] == str(retrobat_root)
    assert body["resolved_retrobat_root"] == str(retrobat_root)
    assert body["retrobat_root_source"] == "config"
    assert body["retrobat_root_valid"] is True
    assert "super-secret-token" not in response.text


def test_launch_rejects_path_traversal(retrobat_root: Path, tmp_path: Path) -> None:
    windows = retrobat_root / "roms" / "windows"
    windows.mkdir(parents=True)
    (windows / "Good.bat").write_text("echo ok", encoding="utf-8")
    outside = tmp_path / "outside.bat"
    outside.write_text("echo bad", encoding="utf-8")
    client = TestClient(create_app(make_config(retrobat_root)))

    response = client.post(
        "/launch",
        headers={"X-Arcade-Token": "secret"},
        json={"system": "windows", "path": str(outside), "dry_run": True},
    )

    assert response.status_code == 404


def test_windows_bat_launch_allowed_only_when_indexed(retrobat_root: Path) -> None:
    windows = retrobat_root / "roms" / "windows"
    windows.mkdir(parents=True)
    launcher = windows / "Good.bat"
    launcher.write_text("echo ok", encoding="utf-8")
    client = TestClient(create_app(make_config(retrobat_root)))

    response = client.post(
        "/launch",
        headers={"X-Arcade-Token": "secret"},
        json={"system": "windows", "path": str(launcher), "dry_run": True},
    )

    assert response.status_code == 200
    assert response.json()["dry_run"] is True


def test_shutdown_and_reboot_support_dry_run(retrobat_root: Path) -> None:
    client = TestClient(create_app(make_config(retrobat_root)))

    shutdown = client.post("/shutdown?dry_run=true", headers={"X-Arcade-Token": "secret"})
    reboot = client.post("/reboot?dry_run=true", headers={"X-Arcade-Token": "secret"})

    assert shutdown.status_code == 200
    assert reboot.status_code == 200
    assert shutdown.json()["dry_run"] is True
    assert reboot.json()["dry_run"] is True
