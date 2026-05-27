from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
APP_NAME = "RetroBatCabCommander"
VERSION = "0.1.1"


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def copy_runtime_files(release_dir: Path) -> None:
    config_example = PROJECT_ROOT / "config.example.toml"
    shutil.copy2(config_example, release_dir / "config.example.toml")
    config_path = release_dir / "config.toml"
    if not config_path.exists():
        shutil.copy2(config_example, config_path)
    (release_dir / "logs").mkdir(exist_ok=True)
    (release_dir / "VERSION.txt").write_text(f"{APP_NAME} {VERSION}\n", encoding="utf-8")


def zip_release(release_dir: Path) -> Path:
    zip_path = DIST_DIR / f"{APP_NAME}-v{VERSION}-win64.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in release_dir.rglob("*"):
            archive.write(path, path.relative_to(DIST_DIR))
    return zip_path


def main() -> None:
    run([sys.executable, "-m", "pytest"])

    release_dir = DIST_DIR / APP_NAME
    if release_dir.exists():
        shutil.rmtree(release_dir)

    add_data = f"{PROJECT_ROOT / 'app' / 'web'}{os.pathsep}app/web"
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--name",
            APP_NAME,
            "--distpath",
            str(DIST_DIR),
            "--workpath",
            str(BUILD_DIR),
            "--add-data",
            add_data,
            "--collect-submodules",
            "uvicorn",
            "--collect-submodules",
            "fastapi",
            str(PROJECT_ROOT / "retrobat_cab_commander.py"),
        ]
    )

    copy_runtime_files(release_dir)
    zip_path = zip_release(release_dir)
    print(f"Built {release_dir}")
    print(f"Created {zip_path}")


if __name__ == "__main__":
    main()
