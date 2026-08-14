let state = {
  goals: [],
  selectedId: null,
  category: "All",
  search: "",
  whoop: null,
  goodreads: null,
  logs: [],
  editingSampleId: null,
  sampleMessage: "",
  settingsOpen: false,
};

const fmt = new Intl.NumberFormat("en", { maximumFractionDigits: 1 });
const basePath = new URL(document.baseURI).pathname.replace(/\/$/, "");
const categoryOrder = ["Wellness", "Personal Growth", "Me & Angel", "Social Growth", "Personal Finances"];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function api(path, options = {}) {
  const res = await fetch(`${basePath}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function valueLabel(value, unit) {
  return `${fmt.format(value)} ${unit}`.trim();
}

function categories() {
  const available = new Set(state.goals.map((g) => g.category));
  const ordered = categoryOrder.filter((category) => available.has(category));
  const remaining = [...available].filter((category) => !categoryOrder.includes(category)).sort();
  return ["All", ...ordered, ...remaining];
}

function filteredGoals() {
  const q = state.search.trim().toLowerCase();
  return state.goals.filter((goal) => {
    const categoryOk = state.category === "All" || goal.category === state.category;
    const searchOk = !q || `${goal.title} ${goal.category} ${goal.source}`.toLowerCase().includes(q);
    return categoryOk && searchOk;
  }).sort((a, b) => categoryOrder.indexOf(a.category) - categoryOrder.indexOf(b.category));
}

function renderSummary() {
  const avg = state.goals.length
    ? state.goals.reduce((sum, goal) => sum + goal.progressPct, 0) / state.goals.length
    : 0;
  const onTrack = state.goals.filter((goal) => goal.progressPct >= 70).length;
  const samples = state.goals.reduce((sum, goal) => sum + goal.samples.length, 0);
  const categoriesCount = new Set(state.goals.map((goal) => goal.category)).size;
  document.querySelector("#summary").innerHTML = [
    ["Overall", `${fmt.format(avg)}%`],
    ["Targets on track", `${onTrack}/${state.goals.length}`],
    ["Samples saved", samples],
    ["Categories", categoriesCount],
  ]
    .map(([label, value]) => `<div class="summary-card"><strong>${value}</strong><span>${label}</span></div>`)
    .join("");
}

function renderTabs() {
  const wrap = document.querySelector("#tabs");
  wrap.innerHTML = categories()
    .map((cat) => `<button class="tab ${cat === state.category ? "active" : ""}" data-cat="${cat}">${cat}</button>`)
    .join("");
  wrap.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.category = btn.dataset.cat;
      render();
    });
  });
}

function renderGoals() {
  const wrap = document.querySelector("#goals");
  const template = document.querySelector("#goalCardTemplate");
  wrap.innerHTML = "";
  const goals = filteredGoals();
  if (!goals.some((goal) => goal.id === state.selectedId)) {
    state.selectedId = goals[0]?.id || state.goals[0]?.id || null;
  }
  goals.forEach((goal) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.classList.toggle("selected", goal.id === state.selectedId);
    node.querySelector(".category").textContent = goal.category;
    node.querySelector(".source").textContent = goal.source;
    node.querySelector("h3").textContent = goal.title;
    node.querySelector(".current").textContent = valueLabel(goal.currentValue, goal.targetUnit);
    node.querySelector(".target").textContent = `Target ${valueLabel(goal.targetValue, goal.targetUnit)}`;
    node.querySelector(".bar span").style.width = `${goal.progressPct}%`;
    node.addEventListener("click", () => {
      state.selectedId = goal.id;
      render();
    });
    wrap.appendChild(node);
  });
}

function makeTrend(goal) {
  const points = goal.samples.map((sample) => ({
    date: sample.date,
    value: sample.value,
    label: sample.note.match(/for (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})/)?.slice(1).join(" to ") || sample.date,
  }));
  if (!points.length) {
    return `<div class="trend-empty"><strong>Target ${escapeHtml(valueLabel(goal.targetValue, goal.targetUnit))}</strong><span>No samples recorded yet.</span></div>`;
  }
  const values = points.map((p) => p.value).concat([goal.targetValue]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const w = Math.max(640, points.length * 112);
  const h = 250;
  const pad = { top: 36, right: 38, bottom: 58, left: 38 };
  const x = (i) => pad.left + (i * (w - pad.left - pad.right)) / Math.max(1, points.length - 1);
  const y = (value) => h - pad.bottom - ((value - min) * (h - pad.top - pad.bottom)) / span;
  const path = points.map((p, i) => `${i ? "L" : "M"} ${x(i)} ${y(p.value)}`).join(" ");
  const targetY = y(goal.targetValue);
  const dots = points
    .map((p, i) => `<g><circle cx="${x(i)}" cy="${y(p.value)}" r="5"><title>${p.label}: ${valueLabel(p.value, goal.targetUnit)}</title></circle><text x="${x(i)}" y="${Math.max(17, y(p.value) - 11)}" text-anchor="middle" fill="#14312b" font-size="12" font-weight="700">${escapeHtml(valueLabel(p.value, goal.targetUnit))}</text><text x="${x(i)}" y="${h - 20}" text-anchor="middle" fill="#64605a" font-size="11">${escapeHtml(p.label)}</text></g>`)
    .join("");
  return `
    <svg viewBox="0 0 ${w} ${h}" style="min-width:${w}px" role="img" aria-label="Samples and target for ${goal.title}">
      <rect width="${w}" height="${h}" fill="#fffdf8"></rect>
      <line x1="${pad.left}" x2="${w - pad.right}" y1="${targetY}" y2="${targetY}" stroke="#a86900" stroke-dasharray="6 6"></line>
      <text x="${w - pad.right}" y="${Math.max(18, targetY - 9)}" text-anchor="end" fill="#a86900" font-size="12" font-weight="700">Target ${escapeHtml(valueLabel(goal.targetValue, goal.targetUnit))}</text>
      <path d="${path}" fill="none" stroke="#276ef1" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></path>
      <g fill="#14312b">${dots}</g>
    </svg>`;
}

function renderDetail() {
  const goal = state.goals.find((g) => g.id === state.selectedId);
  const detail = document.querySelector("#detail");
  if (!goal) {
    detail.innerHTML = "<p>No target selected.</p>";
    return;
  }
  detail.innerHTML = `
    <div class="detail-head">
      <p class="eyebrow">${escapeHtml(goal.category)}</p>
      <h2>${escapeHtml(goal.title)}</h2>
      <div class="chips">
        <span class="chip">${escapeHtml(goal.source)}</span>
        <span class="chip">${escapeHtml(goal.cadence)}</span>
        <span class="chip">${goal.direction === "down" ? "lower is better" : "higher is better"}</span>
      </div>
    </div>
    <div class="detail-grid">
      <div class="mini-stat"><span>Current</span><strong>${valueLabel(goal.currentValue, goal.targetUnit)}</strong></div>
      <div class="mini-stat"><span>Target</span><strong>${valueLabel(goal.targetValue, goal.targetUnit)}</strong></div>
      <div class="mini-stat"><span>Baseline</span><strong>${goal.baselineLabel}</strong></div>
      <div class="mini-stat"><span>Progress</span><strong>${goal.progressPct}%</strong></div>
    </div>
    <div class="trend">${makeTrend(goal)}</div>
    <form class="sample-form" id="sampleForm">
      <label>Date<input id="sampleDate" type="date" value="${new Date().toISOString().slice(0, 10)}"></label>
      <label>Value<input id="sampleValue" type="number" step="0.01" required placeholder="${goal.targetUnit}"></label>
      <label>Note<input id="sampleNote" type="text" placeholder="Optional context"></label>
      <button type="submit">Save progress sample</button>
    </form>
    <h2>Plan</h2>
    <ul class="plan-list">${goal.plan.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    <p class="sample-message" role="status">${escapeHtml(state.sampleMessage)}</p>
    <h2>Recent Samples</h2>
    <ul class="sample-list">${
      goal.samples
        .slice()
        .reverse()
        .slice(0, 8)
        .map((s) => s.id === state.editingSampleId ? `
          <li class="sample-row sample-row-editing">
            <form class="sample-edit-form" data-sample-id="${escapeHtml(s.id)}">
              <input name="date" type="date" value="${escapeHtml(s.date)}" required aria-label="Sample date">
              <input name="value" type="number" step="0.01" value="${escapeHtml(s.value)}" required aria-label="Sample value">
              <input name="note" type="text" value="${escapeHtml(s.note)}" placeholder="Optional context" aria-label="Sample note">
              <button type="submit" class="sample-action">Save</button>
              <button type="button" class="sample-action" data-cancel-edit>Cancel</button>
            </form>
          </li>` : `
          <li class="sample-row">
            <div class="sample-copy">${escapeHtml(s.date)}: ${escapeHtml(valueLabel(s.value, goal.targetUnit))} - ${escapeHtml(s.source)}${s.note ? ` - ${escapeHtml(s.note)}` : ""}</div>
            <div class="sample-actions">
              <button type="button" class="sample-action" data-edit-sample="${escapeHtml(s.id)}">Edit</button>
              <button type="button" class="sample-action sample-delete" data-delete-sample="${escapeHtml(s.id)}">Delete</button>
            </div>
          </li>`)
        .join("") || "<li>No samples yet.</li>"
    }</ul>
  `;
  document.querySelector("#sampleForm").addEventListener("submit", saveSample);
  detail.querySelectorAll("[data-edit-sample]").forEach((button) => button.addEventListener("click", () => {
    state.editingSampleId = button.dataset.editSample;
    state.sampleMessage = "";
    renderDetail();
  }));
  detail.querySelectorAll("[data-cancel-edit]").forEach((button) => button.addEventListener("click", () => {
    state.editingSampleId = null;
    state.sampleMessage = "";
    renderDetail();
  }));
  detail.querySelectorAll(".sample-edit-form").forEach((form) => form.addEventListener("submit", saveSampleEdit));
  detail.querySelectorAll("[data-delete-sample]").forEach((button) => button.addEventListener("click", () => deleteSavedSample(button.dataset.deleteSample)));
}

function renderWhoop() {
  const connection = state.whoop?.connection;
  if (!connection) return;
  const clientId = document.querySelector("#whoopClientId");
  const redirectUri = document.querySelector("#whoopRedirectUri");
  const connect = document.querySelector("#whoopConnectBtn");
  const sync = document.querySelector("#whoopSyncBtn");
  const status = document.querySelector("#whoopStatus");
  clientId.value = connection.clientId || "";
  redirectUri.value = connection.redirectUri || "";
  connect.classList.toggle("disabled", !connection.configured);
  connect.setAttribute("aria-disabled", String(!connection.configured));
  sync.disabled = !connection.connected;
  if (connection.connected) {
    status.textContent = connection.lastSyncAt
      ? `Connected. ${connection.lastSyncDetail || `Last sync ${new Date(connection.lastSyncAt).toLocaleString()}`}`
      : "Connected and ready to sync.";
  } else if (connection.configured) {
    status.textContent = "Settings saved. Connect your WHOOP account to begin syncing.";
  } else {
    status.textContent = "Set up your WHOOP Developer app to connect your account.";
  }
}

function renderGoodreads() {
  const connection = state.goodreads?.connection;
  if (!connection) return;
  document.querySelector("#goodreadsFeedUrl").value = connection.feedUrl || "";
  document.querySelector("#goodreadsSyncBtn").disabled = !connection.configured;
  document.querySelector("#goodreadsStatus").textContent = connection.lastSyncAt
    ? connection.lastSyncDetail : connection.configured ? "Feed saved. Ready to sync books." : "Add your public Goodreads read-shelf RSS URL.";
}

function logDetail(log) {
  const detail = log.detail || {};
  const entries = Object.entries(detail).filter(([, value]) => value !== "" && value != null);
  if (!entries.length) return "";
  return entries.map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : value}`).join(" · ");
}

function renderLogs() {
  const list = document.querySelector("#logsList");
  if (!state.logs.length) {
    list.innerHTML = '<p class="log-empty">No server activity recorded yet.</p>';
    return;
  }
  list.innerHTML = state.logs.map((log) => `
    <article class="log-row">
      <span class="log-level ${escapeHtml(log.level)}">${escapeHtml(log.level)}</span>
      <div class="log-copy">
        <div><strong>${escapeHtml(log.event)}</strong><span class="log-source">${escapeHtml(log.source)}</span></div>
        ${logDetail(log) ? `<p>${escapeHtml(logDetail(log))}</p>` : ""}
      </div>
      <time datetime="${escapeHtml(log.at)}">${escapeHtml(new Date(log.at).toLocaleString())}</time>
    </article>`).join("");
}

function setSettingsMode(open) {
  state.settingsOpen = open;
  document.querySelectorAll(".dashboard-only").forEach((node) => { node.hidden = open; });
  document.querySelectorAll(".settings-only").forEach((node) => { node.hidden = !open; });
  document.querySelector("#settingsBtn").textContent = open ? "Dashboard" : "Settings";
}

async function loadWhoop() {
  state.whoop = await api("/api/whoop/settings");
  renderWhoop();
}

async function loadGoodreads() {
  state.goodreads = await api("/api/goodreads/settings");
  renderGoodreads();
}

async function loadLogs() {
  const data = await api("/api/logs?limit=150");
  state.logs = data.logs;
  renderLogs();
}

async function saveGoodreads(event) {
  event.preventDefault();
  const message = document.querySelector("#goodreadsMessage");
  message.textContent = "Saving Goodreads feed...";
  try {
    state.goodreads = await api("/api/goodreads/settings", { method: "POST", body: JSON.stringify({ feedUrl: document.querySelector("#goodreadsFeedUrl").value }) });
    renderGoodreads();
    message.textContent = "Goodreads feed saved. You can now sync books.";
  } catch (error) { message.textContent = error.message; }
}

async function syncGoodreads() {
  const message = document.querySelector("#goodreadsMessage");
  message.textContent = "Syncing Goodreads books...";
  try {
    const result = await api("/api/goodreads/sync", { method: "POST", body: "{}" });
    state.goodreads = { connection: result.connection };
    renderGoodreads();
    message.textContent = result.detail;
    await load();
  } catch (error) { message.textContent = error.message; }
}

async function saveWhoopSettings(event) {
  event.preventDefault();
  const message = document.querySelector("#whoopMessage");
  message.textContent = "Saving WHOOP settings...";
  try {
    state.whoop = await api("/api/whoop/settings", {
      method: "POST",
      body: JSON.stringify({
        clientId: document.querySelector("#whoopClientId").value,
        clientSecret: document.querySelector("#whoopClientSecret").value,
        redirectUri: document.querySelector("#whoopRedirectUri").value,
      }),
    });
    document.querySelector("#whoopClientSecret").value = "";
    renderWhoop();
    message.textContent = "WHOOP settings saved. You can now connect your account.";
  } catch (error) {
    message.textContent = error.message;
  }
}

async function syncWhoop() {
  const message = document.querySelector("#whoopMessage");
  const button = document.querySelector("#whoopSyncBtn");
  button.disabled = true;
  message.textContent = "Syncing WHOOP readings...";
  try {
    const result = await api("/api/whoop/sync", { method: "POST", body: JSON.stringify({ days: 30 }) });
    state.whoop = { connection: result.connection };
    renderWhoop();
    message.textContent = result.detail;
    await load();
  } catch (error) {
    message.textContent = error.message;
  } finally {
    button.disabled = !state.whoop?.connection?.connected;
  }
}

async function resetAllSamples() {
  if (!window.confirm("Delete every saved progress sample across all targets? Connection settings and activity logs will remain.")) return;
  const button = document.querySelector("#resetSamplesBtn");
  const message = document.querySelector("#resetSamplesMessage");
  button.disabled = true;
  try {
    const result = await api("/api/samples/reset", { method: "POST", body: "{}" });
    state.goals = result.goals; state.selectedId = null; state.editingSampleId = null; state.sampleMessage = ""; render();
    message.textContent = `${result.deleted} samples reset.`;
    await loadLogs();
  } catch (error) { message.textContent = error.message; } finally { button.disabled = false; }
}

async function saveSample(event) {
  event.preventDefault();
  const goal = state.goals.find((g) => g.id === state.selectedId);
  try {
    const result = await api("/api/samples", {
      method: "POST",
      body: JSON.stringify({
        goalId: goal.id,
        date: document.querySelector("#sampleDate").value,
        value: document.querySelector("#sampleValue").value,
        note: document.querySelector("#sampleNote").value,
        source: "manual",
      }),
    });
    state.goals = result.goals;
    state.sampleMessage = "Progress sample saved.";
    render();
  } catch (error) {
    state.sampleMessage = error.message;
    renderDetail();
  }
}

async function saveSampleEdit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    const result = await api(`/api/samples/${form.dataset.sampleId}`, {
      method: "PUT",
      body: JSON.stringify({ date: form.elements.date.value, value: form.elements.value.value, note: form.elements.note.value }),
    });
    state.goals = result.goals;
    state.editingSampleId = null;
    state.sampleMessage = "Progress sample updated.";
    render();
  } catch (error) {
    state.sampleMessage = error.message;
    renderDetail();
  }
}

async function deleteSavedSample(sampleId) {
  if (!window.confirm("Delete this saved progress sample?")) return;
  try {
    const result = await api(`/api/samples/${sampleId}/delete`, { method: "POST", body: "{}" });
    state.goals = result.goals;
    state.editingSampleId = null;
    state.sampleMessage = "Progress sample deleted.";
    render();
  } catch (error) {
    state.sampleMessage = error.message;
    renderDetail();
  }
}

function render() {
  renderSummary();
  renderTabs();
  renderGoals();
  renderDetail();
  renderWhoop();
  renderGoodreads();
  renderLogs();
}

async function load() {
  const data = await api("/api/goals");
  state.goals = data.goals;
  if (!state.selectedId) state.selectedId = state.goals[0]?.id;
  render();
}

document.querySelector("#search").addEventListener("input", (event) => {
  state.search = event.target.value;
  render();
});
document.querySelector("#refreshBtn").addEventListener("click", load);
document.querySelector("#whoopForm").addEventListener("submit", saveWhoopSettings);
document.querySelector("#whoopSyncBtn").addEventListener("click", syncWhoop);
document.querySelector("#goodreadsForm").addEventListener("submit", saveGoodreads);
document.querySelector("#goodreadsSyncBtn").addEventListener("click", syncGoodreads);
document.querySelector("#refreshLogsBtn").addEventListener("click", loadLogs);
document.querySelector("#resetSamplesBtn").addEventListener("click", resetAllSamples);
document.querySelector("#settingsBtn").addEventListener("click", () => setSettingsMode(!state.settingsOpen));

Promise.all([load(), loadWhoop(), loadGoodreads(), loadLogs()]).then(() => {
  const params = new URLSearchParams(location.search);
  if (params.get("whoop") === "connected") {
    document.querySelector("#whoopMessage").textContent = "WHOOP connected. Sync when you are ready.";
    history.replaceState({}, "", `${basePath}/`);
  }
  if (params.get("whoop") === "error") {
    document.querySelector("#whoopMessage").textContent = params.get("message") || "WHOOP connection did not complete.";
    history.replaceState({}, "", `${basePath}/`);
  }
}).catch((error) => {
  document.body.innerHTML = `<main><p>${error.message}</p></main>`;
});
