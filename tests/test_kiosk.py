from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_config


def test_existing_dashboard_remains_available(retrobat_root) -> None:
    client = TestClient(create_app(make_config(retrobat_root)))

    response = client.get("/")

    assert response.status_code == 200
    assert "RetroBat Cab Commander" in response.text
    assert "/app.js" in response.text
    assert "Health" in response.text
    assert "/marquee" in response.text


def test_dashboard_assets_include_health_loader(retrobat_root) -> None:
    client = TestClient(create_app(make_config(retrobat_root)))

    response = client.get("/app.js")

    assert response.status_code == 200
    assert 'api("/health")' in response.text
    assert "loadHealth" in response.text
    assert 'api("/marquee/state")' in response.text
    assert "loadMarqueeStatus" in response.text


def test_kiosk_route_serves_dashboard(retrobat_root) -> None:
    client = TestClient(create_app(make_config(retrobat_root)))

    response = client.get("/kiosk")

    assert response.status_code == 200
    assert "RetroBat Cab Commander Kiosk" in response.text
    assert "/kiosk.css" in response.text
    assert "/kiosk.js" in response.text
    assert "data-focusable" in response.text


def test_kiosk_assets_are_served(retrobat_root) -> None:
    client = TestClient(create_app(make_config(retrobat_root)))

    js = client.get("/kiosk.js")
    css = client.get("/kiosk.css")

    assert js.status_code == 200
    assert "FocusManager" in js.text or "moveFocus" in js.text
    assert css.status_code == 200
    assert ".focused" in css.text


def test_kiosk_does_not_weaken_protected_actions(retrobat_root) -> None:
    client = TestClient(create_app(make_config(retrobat_root)))

    for path in ["/launch", "/game/random", "/shutdown", "/reboot", "/now-playing/clear", "/power/quit-current-game", "/power/shutdown-safe", "/power/reboot-safe"]:
        assert client.post(path, json={}).status_code == 401
