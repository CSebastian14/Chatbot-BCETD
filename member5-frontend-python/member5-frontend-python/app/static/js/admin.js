/**
 * BCETD Admin Dashboard Client — Refactored for Python Backend
 *
 * BEFORE: fetch("http://localhost:5678/webhook/analytics/summary")
 * AFTER:  fetch("/api/analytics/summary")
 */

const API = {
  summary: "/api/analytics/summary",
  daily: "/api/analytics/daily",
  categories: "/api/analytics/categories",
  documents: "/api/analytics/documents",
  hourly: "/api/analytics/hourly",
};

const CATEGORY_COLORS = {
  ACADEMIC: "#27AE60",
  ADMINISTRATIVE: "#2B5EA7",
  REJECTED: "#E67E22",
  OFF_TOPIC: "#8E44AD",
  INAPPROPRIATE: "#C0392B",
  UNANSWERED: "#95A5A6",
  ERROR: "#E74C3C",
};

async function fetchJSON(url) {
  try {
    var res = await fetch(url, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) throw new Error("HTTP " + res.status);
    return await res.json();
  } catch (err) {
    console.warn("Failed: " + url, err.message);
    return null;
  }
}

function fmt(n) {
  return n != null ? Number(n).toLocaleString() : "\u2014";
}

async function loadSummary() {
  var data = await fetchJSON(API.summary);
  if (!data) return;
  var d = Array.isArray(data) ? data[0] : data;
  document.getElementById("val-queries-7d").textContent = fmt(d.queries_7d);
  document.getElementById("sub-queries-24h").textContent = "Last 24h: " + fmt(d.queries_24h);
  var rate = parseFloat(d.success_rate_7d) || 0;
  var rateEl = document.getElementById("val-success-rate");
  rateEl.textContent = rate.toFixed(1) + "%";
  rateEl.className = "value " + (rate >= 80 ? "success" : rate >= 60 ? "warning" : "danger");
  var ms = parseInt(d.avg_response_ms) || 0;
  var msEl = document.getElementById("val-response-time");
  msEl.textContent = fmt(ms) + "ms";
  msEl.className = "value " + (ms < 3000 ? "success" : ms < 8000 ? "warning" : "danger");
  document.getElementById("val-sessions").textContent = fmt(d.unique_sessions_7d);
}

async function loadDailyChart() {
  var data = await fetchJSON(API.daily);
  if (!data || !data.length) return;
  new Chart(document.getElementById("chart-daily"), {
    type: "bar",
    data: {
      labels: data.map(function (d) { return (d.day || "").substring(5, 10); }),
      datasets: [
        { label: "Answered", data: data.map(function (d) { return d.answered || 0; }), backgroundColor: "#27AE60", borderRadius: 4 },
        { label: "Unanswered", data: data.map(function (d) { return d.unanswered || 0; }), backgroundColor: "#E67E22", borderRadius: 4 },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: "bottom", labels: { font: { family: "DM Sans", size: 11 } } } },
      scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, beginAtZero: true } },
    },
  });
}

async function loadCategoryChart() {
  var data = await fetchJSON(API.categories);
  if (!data || !data.length) return;
  new Chart(document.getElementById("chart-categories"), {
    type: "doughnut",
    data: {
      labels: data.map(function (d) { return d.category; }),
      datasets: [{ data: data.map(function (d) { return d.count; }), backgroundColor: data.map(function (d) { return CATEGORY_COLORS[d.category] || "#95A5A6"; }), borderWidth: 2, borderColor: "#fff" }],
    },
    options: { responsive: true, plugins: { legend: { position: "bottom" } } },
  });
}

async function loadHourlyChart() {
  var data = await fetchJSON(API.hourly);
  if (!data || !data.length) return;
  new Chart(document.getElementById("chart-hourly"), {
    type: "bar",
    data: {
      labels: data.map(function (d) { return String(d.hour_of_day).padStart(2, "0") + ":00"; }),
      datasets: [{ label: "Queries", data: data.map(function (d) { return d.query_count; }), backgroundColor: "#2B5EA7", borderRadius: 4 }],
    },
    options: { responsive: true, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } }, y: { beginAtZero: true } } },
  });
}

async function loadDocumentsTable() {
  var data = await fetchJSON(API.documents);
  var c = document.getElementById("table-documents");
  if (!data || !data.length) { c.innerHTML = '<div class="loading">No data</div>'; return; }
  var h = '<table class="data-table"><thead><tr><th>Document</th><th>References</th><th>Last used</th></tr></thead><tbody>';
  data.slice(0, 10).forEach(function (d) {
    var lu = d.last_referenced ? new Date(d.last_referenced).toLocaleDateString() : "\u2014";
    h += "<tr><td>" + (d.document_name || "\u2014") + "</td><td>" + fmt(d.reference_count) + "</td><td>" + lu + "</td></tr>";
  });
  c.innerHTML = h + "</tbody></table>";
}

async function loadCategoriesTable() {
  var data = await fetchJSON(API.categories);
  var c = document.getElementById("table-categories");
  if (!data || !data.length) { c.innerHTML = '<div class="loading">No data</div>'; return; }
  var h = '<table class="data-table"><thead><tr><th>Category</th><th>Count</th><th>%</th><th>Avg ms</th></tr></thead><tbody>';
  data.forEach(function (d) {
    var cat = (d.category || "UNKNOWN").toLowerCase();
    h += '<tr><td><span class="tag ' + cat + '">' + d.category + "</span></td><td>" + fmt(d.count) + "</td><td>" + (d.percentage || 0) + "%</td><td>" + fmt(d.avg_response_ms) + "ms</td></tr>";
  });
  c.innerHTML = h + "</tbody></table>";
}

async function loadAll() {
  document.getElementById("refresh-time").textContent = "Last refresh: " + new Date().toLocaleTimeString();
  await Promise.all([loadSummary(), loadDailyChart(), loadCategoryChart(), loadHourlyChart(), loadDocumentsTable(), loadCategoriesTable()]);
}

loadAll();
setInterval(loadAll, 300000);
