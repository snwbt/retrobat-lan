const views = new Map([...document.querySelectorAll(".view")].map((view) => [view.id.replace("view-", ""), view]));
const messageEl = document.querySelector("#message");
const cabinetStatusEl = document.querySelector("#cabinet-status");
const nowPlayingSummaryEl = document.querySelector("#now-playing-summary");
const tokenSummaryEl = document.querySelector("#token-summary");
const tokenInput = document.querySelector("#token-input");
const systemsListEl = document.querySelector("#systems-list");
const gamesListEl = document.querySelector("#games-list");
const gamesHeadingEl = document.querySelector("#games-heading");
const searchForm = document.querySelector("#search-form");
const searchInput = document.querySelector("#search-input");
const searchResultsEl = document.querySelector("#search-results");
const nowPlayingDetailEl = document.querySelector("#now-playing-detail");
const controlsDetailEl = document.querySelector("#controls-detail");
const powerDetailEl = document.querySelector("#power-detail");
const confirmTitleEl = document.querySelector("#confirm-title");
const confirmBodyEl = document.querySelector("#confirm-body");

let token = sessionStorage.getItem("kioskArcadeToken") || localStorage.getItem("arcadeToken") || "";
let viewStack = ["home"];
let currentView = "home";
let confirmAction = null;

tokenInput.value = token;
updateTokenSummary();

function authHeaders() {
  return {
    "Content-Type": "application/json",
    "X-Arcade-Token": token,
  };
}

function setMessage(text) {
  messageEl.textContent = text || "";
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || body);
    } catch {
      detail = await response.text();
    }
    if (response.status === 401) setMessage("Token required. Enter the arcade token on Home.");
    throw new Error(`HTTP ${response.status}: ${detail || response.statusText}`);
  }
  return response.json();
}

function updateTokenSummary() {
  tokenSummaryEl.textContent = token ? "Session token ready" : "Token needed for actions";
}

function focusables() {
  return [...views.get(currentView).querySelectorAll("[data-focusable]")].filter((item) => {
    return !item.disabled && item.offsetParent !== null;
  });
}

function setFocused(element) {
  for (const item of document.querySelectorAll(".focused")) item.classList.remove("focused");
  if (!element) return;
  element.classList.add("focused");
  element.focus({ preventScroll: true });
  element.scrollIntoView({ block: "nearest", inline: "nearest" });
}

function focusFirst() {
  setFocused(focusables()[0]);
}

function moveFocus(direction) {
  const items = focusables();
  const active = document.activeElement;
  const current = items.includes(active) ? active : items[0];
  if (!current) return;
  const currentRect = current.getBoundingClientRect();
  const cx = currentRect.left + currentRect.width / 2;
  const cy = currentRect.top + currentRect.height / 2;
  let best = null;
  let bestScore = Infinity;
  for (const item of items) {
    if (item === current) continue;
    const rect = item.getBoundingClientRect();
    const ix = rect.left + rect.width / 2;
    const iy = rect.top + rect.height / 2;
    const dx = ix - cx;
    const dy = iy - cy;
    if (direction === "left" && dx >= -8) continue;
    if (direction === "right" && dx <= 8) continue;
    if (direction === "up" && dy >= -8) continue;
    if (direction === "down" && dy <= 8) continue;
    const primary = direction === "left" || direction === "right" ? Math.abs(dx) : Math.abs(dy);
    const secondary = direction === "left" || direction === "right" ? Math.abs(dy) : Math.abs(dx);
    const score = primary + secondary * 1.8;
    if (score < bestScore) {
      best = item;
      bestScore = score;
    }
  }
  if (best) setFocused(best);
}

function showView(name, push = true) {
  for (const view of views.values()) view.classList.remove("active-view");
  views.get(name).classList.add("active-view");
  currentView = name;
  if (push && viewStack[viewStack.length - 1] !== name) viewStack.push(name);
  setTimeout(focusFirst, 0);
}

function goBack() {
  if (currentView === "home") return;
  viewStack.pop();
  showView(viewStack[viewStack.length - 1] || "home", false);
}

function resultButton(label, meta, onActivate) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "result-button";
  button.dataset.focusable = "";
  button.innerHTML = `<strong>${label}</strong><br><span class="eyebrow">${meta || ""}</span>`;
  button.addEventListener("click", onActivate);
  return button;
}

async function loadStatus() {
  const status = await api("/status");
  cabinetStatusEl.textContent = `${status.retrobat_root_valid ? "RetroBat found" : "RetroBat not found"} - ${status.indexed_game_count} games`;
}

function elapsedLabel(startedAt) {
  if (!startedAt) return "elapsed unknown";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000));
  const minutes = Math.floor(seconds / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes}m ${seconds % 60}s`;
}

async function loadNowPlaying() {
  const data = await api("/now-playing");
  if (!data.active || !data.session) {
    nowPlayingSummaryEl.textContent = "No game detected";
    nowPlayingDetailEl.textContent = "No active game detected.";
    return data;
  }
  const session = data.session;
  const process = session.process_name || data.detected_processes[0]?.name || "unknown process";
  const title = session.game_title || "Unknown game";
  const system = session.system || "unknown system";
  nowPlayingSummaryEl.textContent = `${title} - ${system}`;
  nowPlayingDetailEl.innerHTML = `
    <strong>${title}</strong><br>
    System: ${system}<br>
    Status: ${session.status}<br>
    Elapsed: ${elapsedLabel(session.started_at)}<br>
    Process: ${process}<br>
    Confidence: ${data.confidence}
  `;
  return data;
}

async function loadSystems() {
  const systems = await api("/systems");
  systemsListEl.innerHTML = "";
  if (!systems.length) {
    systemsListEl.textContent = "No systems indexed yet.";
    return;
  }
  for (const system of systems) {
    systemsListEl.appendChild(resultButton(system.fullname || system.name, `${system.game_count} games`, () => openGames(system)));
  }
  setTimeout(focusFirst, 0);
}

async function openGames(system) {
  const games = await api(`/games/${encodeURIComponent(system.name)}`);
  gamesHeadingEl.textContent = system.fullname || system.name;
  renderGameResults(gamesListEl, games);
  showView("games");
}

function renderGameResults(container, games) {
  container.innerHTML = "";
  if (!games.length) {
    container.textContent = "No games found.";
    return;
  }
  for (const game of games) {
    container.appendChild(resultButton(game.likely_display_name, `${game.system} - ${game.extension}`, () => confirmLaunch(game)));
  }
}

async function searchGames(query) {
  const games = await api(`/search?q=${encodeURIComponent(query)}`);
  renderGameResults(searchResultsEl, games);
  setTimeout(focusFirst, 0);
}

async function loadControlsStatus() {
  if (!token) {
    controlsDetailEl.textContent = "Token required for controls status.";
    return;
  }
  const controls = await api("/controls/status", { headers: authHeaders() });
  const assignments = controls.assignments.map((item) => `${item.label}: ${item.device ? "connected" : item.usb_location_path ? "missing" : "not assigned"}`);
  controlsDetailEl.innerHTML = `
    Enabled: ${controls.enabled ? "yes" : "no"}<br>
    Auto repair: ${controls.auto_repair_on_launch ? "yes" : "no"}<br>
    RetroArch config: ${controls.retroarch_config_exists ? "found" : "not found"}<br>
    ${assignments.join("<br>")}
  `;
}

async function loadPowerStatus() {
  const power = await api("/power/status");
  const nowPlaying = power.now_playing?.active && power.now_playing.session
    ? power.now_playing.session.game_title || "Unknown game"
    : "No active game";
  const warnings = power.warnings.length ? `<br>Warnings:<br>${power.warnings.join("<br>")}` : "";
  powerDetailEl.innerHTML = `
    Safe to shutdown: ${power.safe_to_shutdown ? "yes" : "no"}<br>
    Frontend: ${power.frontend_running ? "running" : "stopped"}<br>
    Emulator: ${power.emulator_running ? "running" : "stopped"}<br>
    Now playing: ${nowPlaying}${warnings}
  `;
  return power;
}

function confirmLaunch(game) {
  showConfirm("Launch game", `${game.likely_display_name} (${game.system})`, async () => {
    await api("/launch", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ system: game.system, path: game.path }),
    });
    setMessage(`Launch requested: ${game.likely_display_name}`);
    await loadNowPlaying();
    showView("home", false);
  });
}

function showConfirm(title, body, action) {
  confirmTitleEl.textContent = title;
  confirmBodyEl.textContent = body;
  confirmAction = action;
  showView("confirm");
}

async function runAction(action) {
  try {
    if (action === "open-search") showView("search");
    else if (action === "open-systems") {
      showView("systems");
      await loadSystems();
    } else if (action === "random-game") {
      const game = await api("/game/random", { method: "POST", headers: authHeaders(), body: JSON.stringify({}) });
      confirmLaunch(game);
    } else if (action === "open-now-playing") {
      showView("now-playing");
      await loadNowPlaying();
    } else if (action === "open-controls") {
      showView("controls");
      await loadControlsStatus();
    } else if (action === "open-power") {
      showView("power");
      await loadPowerStatus();
    }
    else if (action === "save-token") {
      token = tokenInput.value.trim();
      sessionStorage.setItem("kioskArcadeToken", token);
      updateTokenSummary();
      setMessage(token ? "Token saved for this browser session." : "Token cleared.");
    } else if (action === "back" || action === "confirm-cancel") goBack();
    else if (action === "refresh-now-playing") await loadNowPlaying();
    else if (action === "clear-now-playing") {
      await api("/now-playing/clear", { method: "POST", headers: authHeaders() });
      await loadNowPlaying();
    } else if (action === "refresh-controls") await loadControlsStatus();
    else if (action === "quit-current-game") {
      const result = await api("/power/quit-current-game", { method: "POST", headers: authHeaders() });
      await loadPowerStatus();
      setMessage(`${result.message}${result.warnings.length ? " " + result.warnings.join(" ") : ""}`);
    }
    else if (action === "confirm-reboot") showConfirm("Safe reboot", "Quit the current game if needed, then reboot Windows.", () => api("/power/reboot-safe", { method: "POST", headers: authHeaders() }));
    else if (action === "confirm-shutdown") showConfirm("Safe shutdown", "Quit the current game if needed, then shut down Windows.", () => api("/power/shutdown-safe", { method: "POST", headers: authHeaders() }));
    else if (action === "confirm-accept" && confirmAction) {
      await confirmAction();
      confirmAction = null;
      setMessage("Action sent.");
    }
  } catch (error) {
    setMessage(error.message);
  }
}

document.addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (target) runAction(target.dataset.action);
});

document.addEventListener("keydown", (event) => {
  const active = document.activeElement;
  const isTyping = active && active.tagName === "INPUT";
  if (isTyping && event.key !== "Escape") return;
  if (event.key === "ArrowLeft") moveFocus("left");
  else if (event.key === "ArrowRight") moveFocus("right");
  else if (event.key === "ArrowUp") moveFocus("up");
  else if (event.key === "ArrowDown") moveFocus("down");
  else if (event.key === "Enter" || event.key === " ") document.activeElement?.click();
  else if (event.key === "Escape" || event.key === "Backspace") goBack();
  else return;
  event.preventDefault();
});

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await searchGames(searchInput.value.trim());
});

let lastGamepadMove = 0;
function pollGamepad() {
  const pad = navigator.getGamepads?.().find(Boolean);
  if (pad) {
    const now = Date.now();
    const ready = now - lastGamepadMove > 180;
    const x = pad.axes[0] || 0;
    const y = pad.axes[1] || 0;
    const buttons = pad.buttons;
    if (ready) {
      if (x < -0.5 || buttons[14]?.pressed) moveFocus("left");
      else if (x > 0.5 || buttons[15]?.pressed) moveFocus("right");
      else if (y < -0.5 || buttons[12]?.pressed) moveFocus("up");
      else if (y > 0.5 || buttons[13]?.pressed) moveFocus("down");
      else if (buttons[0]?.pressed) document.activeElement?.click();
      else if (buttons[1]?.pressed) goBack();
      else {
        requestAnimationFrame(pollGamepad);
        return;
      }
      lastGamepadMove = now;
    }
  }
  requestAnimationFrame(pollGamepad);
}

async function boot() {
  await Promise.allSettled([loadStatus(), loadNowPlaying()]);
  focusFirst();
  setInterval(() => loadNowPlaying().catch((error) => setMessage(error.message)), 10000);
  requestAnimationFrame(pollGamepad);
}

boot();
