# RetroBat Cab Commander Agent Instructions

## Project Intent
- Build a Windows-first, LAN/local-only companion API and dashboard for a RetroBat arcade cabinet.
- Prefer safe, conservative behavior over clever automation.
- Keep the MVP source-run Python; do not require Docker or packaging.

## Safety Rules
- Bind to `127.0.0.1` by default. Allow broader binding only when explicitly configured.
- Require `X-Arcade-Token` for every POST endpoint.
- Never expose, return, or log `api_token`.
- Never execute arbitrary commands from API input.
- Never delete, rewrite, move, or modify ROM files.
- Validate requested ROM paths before launch.
- Shutdown and reboot must remain token-protected.
- Do not kill RetroBat, EmulationStation, RetroArch, or emulator processes in the MVP.

## Dependencies
- Prefer Python standard library first.
- Accepted runtime dependencies: `fastapi`, `uvicorn`, `pydantic`.
- Accepted test dependencies: `pytest`, `httpx`.
- Optional dependency: `psutil` for process detection. Code must degrade gracefully if it is absent.
- Do not add extra dependencies without documenting why.

## RetroBat Discovery
- Do not hardcode a single `es_systems.cfg` location.
- Search in this order:
  1. User-configured `es_systems_cfg` from `config.toml`.
  2. `<RETROBAT_ROOT>\emulationstation\.emulationstation\es_systems.cfg`.
  3. `<RETROBAT_ROOT>\emulationstation\es_systems.cfg`.
- If `es_systems.cfg` exists, treat it as the source of supported systems.
- If no `es_systems.cfg` exists, fall back to directories under `<RETROBAT_ROOT>\roms`.
- Parse `name`, `fullname`, `path`, `extension`, `command`, `platform`, and `theme`.
- Use configured system extensions for ROM filtering when available.

## Path And Launch Rules
- RetroBat systems map by system name to folders under `<RETROBAT_ROOT>\roms`.
- Support Windows-native systems: `windows`, `steam`, `epic`, `gog`, `amazon`, `eagames`.
- Windows-native launchable extensions include `.exe`, `.bat`, `.cmd`, `.lnk`, `.game`, `.url`, `.pc`, `.win`, `.windows`, `.wine`, `.7z`, `.zip`, `.rar`, `.wsquashfs`, and `.uwp`.
- Treat `.game` files as launcher descriptors in v1.
- Direct emulator launching from `es_systems.cfg` command templates is not MVP behavior.
- Keep `experimental_direct_es_launch = false` by default.
- If direct launching is added later, only substitute known placeholders after careful escaping and add tests.
- Windows-native launch must only use validated files inside allowed ROM locations.
- Include `dry_run` support for launch tests.

## Symlinks And Junctions
- Support symlinked or junctioned ROM folders when `allow_rom_symlinks = true`.
- Validate both configured ROM-root containment and resolved target locations.
- Log skipped files when symlink targets are unsafe or unexpected.

## API And Dashboard
- GET endpoints do not require tokens.
- POST endpoints always require tokens.
- CORS is disabled by default.
- If CORS is enabled, allow only configured origins.
- `/status` and `/config/public` must never reveal secrets.
- Dashboard should be simple, local, and useful: systems, search, random game, launch, shutdown/reboot confirmations.

## Logging
- Write rotating logs under `logs/retrobat-cab-commander.log`.
- Log launches, rescans, shutdown/reboot requests, auth failures, and skipped unsafe paths.
- Never log tokens.

## Windows Startup
- For packaged arcade installs, prefer exe-managed current-user startup via the HKCU Run key.
- Do not require the arcade user to run PowerShell, CMD, Python, pip, or startup scripts.
- The app may add/remove only its own `RetroBat Cab Commander` startup value.

## Testing
- Run `pytest` before final summary.
- Cover config loading, scanner behavior, auth, random selection, path traversal, safe public config, Windows launcher allowlist, and default `experimental_direct_es_launch = false`.
- Symlink tests should skip cleanly if Windows privileges do not allow symlink creation.
