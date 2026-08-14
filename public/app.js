let state = {
  goals: [],
  selectedId: null,
  category: "All",
  search: "",
  whoop: null,
};

const fmt = new Intl.NumberFormat("en", { maximumFractionDigits: 1 });
const basePath = new URL(document.baseURI).pathname.replace(/\/$/, "");

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
  return ["All", ...new Set(state.goals.map((g) => g.category))];
}

function filteredGoals() {
  const q = state.search.trim().toLowerCase();
  return state.goals.filter((goal) => {
    const categoryOk = state.category === "All" || goal.category === state.category;
    const searchOk = !q || `${goal.title} ${goal.category} ${goal.source}`.toLowerCase().includes(q);
    return categoryOk && searchOk;
  });
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
  const points = [{ date: "Baseline", value: goal.baselineValue }, ...goal.samples.map((s) => ({ date: s.date, value: s.value }))];
  const values = points.map((p) => p.value).concat([goal.targetValue]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const w = 640;
  const h = 210;
  const pad = 34;
  const x = (i) => pad + (i * (w - pad * 2)) / Math.max(1, points.length - 1);
  const y = (value) => h - pad - ((value - min) * (h - pad * 2)) / span;
  const path = points.map((p, i) => `${i ? "L" : "M"} ${x(i)} ${y(p.value)}`).join(" ");
  const targetY = y(goal.targetValue);
  const dots = points
    .map((p, i) => `<circle cx="${x(i)}" cy="${y(p.value)}" r="4"><title>${p.date}: ${valueLabel(p.value, goal.targetUnit)}</title></circle>`)
    .join("");
  return `
    <svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Trend for ${goal.title}">
      <rect width="${w}" height="${h}" fill="#fffdf8"></rect>
      <line x1="${pad}" x2="${w - pad}" y1="${targetY}" y2="${targetY}" stroke="#a86900" stroke-dasharray="6 6"></line>
      <text x="${w - pad}" y="${Math.max(16, targetY - 8)}" text-anchor="end" fill="#a86900" font-size="12">target</text>
      <path d="${path}" fill="none" stroke="#276ef1" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></path>
      <g fill="#14312b">${dots}</g>
      <text x="${pad}" y="${h - 10}" fill="#64605a" font-size="12">${points[0]?.date || ""}</text>
      <text x="${w - pad}" y="${h - 10}" text-anchor="end" fill="#64605a" font-size="12">${points.at(-1)?.date || ""}</text>
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
    <h2>Recent Samples</h2>
    <ul class="sample-list">${
      goal.samples
        .slice()
        .reverse()
        .slice(0, 8)
        .map((s) => `<li>${escapeHtml(s.date)}: ${escapeHtml(valueLabel(s.value, goal.targetUnit))} - ${escapeHtml(s.source)}${s.note ? ` - ${escapeHtml(s.note)}` : ""}</li>`)
        .join("") || "<li>No samples yet.</li>"
    }</ul>
  `;
  document.querySelector("#sampleForm").addEventListener("submit", saveSample);
}

function renderImportGoals() {
  const select = document.querySelector("#importGoal");
  const current = select.value;
  select.innerHTML = `<option value="">Auto-detect</option>` + state.goals.map((g) => `<option value="${g.id}">${g.title}</option>`).join("");
  select.value = current;
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

async function loadWhoop() {
  state.whoop = await api("/api/whoop/settings");
  renderWhoop();
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

async function saveSample(event) {
  event.preventDefault();
  const goal = state.goals.find((g) => g.id === state.selectedId);
  await api("/api/samples", {
    method: "POST",
    body: JSON.stringify({
      goalId: goal.id,
      date: document.querySelector("#sampleDate").value,
      value: document.querySelector("#sampleValue").value,
      note: document.querySelector("#sampleNote").value,
      source: "manual",
    }),
  });
  await load();
}

async function importSamples(event) {
  event.preventDefault();
  const status = document.querySelector("#importStatus");
  status.textContent = "Importing...";
  try {
    const result = await api("/api/import", {
      method: "POST",
      body: JSON.stringify({
        source: document.querySelector("#importSource").value,
        goalId: document.querySelector("#importGoal").value,
        raw: document.querySelector("#importData").value,
      }),
    });
    status.textContent = `Imported ${result.imported} sample(s). Failed ${result.failed}.`;
    await load();
  } catch (error) {
    status.textContent = error.message;
  }
}

async function exportData() {
  const data = await api("/api/export");
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `leaps-export-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function render() {
  renderSummary();
  renderTabs();
  renderGoals();
  renderDetail();
  renderImportGoals();
  renderWhoop();
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
document.querySelector("#exportBtn").addEventListener("click", exportData);
document.querySelector("#importForm").addEventListener("submit", importSamples);
document.querySelector("#whoopForm").addEventListener("submit", saveWhoopSettings);
document.querySelector("#whoopSyncBtn").addEventListener("click", syncWhoop);

Promise.all([load(), loadWhoop()]).then(() => {
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
