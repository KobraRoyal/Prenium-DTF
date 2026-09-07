const readChartData = (id) => {
  const source = document.getElementById(id);
  if (!source) return null;
  try {
    return JSON.parse(source.textContent || "{}");
  } catch (_error) {
    return null;
  }
};

const drilldown = document.getElementById("client-dashboard-drilldown");
const drilldownTitle = document.getElementById("client-dashboard-drilldown-title");
const drilldownDescription = document.getElementById("client-dashboard-drilldown-description");
const drilldownList = document.getElementById("client-dashboard-drilldown-list");

const showDrilldown = (data) => {
  if (!data || !drilldown || !drilldownTitle || !drilldownDescription || !drilldownList) return;
  drilldownTitle.textContent = data.title || "Éléments concernés";
  drilldownDescription.textContent = data.description || "";
  drilldownList.replaceChildren();
  const items = Array.isArray(data.items) ? data.items : [];
  if (items.length) {
    const list = document.createElement("ul");
    list.className = "client-dashboard-drilldown__list";
    items.forEach((item) => {
      const row = document.createElement("li");
      const link = document.createElement("a");
      link.href = item.url || "#";
      link.textContent = item.title || "Ouvrir";
      const detail = document.createElement("span");
      detail.textContent = item.detail || "";
      row.append(link, detail);
      list.append(row);
    });
    drilldownList.append(list);
  } else {
    const empty = document.createElement("p");
    empty.className = "client-dashboard-drilldown__empty";
    empty.textContent = "Aucun élément à afficher pour cette sélection.";
    drilldownList.append(empty);
  }
  if (data.all_url) {
    const link = document.createElement("a");
    link.className = "ui-btn ui-btn-secondary ui-btn-sm client-dashboard-drilldown__all";
    link.href = data.all_url;
    link.textContent = data.all_label || "Tout voir";
    drilldownList.append(link);
  }
  drilldown.hidden = false;
  drilldown.scrollIntoView({ behavior: "smooth", block: "nearest" });
};

document.querySelector("[data-dashboard-drilldown-close]")?.addEventListener("click", () => {
  if (drilldown) drilldown.hidden = true;
});

const styles = getComputedStyle(document.documentElement);
const token = (name, fallback) => styles.getPropertyValue(name).trim() || fallback;
const brand = token("--brand", "#ff8775");
const success = token("--success", "#287451");
const warning = token("--warning", "#8b5d08");
const muted = token("--muted", "#6b675c");
const line = token("--line", "#e2dccb");
const surface = token("--surface-raised", "#fffdf8");

const budgetCanvas = document.getElementById("client-budget-chart");
const budget = readChartData("client-budget-chart-data");
if (budgetCanvas instanceof HTMLCanvasElement && budget && window.Chart) {
  new window.Chart(budgetCanvas, {
    type: "bar",
    data: {
      labels: budget.labels || [],
      datasets: [
        { label: "Commandé", data: budget.ordered || [], backgroundColor: `${brand}AA`, borderRadius: 5 },
        { label: "Réglé", data: budget.paid || [], backgroundColor: `${success}CC`, borderRadius: 5 },
        { label: "À régler", data: budget.awaiting || [], backgroundColor: `${warning}B8`, borderRadius: 5 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      onClick: (_event, elements) => {
        const selected = elements[0];
        if (!selected) return;
        const series = ["ordered", "paid", "awaiting"][selected.datasetIndex];
        showDrilldown(budget.drilldowns?.[series]?.[selected.index]);
      },
      plugins: {
        legend: { align: "end", labels: { boxWidth: 10, boxHeight: 10, color: muted, usePointStyle: true } },
        tooltip: { backgroundColor: "#1a1815", padding: 10, callbacks: { label: (context) => `${context.dataset.label} : ${Number(context.raw || 0).toLocaleString("fr-FR", { style: "currency", currency: "EUR" })}` } },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: muted, font: { size: 11 } }, border: { display: false } },
        y: { beginAtZero: true, ticks: { color: muted, font: { size: 11 }, callback: (value) => `${value} €` }, grid: { color: line }, border: { display: false } },
      },
    },
  });
}

const activityCanvas = document.getElementById("client-activity-chart");
const activity = readChartData("client-activity-chart-data");
if (activityCanvas instanceof HTMLCanvasElement && activity && window.Chart) {
  new window.Chart(activityCanvas, {
    type: "doughnut",
    data: { labels: activity.labels || [], datasets: [{ data: activity.values || [], backgroundColor: [warning, brand, success], borderColor: surface, borderWidth: 3 }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "68%",
      onClick: (_event, elements) => {
        const selected = elements[0];
        if (selected) showDrilldown(activity.drilldowns?.[selected.index]);
      },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10, color: muted, usePointStyle: true } },
        tooltip: { backgroundColor: "#1a1815", padding: 10 },
      },
    },
  });
}

const volumeCanvas = document.getElementById("client-volume-chart");
const volume = readChartData("client-volume-chart-data");
if (volumeCanvas instanceof HTMLCanvasElement && volume && window.Chart) {
  new window.Chart(volumeCanvas, {
    type: "doughnut",
    data: {
      datasets: [{
        data: [volume.achieved || 0, volume.remaining || 0],
        backgroundColor: [brand, line],
        borderWidth: 0,
        borderRadius: 8,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "78%",
      rotation: -90,
      circumference: 180,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
    },
  });
}
