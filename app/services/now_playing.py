from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from ..config import AppConfig
from ..logging_config import get_logger
from ..models import DetectedProcess, LaunchResult, NowPlayingResponse, PlaySession

logger = get_logger("now_playing")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ProcessDetection:
    processes: list[DetectedProcess]
    available: bool


class ProcessDetector:
    def detect(self, process_names: list[str]) -> ProcessDetection:
        wanted = {name.lower() for name in process_names}
        if not wanted:
            return ProcessDetection(processes=[], available=True)
        try:
            import psutil  # type: ignore
        except Exception:
            return ProcessDetection(processes=[], available=False)

        detected: list[DetectedProcess] = []
        try:
            iterator = psutil.process_iter(["name", "pid", "exe", "create_time"])
            for process in iterator:
                info = getattr(process, "info", {}) or {}
                name = str(info.get("name") or "")
                if name.lower() not in wanted:
                    continue
                started_at = None
                create_time = info.get("create_time")
                if isinstance(create_time, (int, float)):
                    started_at = datetime.fromtimestamp(create_time, timezone.utc)
                detected.append(
                    DetectedProcess(
                        name=name,
                        pid=int(info.get("pid") or getattr(process, "pid", 0)),
                        exe=str(info.get("exe") or "") or None,
                        started_at=started_at,
                    )
                )
        except Exception as exc:
            logger.warning("now_playing_process_detection_failed error=%s", exc)
            return ProcessDetection(processes=[], available=False)
        return ProcessDetection(processes=detected, available=True)


class NowPlayingService:
    def __init__(self, config: AppConfig, process_detector: ProcessDetector | None = None, state_path: Path | None = None):
        self.config = config
        self.process_detector = process_detector or ProcessDetector()
        self.state_path = state_path or self.default_state_path(config)

    @staticmethod
    def default_state_path(config: AppConfig) -> Path:
        if config.config_path:
            return config.config_path.parent / "now-playing.json"
        return config.log_dir / "now-playing.json"

    def record_launch(self, result: LaunchResult) -> None:
        if result.dry_run or result.game is None:
            return
        detection = self._detect_processes()
        process_name = detection.processes[0].name if detection.processes else None
        game = result.game
        session = PlaySession(
            session_id=str(uuid.uuid4()),
            system=game.system,
            game_title=game.likely_display_name or game.name,
            rom_path=game.path,
            launcher_type=result.strategy,
            process_name=process_name,
            started_at=utc_now(),
            ended_at=None,
            status="running",
            source="app_launch",
        )
        self._save_session(session)
        logger.info(
            "now_playing_recorded session_id=%s system=%s title=%s launcher=%s",
            session.session_id,
            session.system,
            session.game_title,
            session.launcher_type,
        )

    def clear(self) -> NowPlayingResponse:
        session = self._load_session()
        if session and session.ended_at is None:
            session.status = "exited"
            session.ended_at = utc_now()
            self._save_session(session)
            logger.info("now_playing_cleared session_id=%s", session.session_id)
        return self.current()

    def last_session(self) -> PlaySession | None:
        return self._load_session()

    def current(self) -> NowPlayingResponse:
        detection = self._detect_processes()
        session = self._load_session()
        active_process = detection.processes[0] if detection.processes else None

        if session and session.ended_at is None and session.status in {"launching", "running", "unknown"}:
            if active_process:
                session.status = "running"
                session.process_name = active_process.name
                self._save_session(session)
                return NowPlayingResponse(active=True, session=session, detected_processes=detection.processes, confidence="high")
            if detection.available:
                session.status = "exited"
                session.ended_at = utc_now()
                self._save_session(session)
                return NowPlayingResponse(active=False, session=None, detected_processes=[], confidence="low")
            return NowPlayingResponse(active=True, session=session, detected_processes=[], confidence="medium")

        if active_process:
            synthetic = PlaySession(
                session_id=f"process-{active_process.pid}",
                system=None,
                game_title=None,
                rom_path=None,
                launcher_type="process-detected",
                process_name=active_process.name,
                started_at=active_process.started_at or utc_now(),
                ended_at=None,
                status="unknown",
                source="process_detected",
            )
            return NowPlayingResponse(active=True, session=synthetic, detected_processes=detection.processes, confidence="low")

        return NowPlayingResponse(active=False, session=None, detected_processes=[], confidence="low")

    def _detect_processes(self) -> ProcessDetection:
        names = [*self.config.emulator_process_names, *self.config.frontend_process_names]
        return self.process_detector.detect(names)

    def _load_session(self) -> PlaySession | None:
        if not self.state_path.exists():
            return None
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            return PlaySession.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            logger.warning("now_playing_state_load_failed path=%s error=%s", self.state_path, exc)
            return None

    def _save_session(self, session: PlaySession) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_path.with_suffix(f"{self.state_path.suffix}.tmp")
        tmp_path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        tmp_path.replace(self.state_path)
