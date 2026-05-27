---
name: retrobat-cab-dev
description: Instruction-only development guidance for RetroBat, EmulationStation, arcade cabinet companion apps, FastAPI cabinet APIs, ROM scanners, and Windows launcher tasks. Use when Codex works on RetroBat Cab Commander or similar local Windows arcade cabinet tooling involving safe LAN APIs, ROM indexing, launch validation, or dashboard behavior.
---

# RetroBat Cab Commander Development

## Core Guidance
- Prefer safe local-first behavior for arcade cabinet tooling.
- Default network binding to `127.0.0.1`; require explicit configuration for LAN-wide binding.
- Require token authentication for write or power actions.
- Never expose secrets in API responses or logs.
- Never execute arbitrary user-provided commands.
- Never delete or mutate ROM files.

## RetroBat And EmulationStation
- Discover `es_systems.cfg` from configured path first, then common RetroBat EmulationStation paths.
- Treat `es_systems.cfg` as the supported-system source when present.
- Parse system metadata without assuming every folder under `roms` is valid.
- Use system extension lists for filtering when available.
- Fall back conservatively when config files are missing.

## ROM Scanning
- Cache the game index in memory and provide an explicit rescan operation.
- Validate all file paths before exposing them for launch.
- Support symlinked ROM locations only when configured and validated.
- Log skipped unsafe paths without logging secrets.

## Launching
- Keep emulator launch behavior conservative unless an experimental flag is explicitly enabled.
- For emulator systems, start RetroBat or EmulationStation and return selected game metadata in the MVP.
- For Windows-native systems, launch only validated files with known extensions inside allowed ROM locations.
- Include dry-run behavior for tests.

## Testing
- Add focused tests for config, scanner, auth, random selection, path validation, public config secrecy, Windows launcher allowlists, and default safety flags.
- Skip symlink tests cleanly if the platform or privileges do not support them.
