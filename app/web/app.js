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
const controlsStatusEl = document.querySelector("#controls-status");
const controlDevicesEl = document.querySelector("#control-devices");
const tokenStatusEl = document.querySelector("#token-status");
const folderBrowserEl = document.querySelector("#folder-browser");
const versionStatusEl = document.querySelector("#version-status");
const diagnosticsStatusEl = document.querySelector("#diagnostics-status");
const diagnosticsLogsEl = document.querySelector("#diagnostics-logs");
let currentBrowsePath = "";

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
    row.querySelector(".row-meta").textContent = `${game.system} - ${game.extension} - ${game.path}`;
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
  setupStatusEl.textContent = diagnostics.join(" - ");
  setupRetroBatRoot.value = setup.configured_retrobat_root || "";
  setupBindHost.value = setup.bind_host;
  setupPort.value = setup.port;
  setupAutoDetect.checked = setup.auto_detect_retrobat;
}

async function loadControlsStatus() {
  if (!tokenInput.value) {
    updateTokenStatus();
    return;
  }
  const controls = await api("/controls/status", { headers: headers() });
  const assigned = controls.assignments
    .filter((item) => item.usb_location_path)
    .map((item) => `${item.label}: ${item.device ? "connected" : "missing"}`)
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
  await api("/controls/assign", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ player: player, usb_location_path: locationPath }),
  });
  await loadControlsStatus();
}

async function loadSystems() {
  const systems = await api("/systems");
  systemsEl.innerHTML = "";
  if (!systems.length) {
    systemsEl.innerHTML = '<div class="row"><span class="row-meta">No systems indexed yet. Use Setup to choose the RetroBat folder, then save/rescan.</span></div>';
    return;
  }
  for (const system of systems) {
    const row = document.createElement("button");
    row.type = "button";
    row.textContent = `${system.favorite ? "* " : ""}${system.fullname || system.name} (${system.game_count})`;
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

document.querySelector("#save-setup").addEventListener("click", async () => {
  await api("/setup/config", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      retrobat_root: setupRetroBatRoot.value,
      auto_detect_retrobat: setupAutoDetect.checked,
      bind_host: setupBindHost.value,
      port: Number(setupPort.value),
    }),
  });
  await loadStatus();
  await loadSetupStatus();
  await loadSystems();
  alert("Setup saved and games rescanned. Restart the app if you changed bind host or port.");
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

loadVersion().catch((error) => (versionStatusEl.textContent = error.message));
loadStatus().catch((error) => (statusEl.textContent = error.message));
loadSystems().catch((error) => (systemsEl.innerHTML = `<div class="row"><span class="row-meta">${error.message}</span></div>`));
loadSetupStatus().catch((error) => (setupStatusEl.textContent = error.message));
loadControlsStatus().catch((error) => (controlsStatusEl.textContent = error.message));
loadDiagnostics().catch((error) => (diagnosticsStatusEl.textContent = error.message));
