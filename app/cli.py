from __future__ import annotations

import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from .config import ensure_config_file, load_config
from .main import create_app


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


def dashboard_url(port: int, token: str) -> str:
    return f"http://127.0.0.1:{port}/#token={token}"


def open_dashboard_later(port: int, token: str) -> None:
    timer = threading.Timer(1.5, lambda: webbrowser.open(dashboard_url(port, token)))
    timer.daemon = True
    timer.start()


def main() -> None:
    base_dir = app_base_dir()
    config_path = base_dir / "config.toml"
    _, token, _ = ensure_config_file(config_path)
    config = load_config(config_path)
    open_dashboard_later(config.port, token)
    uvicorn.run(create_app(config), host=config.bind_host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()

