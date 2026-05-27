# RetroBat Cab Commander

RetroBat Cab Commander is a local Windows-first FastAPI companion for a RetroBat arcade cabinet. It indexes RetroBat systems and games, exposes a small LAN/local API, serves a simple dashboard, and keeps launch and power actions token-protected.

## Security

The default bind host is `127.0.0.1`. Do not expose this server to the public internet.

Every POST endpoint requires:

```powershell
X-Arcade-Token: your-token
```

The API never returns the configured token. Shutdown and reboot are POST-only and token-protected.

## Arcade PC Setup

The easiest install is the portable exe release:

1. Extract `RetroBatCabCommander-v0.1.2-win64.zip` to `C:\RetroBatCabCommander`.
2. Double-click `RetroBatCabCommander.exe`.
3. The dashboard opens automatically and stores the generated token in the browser.
4. If RetroBat is not detected, use `Browse folders` in the dashboard setup panel and choose the folder that contains `retrobat.exe` or `roms`.
5. Click `Save setup`; the app rescans systems and games immediately.
6. Click `Start with Windows` in the dashboard.

The arcade PC does not need Python, pip, PowerShell, CMD, or startup scripts.

If you opened the dashboard manually and the token field is empty, open `config.toml` beside the exe and paste the `api_token` value into the dashboard token field.

## Source Setup

Requires Python 3.11 or newer.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,process]"
Copy-Item config.example.toml config.toml
notepad config.toml
.\scripts\run-dev.ps1
```

The `process` extra installs `psutil`, which is optional but improves `/status` process detection for RetroBat, EmulationStation, and emulators.

Open the dashboard:

```text
http://127.0.0.1:8765/
```

## Configuration

Runtime configuration lives in `config.toml`.

Important options:

```toml
auto_detect_retrobat = true
retrobat_root = ""
api_token = "change-this-token"
bind_host = "127.0.0.1"
port = 8765

favorite_systems = ["arcade", "nes", "snes", "windows"]
frontend_process_names = ["retrobat.exe", "emulationstation.exe"]
emulator_process_names = ["retroarch.exe"]

allow_rom_symlinks = true
experimental_direct_es_launch = false
cors_enabled = false
cors_origins = []
```

Leave `retrobat_root` blank for auto-detection. The app checks configured paths first, then shallow local candidates such as the app folder, common `C:\RetroBat` / `D:\RetroBat` / `E:\RetroBat` installs, drive-root `RetroBat` folders, and `RETROBAT_ROOT`.

To force an exact path and disable fallback:

```toml
auto_detect_retrobat = false
retrobat_root = "D:/Arcade/RetroBat"
```

Optional `es_systems_cfg` can point to a specific file. If omitted, discovery checks:

```text
<RETROBAT_ROOT>\emulationstation\.emulationstation\es_systems.cfg
<RETROBAT_ROOT>\emulationstation\es_systems.cfg
```

## RetroBat Assumptions

RetroBat systems are discovered from `es_systems.cfg` when present. Each `<system>` entry provides metadata like `name`, `fullname`, `path`, `extension`, `command`, `platform`, and `theme`.

When `es_systems.cfg` is not present, the scanner falls back to folders under:

```text
<RETROBAT_ROOT>\roms
```

Windows-native systems include:

```text
windows, steam, epic, gog, amazon, eagames
```

For v1, `.game` files are treated as launcher descriptors and may be opened by the Windows shell. Direct parsing can be added later.

## API Examples

```powershell
curl http://127.0.0.1:8765/status
curl http://127.0.0.1:8765/systems
curl "http://127.0.0.1:8765/search?q=mario"
```

Token-protected examples:

```powershell
curl -X POST http://127.0.0.1:8765/rescan -H "X-Arcade-Token: change-this-token"

curl -X POST http://127.0.0.1:8765/game/random `
  -H "Content-Type: application/json" `
  -H "X-Arcade-Token: change-this-token" `
  -d "{}"

curl -X POST http://127.0.0.1:8765/launch `
  -H "Content-Type: application/json" `
  -H "X-Arcade-Token: change-this-token" `
  -d "{\"system\":\"windows\",\"path\":\"C:/RetroBat/roms/windows/My Game.lnk\",\"dry_run\":true}"
```

## Launch Behavior

Windows-native systems launch validated files through the Windows shell.

Emulator systems use a placeholder `RetroBatLaunchStrategy`: it starts `retrobat.exe` if available and not already running, logs the selected ROM, and returns selected game metadata. It does not execute `es_systems.cfg` command templates in the MVP.

`experimental_direct_es_launch` defaults to `false`; direct command-template launch is backlog work and must include command substitution tests before use.

## USB Port Player Lock

RetroBat Cab Commander can bind Player 1 and Player 2 to physical USB hub ports instead of relying only on controller name, VID, or PID. This is useful when two identical arcade encoder boards look the same to RetroBat or RetroArch.

In the dashboard:

1. Open `Controls`.
2. Click `Detect connected controls`.
3. Assign the left/P1 encoder USB port as Player 1.
4. Assign the right/P2 encoder USB port as Player 2.
5. Click `Verify player order`.
6. Click `Repair RetroArch mapping`.

The app writes only these RetroArch keys:

```text
input_player1_joypad_index
input_player2_joypad_index
```

Before the first write, it creates:

```text
<RETROBAT_ROOT>\emulators\retroarch\retroarch.cfg.retrobat-cab-commander.bak
```

If the app cannot determine a joystick index, or Windows reports both encoders as the same controller, launch is blocked with a clear warning. A future driver-backed virtual controller mode may be needed for absolute enforcement if RetroArch still collapses identical boards.

## Startup At Login

In the packaged exe, use the dashboard buttons:

- `Start with Windows`
- `Disable Start with Windows`

The app manages only its own current-user Windows startup entry.

## Development

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Run the app manually:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Build the portable exe release from a development machine:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,process,packaging]"
.\.venv\Scripts\python.exe scripts\build_release.py
```

The output is written to:

```text
dist\RetroBatCabCommander
dist\RetroBatCabCommander-v0.1.2-win64.zip
```

## Backlog

- Home Assistant webhooks and MQTT
- LEDBlinky or WLED integration
- Dynamic marquee output
- Now-playing detection
- Direct launch from `es_systems.cfg` command templates
- System artwork scraping
- Windows tray icon
- PyInstaller build
- Gamepad-controlled local dashboard
