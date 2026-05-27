from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.now_playing import NowPlayingService, ProcessDetection, ProcessDetector
from tests.conftest import make_config


class FakeProcessDetector(ProcessDetector):
    def __init__(self, available: bool = True):
        self.available = available

    def detect(self, process_names: list[str]) -> ProcessDetection:
        return ProcessDetection(processes=[], available=self.available)


def add_arcade_game(root: Path) -> Path:
    rom = root / "roms" / "arcade" / "pacman.zip"
    rom.parent.mkdir(parents=True, exist_ok=True)
    rom.write_text("rom", encoding="utf-8")
    return rom


def make_client(root: Path, *, marquee_enabled: bool = True, detector_available: bool = False) -> TestClient:
    config = make_config(root)
    config.marquee_enabled = marquee_enabled
    service = NowPlayingService(config, process_detector=FakeProcessDetector(available=detector_available), state_path=root / "now-playing.json")
    return TestClient(create_app(config, now_playing_service=service))


def test_marquee_route_serves_display(retrobat_root: Path) -> None:
    client = make_client(retrobat_root)

    response = client.get("/marquee")
    js = client.get("/marquee.js")
    css = client.get("/marquee.css")

    assert response.status_code == 200
    assert "RetroBat Cab Commander Marquee" in response.text
    assert js.status_code == 200
    assert "loadMarquee" in js.text
    assert css.status_code == 200
    assert ".marquee-shell" in css.text


def test_marquee_state_no_active_game_uses_disabled_fallback(retrobat_root: Path) -> None:
    client = make_client(retrobat_root, marquee_enabled=False)

    response = client.get("/marquee/state")
    body = response.json()

    assert response.status_code == 200
    assert body["enabled"] is False
    assert body["source"] == "disabled"
    assert body["fallback_text"] == "Marquee disabled"


def test_marquee_state_uses_active_now_playing(retrobat_root: Path) -> None:
    rom = add_arcade_game(retrobat_root)
    client = make_client(retrobat_root, detector_available=False)
    client.post("/launch", headers={"X-Arcade-Token": "secret"}, json={"system": "arcade", "path": str(rom)})

    response = client.get("/marquee/state")
    body = response.json()

    assert response.status_code == 200
    assert body["enabled"] is True
    assert body["source"] == "now_playing"
    assert body["current_system"] == "arcade"
    assert body["current_game"] == "pacman"


def test_marquee_state_uses_last_launched_game_when_inactive(retrobat_root: Path) -> None:
    rom = add_arcade_game(retrobat_root)
    client = make_client(retrobat_root, detector_available=True)
    client.post("/launch", headers={"X-Arcade-Token": "secret"}, json={"system": "arcade", "path": str(rom)})

    response = client.get("/marquee/state")
    body = response.json()

    assert response.status_code == 200
    assert body["source"] == "last_launch"
    assert body["current_system"] == "arcade"
    assert body["current_game"] == "pacman"


def test_marquee_discovers_and_serves_local_artwork(retrobat_root: Path) -> None:
    rom = add_arcade_game(retrobat_root)
    artwork = retrobat_root / "roms" / "arcade" / "media" / "marquees" / "pacman.png"
    artwork.parent.mkdir(parents=True)
    artwork.write_bytes(b"\x89PNG\r\n\x1a\n")
    client = make_client(retrobat_root, detector_available=False)
    client.post("/launch", headers={"X-Arcade-Token": "secret"}, json={"system": "arcade", "path": str(rom)})

    state = client.get("/marquee/state").json()
    image = client.get(state["selected_artwork_url"])
    missing = client.get("/marquee/artwork/../../config.toml")

    assert state["selected_artwork_url"].startswith("/marquee/artwork/")
    assert image.status_code == 200
    assert image.content.startswith(b"\x89PNG")
    assert missing.status_code == 404


def test_marquee_discovers_gamelist_artwork(retrobat_root: Path) -> None:
    rom = add_arcade_game(retrobat_root)
    artwork = retrobat_root / "roms" / "arcade" / "media" / "wheels" / "pacman.png"
    artwork.parent.mkdir(parents=True)
    artwork.write_bytes(b"\x89PNG\r\n\x1a\n")
    (retrobat_root / "roms" / "arcade" / "gamelist.xml").write_text(
        """
<gameList>
  <game>
    <path>./pacman.zip</path>
    <wheel>./media/wheels/pacman.png</wheel>
  </game>
</gameList>
""",
        encoding="utf-8",
    )
    config = make_config(retrobat_root)
    config.marquee_enabled = True
    config.marquee_artwork_preference = ["wheel"]
    service = NowPlayingService(config, process_detector=FakeProcessDetector(available=False), state_path=retrobat_root / "now-playing.json")
    client = TestClient(create_app(config, now_playing_service=service))
    client.post("/launch", headers={"X-Arcade-Token": "secret"}, json={"system": "arcade", "path": str(rom)})

    state = client.get("/marquee/state").json()

    assert "wheel" in state["artwork_urls"]
    assert state["selected_artwork_url"] == state["artwork_urls"]["wheel"]


def test_marquee_rejects_unknown_artwork_id(retrobat_root: Path) -> None:
    client = make_client(retrobat_root)

    response = client.get("/marquee/artwork/not-registered")

    assert response.status_code == 404
