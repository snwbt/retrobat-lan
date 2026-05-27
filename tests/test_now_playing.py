from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import DetectedProcess
from app.services.now_playing import NowPlayingService, ProcessDetection, ProcessDetector
from tests.conftest import make_config


class FakeProcessDetector(ProcessDetector):
    def __init__(self, processes: list[DetectedProcess] | None = None, available: bool = True):
        self._processes = processes or []
        self._available = available

    def detect(self, process_names: list[str]) -> ProcessDetection:
        return ProcessDetection(processes=self._processes, available=self._available)


def make_now_playing_service(root: Path, detector: ProcessDetector) -> NowPlayingService:
    config = make_config(root)
    return NowPlayingService(config, process_detector=detector, state_path=root / "now-playing.json")


def add_arcade_game(root: Path) -> Path:
    rom = root / "roms" / "arcade" / "pacman.zip"
    rom.parent.mkdir(parents=True, exist_ok=True)
    rom.write_text("rom", encoding="utf-8")
    return rom


def test_now_playing_returns_inactive_before_launch(retrobat_root: Path) -> None:
    service = make_now_playing_service(retrobat_root, FakeProcessDetector())
    client = TestClient(create_app(make_config(retrobat_root), now_playing_service=service))

    response = client.get("/now-playing")

    assert response.status_code == 200
    assert response.json()["active"] is False
    assert response.json()["session"] is None


def test_launch_creates_persistent_now_playing_session(retrobat_root: Path) -> None:
    rom = add_arcade_game(retrobat_root)
    service = make_now_playing_service(retrobat_root, FakeProcessDetector(available=False))
    client = TestClient(create_app(make_config(retrobat_root), now_playing_service=service))

    launch = client.post(
        "/launch",
        headers={"X-Arcade-Token": "secret"},
        json={"system": "arcade", "path": str(rom)},
    )
    now_playing = client.get("/now-playing")

    assert launch.status_code == 200
    assert now_playing.json()["active"] is True
    assert now_playing.json()["confidence"] == "medium"
    assert now_playing.json()["session"]["system"] == "arcade"
    assert now_playing.json()["session"]["game_title"] == "pacman"
    assert (retrobat_root / "now-playing.json").exists()


def test_dry_run_launch_does_not_create_session(retrobat_root: Path) -> None:
    rom = add_arcade_game(retrobat_root)
    service = make_now_playing_service(retrobat_root, FakeProcessDetector(available=False))
    client = TestClient(create_app(make_config(retrobat_root), now_playing_service=service))

    launch = client.post(
        "/launch",
        headers={"X-Arcade-Token": "secret"},
        json={"system": "arcade", "path": str(rom), "dry_run": True},
    )
    now_playing = client.get("/now-playing")

    assert launch.status_code == 200
    assert now_playing.json()["active"] is False
    assert not (retrobat_root / "now-playing.json").exists()


def test_process_detection_without_launch_returns_low_confidence(retrobat_root: Path) -> None:
    process = DetectedProcess(
        name="retroarch.exe",
        pid=123,
        exe="C:/RetroBat/emulators/retroarch/retroarch.exe",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    service = make_now_playing_service(retrobat_root, FakeProcessDetector([process], available=True))
    client = TestClient(create_app(make_config(retrobat_root), now_playing_service=service))

    response = client.get("/now-playing")
    body = response.json()

    assert response.status_code == 200
    assert body["active"] is True
    assert body["confidence"] == "low"
    assert body["session"]["source"] == "process_detected"
    assert body["session"]["process_name"] == "retroarch.exe"


def test_clear_now_playing_requires_token_and_marks_exited(retrobat_root: Path) -> None:
    rom = add_arcade_game(retrobat_root)
    service = make_now_playing_service(retrobat_root, FakeProcessDetector(available=False))
    client = TestClient(create_app(make_config(retrobat_root), now_playing_service=service))
    client.post(
        "/launch",
        headers={"X-Arcade-Token": "secret"},
        json={"system": "arcade", "path": str(rom)},
    )

    missing = client.post("/now-playing/clear")
    cleared = client.post("/now-playing/clear", headers={"X-Arcade-Token": "secret"})

    assert missing.status_code == 401
    assert cleared.status_code == 200
    assert cleared.json()["active"] is False
    assert '"status":"exited"' in (retrobat_root / "now-playing.json").read_text(encoding="utf-8").replace(" ", "")


def test_diagnostics_redacts_token_with_now_playing(retrobat_root: Path) -> None:
    rom = add_arcade_game(retrobat_root)
    config = make_config(retrobat_root, token="super-secret-token")
    service = NowPlayingService(config, process_detector=FakeProcessDetector(available=False), state_path=retrobat_root / "now-playing.json")
    client = TestClient(create_app(config, now_playing_service=service))
    client.post(
        "/launch",
        headers={"X-Arcade-Token": "super-secret-token"},
        json={"system": "arcade", "path": str(rom)},
    )

    response = client.get("/diagnostics/bundle", headers={"X-Arcade-Token": "super-secret-token"})

    assert response.status_code == 200
    assert "now_playing" in response.text
    assert "super-secret-token" not in response.text
