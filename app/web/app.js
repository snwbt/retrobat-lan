const tokenInput = document.querySelector("#token");
const statusEl = document.querySelector("#status");
const systemsEl = document.querySelector("#systems");
const gamesEl = document.querySelector("#games");
const gamesTitle = document.querySelector("#games-title");
const searchForm = document.querySelector("#search-form");
const searchInput = document.querySelector("#search");
const setupStatusEl = document.querySelector("#setup-status");
const setupRetroBatRoot = document.querySelector("#setup-retrobat-root");
const setupBindHost = document.querySelector("#setup-bind-host");
const setupPort = document.querySelector("#setup-port");
const setupAutoDetect = document.querySelector("#setup-auto-detect");
const setupControlsEnabled = document.querySelector("#setup-controls-enabled");
const setupControlsAutoRepair = document.querySelector("#setup-controls-auto-repair");
const setupSafePowerWait = document.querySelector("#setup-safe-power-wait");
const setupForceKillEmulators = document.querySelector("#setup-force-kill-emulators");
const controlsStatusEl = document.querySelector("#controls-status");
const controlDevicesEl = document.querySelector("#control-devices");
const tokenStatusEl = document.querySelector("#token-status");
const folderBrowserEl = document.querySelector("#folder-browser");
const versionStatusEl = document.querySelector("#version-status");
const diagnosticsStatusEl = document.querySelector("#diagnostics-status");
const diagnosticsLogsEl = document.querySelector("#diagnostics-logs");
const nowPlayingStatusEl = document.querySelector("#now-playing-status");
const powerStatusEl = document.querySelector("#power-status");
const healthSummaryEl = document.querySelector("#health-summary");
const healthChecksEl = document.querySelector("#health-checks");
const marqueeStatusEl = document.querySelector("#marquee-status");
let currentBrowsePath = "";
let currentConfig = null;
let draftControllerPorts = {};
let configDirty = false;
let systemLaunchDetails = new Map();

const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
if (fragment.get("token")) {
  localStorage.setItem("arcadeToken", fragment.get("token"));
  history.replaceState(null, "", window.location.pathname + window.location.search);
}

tokenInput.value = localStorage.getItem("arcadeToken") || "";
updateTokenStatus();
tokenInput.addEventListener("input", () => {
  localStorage.setItem("arcadeToken", tokenInput.value);
  updateTokenStatus();
});

function updateTokenStatus() {
  tokenStatusEl.textContent = tokenInput.value
    ? "Token loaded."
    : "Open from RetroBatCabCommander.exe, or paste api_token from config.toml.";
  setupStatusEl.textContent = tokenInput.value
    ? setupStatusEl.textContent
    : "Token required for setup. Open from RetroBatCabCommander.exe, or paste api_token from config.toml.";
  controlsStatusEl.textContent = tokenInput.value
    ? controlsStatusEl.textContent
    : "Token required for controls setup.";
  diagnosticsStatusEl.textContent = tokenInput.value
    ? diagnosticsStatusEl.textContent
    : "Token required for diagnostics.";
}

function headers() {
  return {
    "Content-Type": "application/json",
    "X-Arcade-Token": tokenInput.value,
  };
}

function markConfigDirty() {
  configDirty = true;
  if (setupStatusEl.textContent && !setupStatusEl.textContent.includes("Unsaved changes")) {
    setupStatusEl.textContent = `${setupStatusEl.textContent} - Unsaved changes`;
  }
}

function populateConfigFields(config) {
  currentConfig = config;
  draftControllerPorts = JSON.parse(JSON.stringify(config.controller_ports || {}));
  configDirty = false;
  setupRetroBatRoot.value = config.retrobat_root || "";
  setupBindHost.value = config.bind_host;
  setupPort.value = config.port;
  setupAutoDetect.checked = config.auto_detect_retrobat;
  setupControlsEnabled.checked = config.controls_enabled;
  setupControlsAutoRepair.checked = config.controls_auto_repair_on_launch;
  setupSafePowerWait.value = config.safe_power_wait_seconds;
  setupForceKillEmulators.checked = config.allow_force_kill_emulators;
}

function buildConfigDraft() {
  return {
    retrobat_root: setupRetroBatRoot.value,
    auto_detect_retrobat: setupAutoDetect.checked,
    bind_host: setupBindHost.value,
    port: Number(setupPort.value),
    controls_enabled: setupControlsEnabled.checked,
    controls_auto_repair_on_launch: setupControlsAutoRepair.checked,
    safe_power_wait_seconds: Number(setupSafePowerWait.value),
    allow_force_kill_emulators: setupForceKillEmulators.checked,
    controller_ports: draftControllerPorts,
  };
}

async function loadCurrentConfig() {
  const config = await api("/setup/config/current", { headers: headers() });
  populateConfigFields(config);
  return config;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail?.message) detail = `${body.detail.message} ${(body.detail.errors || []).join(" ")}`;
      else detail = JSON.stringify(body.detail || body);
    } catch {
      detail = await response.text();
    }
    throw new Error(`HTTP ${response.status}: ${detail || response.statusText}`);
  }
  return response.json();
}

function renderGames(title, games) {
  gamesTitle.textContent = title;
  gamesEl.innerHTML = "";
  if (!games.length) {
    gamesEl.innerHTML = '<div class="row"><span class="row-meta">No games found.</span></div>';
    return;
  }
  for (const game of games) {
    const row = document.createElement("article");
    row.className = "row";
    row.innerHTML = `
      <span class="row-title"></span>
      <span class="row-meta"></span>
      <button type="button">Launch</button>
    `;
    row.querySelector(".row-title").textContent = game.likely_display_name;
    const launch = systemLaunchDetails.get(game.system.toLowerCase());
    const launchText = launch ? ` - launch ${launch.mode}${launch.warning ? ` (${launch.warning})` : ""}` : "";
    row.querySelector(".row-meta").textContent = `${game.system} - ${game.extension}${launchText} - ${game.path}`;
    row.querySelector("button").addEventListener("click", () => launchGame(game));
    gamesEl.appendChild(row);
  }
}

async function loadStatus() {
  const status = await api("/status");
  const retrobat = status.retrobat_root_valid
    ? `RetroBat found: ${status.resolved_retrobat_root}`
    : "RetroBat not found: edit config.toml";
  statusEl.textContent = `${retrobat} - ${status.indexed_game_count} games indexed - source ${status.retrobat_root_source} - frontend ${status.frontend_running ? "running" : "stopped"}`;
}

async function loadVersion() {
  const version = await api("/version");
  versionStatusEl.textContent = `${version.name} ${version.version}`;
}

function elapsedLabel(startedAt) {
  if (!startedAt) return "elapsed unknown";
  const started = new Date(startedAt).getTime();
  if (Number.isNaN(started)) return "elapsed unknown";
  const seconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    return `${hours}h ${remainingMinutes}m`;
  }
  return `${minutes}m ${remainingSeconds}s`;
}

async function loadNowPlaying() {
  const nowPlaying = await api("/now-playing");
  if (!nowPlaying.active || !nowPlaying.session) {
    nowPlayingStatusEl.textContent = "No active game detected.";
    return;
  }
  const session = nowPlaying.session;
  const process = session.process_name || nowPlaying.detected_processes[0]?.name || "unknown process";
  const title = session.game_title || "Unknown game";
  const system = session.system || "unknown system";
  nowPlayingStatusEl.textContent = `${title} - ${system} - ${session.status} - ${elapsedLabel(session.started_at)} - ${process} - confidence ${nowPlaying.confidence}`;
}

async function loadMarqueeStatus() {
  const state = await api("/marquee/state");
  marqueeStatusEl.textContent = [
    state.enabled ? "Enabled" : "Disabled",
    `refresh ${state.refresh_seconds}s`,
    `source ${state.source}`,
    state.current_game ? `game ${state.current_game}` : "",
    state.current_system ? `system ${state.current_system}` : "",
    state.selected_artwork_url ? "artwork found" : "no artwork",
  ].filter(Boolean).join(" - ");
}

function formatBytes(value) {
  if (value === null || value === undefined) return "unknown";
  const gib = value / (1024 * 1024 * 1024);
  if (gib >= 1) return `${gib.toFixed(1)} GB`;
  const mib = value / (1024 * 1024);
  return `${mib.toFixed(0)} MB`;
}

function renderHealthChecks(checks) {
  healthChecksEl.innerHTML = "";
  for (const check of checks) {
    const row = document.createElement("article");
    row.className = "health-check";
    row.innerHTML = `
      <div>
        <span class="health-badge"></span>
        <div class="row-title"></div>
      </div>
      <div class="row-meta"></div>
    `;
    const badge = row.querySelector(".health-badge");
    badge.textContent = check.severity;
    badge.classList.add(check.severity);
    row.querySelector(".row-title").textContent = check.label;
    row.querySelector(".row-meta").textContent = check.message;
    healthChecksEl.appendChild(row);
  }
}

async function loadHealth() {
  const health = await api("/health");
  healthSummaryEl.textContent = [
    `Overall ${health.severity}`,
    `Version ${health.version}`,
    `RetroBat ${health.retrobat_root_valid ? "valid" : "not found"}`,
    `systems ${health.indexed_system_count}`,
    `games ${health.indexed_game_count}`,
    `last scan ${health.last_scan_time ? new Date(health.last_scan_time).toLocaleString() : "never"}`,
    `frontend ${health.frontend_running ? "running" : "stopped"}`,
    `emulator ${health.emulator_running ? "running" : "stopped"}`,
    `disk free ${formatBytes(health.disk_free_bytes)}`,
    `startup ${health.startup_available ? (health.startup_enabled ? "enabled" : "disabled") : "unknown"}`,
    `controls ${health.controller_lock_available ? `${health.controller_connected_players}/${health.controller_configured_players} connected` : "unknown"}`,
  ].join(" - ");
  renderHealthChecks(health.checks);
}

async function loadPowerStatus() {
  const power = await api("/power/status");
  const warnings = power.warnings.length ? ` - ${power.warnings.join(" | ")}` : "";
  const activeGame = power.now_playing?.active && power.now_playing.session
    ? ` - ${power.now_playing.session.game_title || "Unknown game"}`
    : "";
  powerStatusEl.textContent = [
    power.safe_to_shutdown ? "Safe to shutdown" : "Shutdown blocked",
    `frontend ${power.frontend_running ? "running" : "stopped"}`,
    `emulator ${power.emulator_running ? "running" : "stopped"}`,
  ].join(" - ") + activeGame + warnings;
}

async function loadDiagnostics() {
  if (!tokenInput.value) {
    updateTokenStatus();
    return;
  }
  const diagnostics = await api("/diagnostics/status", { headers: headers() });
  diagnosticsStatusEl.textContent = [
    `Version ${diagnostics.version}`,
    `RetroBat ${diagnostics.retrobat_root_valid ? "valid" : "invalid"}`,
    `systems ${diagnostics.indexed_system_count}`,
    `games ${diagnostics.indexed_game_count}`,
    diagnostics.controls_detection_error ? `controls: ${diagnostics.controls_detection_error}` : "controls: ok",
    diagnostics.warnings.length ? `warnings: ${diagnostics.warnings.join(" | ")}` : "",
  ].filter(Boolean).join(" - ");
  const logs = await api("/diagnostics/logs?lines=80", { headers: headers() });
  diagnosticsLogsEl.textContent = logs.lines.join("\n");
}

async function loadSetupStatus() {
  if (!tokenInput.value) {
    updateTokenStatus();
    return;
  }
  await loadCurrentConfig();
  const setup = await api("/setup/status", { headers: headers() });
  const diagnostics = [
    `RetroBat ${setup.retrobat_root_valid ? "found" : "not found"}`,
    setup.resolved_retrobat_root,
    `retrobat.exe ${setup.retrobat_exe_exists ? "yes" : "no"}`,
    `roms ${setup.roms_root_exists ? "yes" : "no"}`,
    `systems ${setup.indexed_system_count}`,
    `games ${setup.indexed_game_count}`,
    `startup ${setup.startup_enabled ? "enabled" : "disabled"}`,
  ];
  if (setup.no_games_reason) diagnostics.push(setup.no_games_reason);
  if (currentConfig?.backup_available) diagnostics.push("backup available");
  setupStatusEl.textContent = diagnostics.join(" - ");
}

async function loadControlsStatus() {
  if (!tokenInput.value) {
    updateTokenStatus();
    return;
  }
  const controls = await api("/controls/status", { headers: headers() });
  const draftAssignments = ["player1", "player2"].map((player) => {
    const saved = controls.assignments.find((item) => item.player === player) || {};
    const draft = draftControllerPorts[player] || {};
    const path = draft.usb_location_path ?? saved.usb_location_path ?? "";
    const device = controls.devices.find((item) => item.usb_location_path === path);
    return {
      player,
      label: draft.label || saved.label || player,
      usb_location_path: path,
      device,
    };
  });
  const assigned = draftAssignments
    .filter((item) => item.usb_location_path)
    .map((item) => `${item.label}: ${item.device ? "connected" : "missing"}${configDirty ? " (draft)" : ""}`)
    .join(" - ");
  controlsStatusEl.textContent = `${controls.enabled ? "Enabled" : "Disabled"} - ${assigned || "No ports assigned"} - RetroArch config ${controls.retroarch_config_exists ? "found" : "not found yet"}`;
  renderControlDevices(controls.devices);
}

function describeFolder(folder) {
  const flags = [];
  if (folder.retrobat_exe) flags.push("retrobat.exe");
  if (folder.roms_root) flags.push("roms");
  if (folder.es_systems_cfg) flags.push("es_systems.cfg");
  if (folder.valid_retrobat_root) flags.push("RetroBat candidate");
  return flags.join(" - ");
}

async function loadFolderBrowser(path = "") {
  if (!tokenInput.value) {
    updateTokenStatus();
    return;
  }
  const query = path ? `?path=${encodeURIComponent(path)}` : "";
  const data = await api(`/setup/folders${query}`, { headers: headers() });
  currentBrowsePath = data.current_path || "";
  folderBrowserEl.innerHTML = "";
  if (data.error) {
    const error = document.createElement("div");
    error.className = "row";
    error.textContent = data.error;
    folderBrowserEl.appendChild(error);
  }
  if (data.truncated && !data.error) {
    const truncated = document.createElement("div");
    truncated.className = "row";
    truncated.textContent = "Folder list was capped. Type a more specific path if needed.";
    folderBrowserEl.appendChild(truncated);
  }
  const entries = [];
  if (data.parent_path) entries.push({ name: "..", path: data.parent_path, meta: "Parent folder" });
  for (const drive of data.drives) entries.push({ ...drive, meta: describeFolder(drive) || "Drive" });
  for (const directory of data.directories) entries.push({ ...directory, meta: describeFolder(directory) || "Folder" });
  for (const entry of entries) {
    const row = document.createElement("button");
    row.type = "button";
    row.textContent = `${entry.name} ${entry.meta ? "- " + entry.meta : ""}`;
    row.addEventListener("click", () => loadFolderBrowser(entry.path));
    folderBrowserEl.appendChild(row);
  }
}

function renderControlDevices(devices) {
  controlDevicesEl.innerHTML = "";
  if (!devices.length) {
    controlDevicesEl.innerHTML = '<div class="row"><span class="row-meta">No controller devices detected.</span></div>';
    return;
  }
  for (const device of devices) {
    const row = document.createElement("article");
    row.className = "row";
    row.innerHTML = `
      <span class="row-title"></span>
      <span class="row-meta"></span>
      <div class="setup-actions">
        <button type="button" data-player="player1">Assign as Player 1</button>
        <button type="button" data-player="player2">Assign as Player 2</button>
      </div>
    `;
    row.querySelector(".row-title").textContent = `${device.name} ${device.joystick_index === null || device.joystick_index === undefined ? "" : `(index ${device.joystick_index})`}`;
    row.querySelector(".row-meta").textContent = `${device.usb_location_path} - VID ${device.vendor_id || "?"} PID ${device.product_id || "?"}`;
    for (const button of row.querySelectorAll("button")) {
      button.addEventListener("click", () => assignControl(button.dataset.player, device.usb_location_path));
    }
    controlDevicesEl.appendChild(row);
  }
}

async function assignControl(player, locationPath) {
  const label = player === "player1" ? "Player 1" : "Player 2";
  draftControllerPorts[player] = {
    label: draftControllerPorts[player]?.label || label,
    usb_location_path: locationPath,
  };
  markConfigDirty();
  await loadControlsStatus();
}

async function loadSystems() {
  const systems = await api("/systems");
  systemLaunchDetails = new Map(systems.map((system) => [system.name.toLowerCase(), { mode: system.launch_mode, warning: system.launch_warning }]));
  systemsEl.innerHTML = "";
  if (!systems.length) {
    systemsEl.innerHTML = '<div class="row"><span class="row-meta">No systems indexed yet. Use Setup to choose the RetroBat folder, then save/rescan.</span></div>';
    return;
  }
  for (const system of systems) {
    const row = document.createElement("button");
    row.type = "button";
    row.textContent = `${system.favorite ? "* " : ""}${system.fullname || system.name} (${system.game_count}) - ${system.launch_mode}${system.launch_warning ? ` - ${system.launch_warning}` : ""}`;
    row.addEventListener("click", async () => {
      const games = await api(`/games/${encodeURIComponent(system.name)}`);
      renderGames(system.fullname || system.name, games);
    });
    systemsEl.appendChild(row);
  }
}

async function launchGame(game) {
  const result = await api("/launch", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ system: game.system, path: game.path }),
  });
  await loadNowPlaying().catch(() => {});
  await loadMarqueeStatus().catch(() => {});
  alert(result.message);
}

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = encodeURIComponent(searchInput.value.trim());
  const games = await api(`/search?q=${query}`);
  renderGames(`Search results`, games);
});

document.querySelector("#random").addEventListener("click", async () => {
  const game = await api("/game/random", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({}),
  });
  renderGames("Random game", [game]);
});

document.querySelector("#rescan").addEventListener("click", async () => {
  const result = await api("/rescan", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({}),
  });
  await loadStatus();
  await loadHealth().catch(() => {});
  await loadMarqueeStatus().catch(() => {});
  await loadSystems();
  alert(`Indexed ${result.games} games across ${result.systems} systems.`);
});

document.querySelector("#shutdown").addEventListener("click", async () => {
  if (!confirm("Shutdown the cabinet now?")) return;
  await api("/shutdown", { method: "POST", headers: headers() });
});

document.querySelector("#reboot").addEventListener("click", async () => {
  if (!confirm("Reboot the cabinet now?")) return;
  await api("/reboot", { method: "POST", headers: headers() });
});

document.querySelector("#quit-current-game").addEventListener("click", async () => {
  const result = await api("/power/quit-current-game", { method: "POST", headers: headers() });
  await loadPowerStatus();
  alert(`${result.message}${result.warnings.length ? "\n" + result.warnings.join("\n") : ""}`);
});

document.querySelector("#shutdown-safe").addEventListener("click", async () => {
  if (!confirm("Safely shutdown the cabinet now?")) return;
  const result = await api("/power/shutdown-safe", { method: "POST", headers: headers() });
  await loadPowerStatus();
  alert(`${result.message}${result.warnings.length ? "\n" + result.warnings.join("\n") : ""}`);
});

document.querySelector("#reboot-safe").addEventListener("click", async () => {
  if (!confirm("Safely reboot the cabinet now?")) return;
  const result = await api("/power/reboot-safe", { method: "POST", headers: headers() });
  await loadPowerStatus();
  alert(`${result.message}${result.warnings.length ? "\n" + result.warnings.join("\n") : ""}`);
});

document.querySelector("#clear-now-playing").addEventListener("click", async () => {
  if (!tokenInput.value) {
    alert("Token required to clear now playing. Open from RetroBatCabCommander.exe, or paste api_token from config.toml.");
    return;
  }
  await api("/now-playing/clear", { method: "POST", headers: headers() });
  await loadNowPlaying();
  await loadMarqueeStatus().catch(() => {});
});

for (const field of [setupRetroBatRoot, setupBindHost, setupPort, setupAutoDetect, setupControlsEnabled, setupControlsAutoRepair, setupSafePowerWait, setupForceKillEmulators]) {
  field.addEventListener("input", markConfigDirty);
  field.addEventListener("change", markConfigDirty);
}

document.querySelector("#validate-config").addEventListener("click", async () => {
  const result = await api("/setup/config/validate", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(buildConfigDraft()),
  });
  const lines = [
    result.ok ? "Configuration looks valid." : "Configuration needs attention.",
    `RetroBat ${result.retrobat_root_valid ? "valid" : "not found"}: ${result.resolved_retrobat_root}`,
    `retrobat.exe ${result.retrobat_exe_exists ? "yes" : "no"} - roms ${result.roms_root_exists ? "yes" : "no"}`,
    result.restart_required ? "Restart required after saving bind host or port changes." : "",
    ...result.errors,
    ...result.warnings,
  ].filter(Boolean);
  alert(lines.join("\n"));
});

document.querySelector("#save-config").addEventListener("click", async () => {
  const result = await api("/setup/config/save", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(buildConfigDraft()),
  });
  await loadStatus();
  await loadHealth().catch(() => {});
  await loadMarqueeStatus().catch(() => {});
  await loadSetupStatus();
  await loadSystems();
  await loadControlsStatus();
  await loadPowerStatus().catch(() => {});
  await loadDiagnostics().catch(() => {});
  alert(`${result.message}${result.restart_required ? "\nRestart the app to use the new bind host or port." : ""}`);
});

document.querySelector("#revert-config").addEventListener("click", async () => {
  if (!confirm("Restore the previous saved configuration backup?")) return;
  const result = await api("/setup/config/revert", { method: "POST", headers: headers() });
  await loadStatus();
  await loadHealth().catch(() => {});
  await loadMarqueeStatus().catch(() => {});
  await loadSetupStatus();
  await loadSystems();
  await loadControlsStatus();
  await loadPowerStatus().catch(() => {});
  await loadDiagnostics().catch(() => {});
  alert(`${result.message}${result.restart_required ? "\nRestart the app if bind host or port changed." : ""}`);
});

document.querySelector("#browse-folders").addEventListener("click", async () => {
  await loadFolderBrowser(setupRetroBatRoot.value);
});

document.querySelector("#use-folder").addEventListener("click", () => {
  if (!currentBrowsePath) {
    alert("Choose a folder first.");
    return;
  }
  setupRetroBatRoot.value = currentBrowsePath;
  setupAutoDetect.checked = false;
  markConfigDirty();
});

document.querySelector("#enable-startup").addEventListener("click", async () => {
  const result = await api("/setup/startup/enable", { method: "POST", headers: headers() });
  await loadSetupStatus();
  alert(result.message);
});

document.querySelector("#disable-startup").addEventListener("click", async () => {
  const result = await api("/setup/startup/disable", { method: "POST", headers: headers() });
  await loadSetupStatus();
  alert(result.message);
});

document.querySelector("#detect-controls").addEventListener("click", async () => {
  await loadControlsStatus();
});

document.querySelector("#verify-controls").addEventListener("click", async () => {
  const result = await api("/controls/verify", { method: "POST", headers: headers() });
  alert(result.ok ? "Controller order verified." : result.errors.join("\n"));
});

document.querySelector("#repair-controls").addEventListener("click", async () => {
  let result = await api("/controls/repair-retroarch", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ force_estimated_indexes: false }),
  });
  if (!result.repaired && result.verify.errors.some((error) => error.includes("estimated"))) {
    if (confirm(`${result.verify.errors.join("\n")}\n\nRepair anyway using estimated indexes?`)) {
      result = await api("/controls/repair-retroarch", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ force_estimated_indexes: true }),
      });
    }
  }
  await loadControlsStatus();
  alert(result.repaired ? "RetroArch player mapping repaired." : result.verify.errors.join("\n"));
});

document.querySelector("#refresh-diagnostics").addEventListener("click", async () => {
  await loadDiagnostics();
});

document.querySelector("#refresh-health").addEventListener("click", async () => {
  await loadHealth();
});

document.querySelector("#download-diagnostics").addEventListener("click", async () => {
  const text = await fetch("/diagnostics/bundle", { headers: headers() }).then(async (response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    return response.text();
  });
  const blob = new Blob([text], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "retrobat-cab-commander-diagnostics.json";
  link.click();
  URL.revokeObjectURL(link.href);
});

document.querySelector("#download-config-backup").addEventListener("click", async () => {
  const text = await fetch("/diagnostics/config-backup", { headers: headers() }).then(async (response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    return response.text();
  });
  const blob = new Blob([text], { type: "text/plain" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "retrobat-cab-commander-config-backup.redacted.toml";
  link.click();
  URL.revokeObjectURL(link.href);
});

async function bootDashboard() {
  await loadVersion().catch((error) => (versionStatusEl.textContent = error.message));
  await loadStatus().catch((error) => (statusEl.textContent = error.message));
  await loadNowPlaying().catch((error) => (nowPlayingStatusEl.textContent = error.message));
  await loadMarqueeStatus().catch((error) => (marqueeStatusEl.textContent = error.message));
  await loadHealth().catch((error) => (healthSummaryEl.textContent = error.message));
  await loadPowerStatus().catch((error) => (powerStatusEl.textContent = error.message));
  await loadSystems().catch((error) => (systemsEl.innerHTML = `<div class="row"><span class="row-meta">${error.message}</span></div>`));
  await loadSetupStatus().catch((error) => (setupStatusEl.textContent = error.message));
  await loadControlsStatus().catch((error) => (controlsStatusEl.textContent = error.message));
  await loadDiagnostics().catch((error) => (diagnosticsStatusEl.textContent = error.message));
}

bootDashboard();
setInterval(() => loadNowPlaying().catch((error) => (nowPlayingStatusEl.textContent = error.message)), 10000);
setInterval(() => loadMarqueeStatus().catch((error) => (marqueeStatusEl.textContent = error.message)), 10000);
setInterval(() => loadPowerStatus().catch((error) => (powerStatusEl.textContent = error.message)), 10000);
