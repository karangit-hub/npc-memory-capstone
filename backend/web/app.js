"use strict";
const byId = id => document.getElementById(id);
const form = byId("chat-form"), input = byId("message"), log = byId("chat-log");
let busy = false, identityVersion = 0, previewVersion = 0;

function identity() {
  const player = byId("player-choice").value === "custom" ? byId("custom-player").value.trim() : byId("player-choice").value;
  return {player_id: player, npc_id: byId("npc-id").value.trim()};
}
function setBusy(value) {
  busy = value;
  for (const id of ["send", "player-choice", "custom-player", "npc-id", "clear-view"]) byId(id).disabled = value;
  byId("thinking").hidden = !value;
  input.disabled = value;
  form.setAttribute("aria-busy", String(value));
}
function error(message = "") { byId("error").textContent = message; byId("error").hidden = !message; }
async function request(path, options = {}) {
  let response;
  try { response = await fetch(path, options); }
  catch (_) { throw new Error("Cannot reach the backend. Check that the local server is running, then refresh the connection status."); }
  let data;
  try { data = await response.json(); }
  catch (_) { throw new Error(`The backend returned an unreadable response (HTTP ${response.status}).`); }
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data);
    throw new Error(`HTTP ${response.status}: ${detail}`);
  }
  return data;
}
function bubble(role, content, label) {
  byId("empty-state")?.remove();
  const row = document.createElement("article"); row.className = `bubble-row ${role}`;
  const heading = document.createElement("p"); heading.className = "bubble-label"; heading.textContent = label;
  const text = document.createElement("p"); text.className = "bubble"; text.textContent = content;
  row.append(heading, text); log.append(row); log.scrollTop = log.scrollHeight;
  return row;
}
function clearView() {
  log.replaceChildren();
  const notice = document.createElement("div"); notice.id = "empty-state"; notice.className = "empty-state";
  const title = document.createElement("h3"); title.textContent = "A fresh view. The memories stay.";
  const text = document.createElement("p"); text.textContent = "No saved history was deleted. Your next messages will appear here.";
  notice.append(title, text); log.append(notice); error();
}
async function connection() {
  try {
    const data = await request("/demo/api/status");
    byId("backend-status").textContent = "Backend connected"; byId("backend-status").className = "status online";
    byId("model-status").textContent = !data.ollama_available ? "Ollama unavailable" : data.model_installed ? `${data.model} available` : `${data.model} not installed`;
    byId("database-path").textContent = data.database_path;
    byId("summary-flag").textContent = data.summary_context_enabled ? "Summary context enabled" : "Summary context disabled";
  } catch (e) {
    byId("backend-status").textContent = "Backend disconnected"; byId("backend-status").className = "status offline";
    byId("model-status").textContent = "Ollama status unknown";
    byId("summary-flag").textContent = "Configuration unavailable";
  }
}
async function preview(loadHistory = false) {
  const pair = identity(), version = ++previewVersion, pairVersion = identityVersion;
  if (!pair.player_id || !pair.npc_id) { byId("memory-state").textContent = "Enter both player and NPC IDs."; return; }
  byId("memory-state").textContent = "Reading saved data…";
  try {
    const data = await request("/demo/api/context", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...pair, message: input.value})});
    if (version !== previewVersion || pairVersion !== identityVersion) return;
    byId("preview-query").textContent = data.query || "(empty draft — no keyword query)";
    byId("recent-data").textContent = JSON.stringify(data.recent_messages, null, 2);
    byId("keyword-data").textContent = JSON.stringify(data.keyword_memories, null, 2);
    byId("saved-data").textContent = JSON.stringify(data.saved_summary, null, 2);
    byId("summary-data").textContent = JSON.stringify(data.summary_context, null, 2);
    byId("retention-data").textContent = Array.isArray(data.summary_retention_review)
      ? JSON.stringify(data.summary_retention_review, null, 2)
      : "Retention review unavailable. Restart the backend to load the updated code.";
    byId("recent-count").textContent = `(${data.recent_messages.length})`;
    byId("keyword-count").textContent = `(${data.keyword_memories.length})`;
    byId("summary-flag").textContent = data.summary_context_enabled ? "Summary context enabled" : "Summary context disabled";
    byId("memory-state").textContent = "Preview refreshed from SQLite. It describes the next request, not the previous reply.";
    if (loadHistory && !busy) {
      log.replaceChildren();
      if (!data.recent_messages.length) clearView();
      for (const item of data.recent_messages) bubble(item.role, item.content, item.role === "user" ? pair.player_id : pair.npc_id);
      log.scrollTo({top: log.scrollHeight, behavior: "instant"});
    }
  } catch (e) {
    if (version !== previewVersion || pairVersion !== identityVersion) return;
    byId("memory-state").textContent = `Memory preview unavailable: ${e.message}`;
    for (const id of ["recent-data", "keyword-data", "saved-data", "summary-data", "retention-data"]) byId(id).textContent = "Unavailable — refresh to read current data.";
  }
}
function changeIdentity() {
  identityVersion++; previewVersion++;
  byId("custom-player-wrap").hidden = byId("player-choice").value !== "custom";
  const pair = identity();
  byId("chat-title").textContent = pair.npc_id || "Choose an NPC";
  byId("pair-label").textContent = `Player: ${pair.player_id || "(required)"} · NPC: ${pair.npc_id || "(required)"}`;
  for (const id of ["recent-data", "keyword-data", "saved-data", "summary-data", "retention-data"]) byId(id).textContent = "Loading this player's data…";
  byId("recent-count").textContent = ""; byId("keyword-count").textContent = "";
  clearView(); input.value = ""; preview(true);
}
form.addEventListener("submit", async event => {
  event.preventDefault(); if (busy) return;
  const pair = identity(), message = input.value.trim();
  if (!pair.player_id || !pair.npc_id || !message) { error("Enter a player ID, NPC ID, and message."); return; }
  error(); setBusy(true); const row = bubble("user", message, pair.player_id);
  try {
    const data = await request("/chat", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...pair, message})});
    bubble("assistant", data.reply, data.npc_id); input.value = "";
  } catch (e) {
    const delivery = document.createElement("p"); delivery.className = "delivery"; delivery.textContent = "Delivery not confirmed. Check before retrying."; row.append(delivery);
    error(e.message);
  } finally { setBusy(false); input.focus(); preview(); connection(); }
});
input.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); if (!busy) form.requestSubmit(); }
});
byId("clear-view").addEventListener("click", () => { previewVersion++; clearView(); });
byId("player-choice").addEventListener("change", changeIdentity);
byId("custom-player").addEventListener("change", changeIdentity);
byId("npc-id").addEventListener("change", changeIdentity);
byId("refresh-memory").addEventListener("click", () => preview());
connection(); preview(true); setInterval(connection, 15000);
