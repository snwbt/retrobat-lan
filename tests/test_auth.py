from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_config


def test_get_endpoints_do_not_require_token(retrobat_root: Path) -> None:
    client = TestClient(create_app(make_config(retrobat_root)))

    assert client.get("/status").status_code == 200
    assert client.get("/config/public").status_code == 200
    assert client.get("/version").status_code == 200
    assert client.get("/systems").status_code == 200
    assert client.get("/search?q=mario").status_code == 200


def test_post_endpoints_require_token(retrobat_root: Path) -> None:
    client = TestClient(create_app(make_config(retrobat_root)))

    for path in [
        "/rescan",
        "/launch",
        "/game/random",
        "/shutdown",
        "/reboot",
        "/setup/config",
        "/setup/startup/enable",
        "/setup/startup/disable",
        "/controls/assign",
        "/controls/verify",
        "/controls/repair-retroarch",
    ]:
        response = client.post(path, json={})
        assert response.status_code == 401


def test_setup_status_requires_token(retrobat_root: Path) -> None:
    client = TestClient(create_app(make_config(retrobat_root)))

    assert client.get("/setup/status").status_code == 401
    assert client.get("/setup/status", headers={"X-Arcade-Token": "secret"}).status_code == 200
    assert client.get("/setup/folders").status_code == 401
    assert client.get("/setup/folders", headers={"X-Arcade-Token": "secret"}).status_code == 200


def test_controls_get_endpoints_require_token(retrobat_root: Path) -> None:
    client = TestClient(create_app(make_config(retrobat_root)))

    assert client.get("/controls/status").status_code == 401
    assert client.get("/controls/devices").status_code == 401
    assert client.get("/diagnostics/status").status_code == 401
    assert client.get("/diagnostics/logs").status_code == 401
    assert client.get("/diagnostics/bundle").status_code == 401


def test_post_endpoint_accepts_valid_token(retrobat_root: Path) -> None:
    client = TestClient(create_app(make_config(retrobat_root, token="secret")))

    response = client.post("/rescan", headers={"X-Arcade-Token": "secret"})

    assert response.status_code == 200
