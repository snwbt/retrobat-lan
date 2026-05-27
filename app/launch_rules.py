from __future__ import annotations

from .config import AppConfig

SUPPORTED_LAUNCH_MODES = {"shell", "retrobat", "disabled", "dry_run_only"}
WINDOWS_NATIVE_SYSTEMS = {"windows", "steam", "epic", "gog", "amazon", "eagames"}


def normalize_system_name(system: str) -> str:
    return system.strip().lower()


def configured_launch_mode(config: AppConfig, system: str) -> str | None:
    rule = config.launch_rules.get(normalize_system_name(system))
    if not rule:
        return None
    return rule.mode.strip().lower()


def default_launch_mode(system: str) -> str:
    return "shell" if normalize_system_name(system) in WINDOWS_NATIVE_SYSTEMS else "retrobat"


def effective_launch_mode(config: AppConfig, system: str) -> str:
    return configured_launch_mode(config, system) or default_launch_mode(system)


def launch_mode_warning(config: AppConfig, system: str) -> str | None:
    mode = effective_launch_mode(config, system)
    if mode not in SUPPORTED_LAUNCH_MODES:
        return f"Unknown launch mode '{mode}' configured."
    if mode == "disabled":
        return "Launches are disabled for this system."
    if mode == "dry_run_only":
        return "This system only allows dry-run launch tests."
    return None


def launch_rule_warnings(config: AppConfig) -> list[str]:
    warnings: list[str] = []
    for system, rule in sorted(config.launch_rules.items()):
        mode = rule.mode.strip().lower()
        if mode not in SUPPORTED_LAUNCH_MODES:
            warnings.append(f"Unknown launch mode '{mode}' configured for {system}.")
    return warnings
