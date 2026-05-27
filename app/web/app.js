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

const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
if (fragment.get("token")) {
  localStorage.setItem("arcadeToken", fragment.get("token"));
  history.replaceState(null, "", window.location.pathname + window.location.search);
}

tokenInput.value = localStorage.getItem("arcadeToken") || "";
tokenInput.addEventListener("input", () => localStorage.setItem("arcadeToken", tokenInput.value));

function headers() {
  return {
    "Content-Type": "application/json",
    "X-Arcade-Token": tokenInput.value,
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
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

async function loadSetupStatus() {
  if (!tokenInput.value) return;
  const setup = await api("/setup/status", { headers: headers() });
  setupStatusEl.textContent = `${setup.retrobat_root_valid ? "RetroBat found" : "RetroBat not found"} - ${setup.resolved_retrobat_root} - startup ${setup.startup_enabled ? "enabled" : "disabled"}`;
  setupRetroBatRoot.value = setup.configured_retrobat_root || "";
  setupBindHost.value = setup.bind_host;
  setupPort.value = setup.port;
  setupAutoDetect.checked = setup.auto_detect_retrobat;
}

async function loadSystems() {
  const systems = await api("/systems");
  systemsEl.innerHTML = "";
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
  alert("Setup saved. Restart the app if you changed bind host or port.");
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

loadStatus().catch((error) => (statusEl.textContent = error.message));
loadSystems().catch((error) => (systemsEl.textContent = error.message));
loadSetupStatus().catch((error) => (setupStatusEl.textContent = error.message));
