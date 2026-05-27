const artworkEl = document.querySelector("#artwork");
const fallbackEl = document.querySelector("#fallback");
const systemEl = document.querySelector("#system");
const titleEl = document.querySelector("#title");
const statusEl = document.querySelector("#status");

let refreshTimer = null;

async function api(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  return response.json();
}

function setRefresh(seconds) {
  const interval = Math.max(1, Number(seconds) || 5) * 1000;
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(loadMarquee, interval);
}

function renderState(state) {
  const title = state.current_game || state.fallback_text || "RetroBat Cab Commander";
  const system = state.current_system || "RetroBat Cab Commander";
  titleEl.textContent = title;
  systemEl.textContent = system;
  fallbackEl.textContent = state.enabled ? title : "Marquee disabled";
  statusEl.textContent = state.enabled ? `Source: ${state.source}` : "Disabled in config.toml";

  if (state.enabled && state.selected_artwork_url) {
    artworkEl.src = state.selected_artwork_url;
    artworkEl.hidden = false;
    fallbackEl.hidden = true;
  } else {
    artworkEl.removeAttribute("src");
    artworkEl.hidden = true;
    fallbackEl.hidden = false;
  }
}

async function loadMarquee() {
  try {
    const state = await api("/marquee/state");
    renderState(state);
    setRefresh(state.refresh_seconds);
  } catch (error) {
    artworkEl.hidden = true;
    fallbackEl.hidden = false;
    fallbackEl.textContent = "RetroBat Cab Commander";
    systemEl.textContent = "Marquee";
    titleEl.textContent = "Unable to load state";
    statusEl.textContent = error.message;
  }
}

loadMarquee();
