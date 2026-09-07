const readChartData = (id) => {
  const source = document.getElementById(id);
  if (!source) return null;
  try {
    return JSON.parse(source.textContent || "{}");
  } catch (_error) {
    return null;
  }
};

const styles = getComputedStyle(document.documentElement);
const token = (name, fallback) => styles.getPropertyValue(name).trim() || fallback;
const brand = token("--brand", "#ff8775");
const success = token("--success", "#287451");
const warning = token("--warning", "#8b5d08");
const muted = token("--muted", "#6b675c");
const line = token("--line", "#e2dccb");

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
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
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
    data: { labels: activity.labels || [], datasets: [{ data: activity.values || [], backgroundColor: [warning, brand, success], borderColor: token("--surface-raised", "#fffdf8"), borderWidth: 3 }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "68%",
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10, color: muted, usePointStyle: true } },
        tooltip: { backgroundColor: "#1a1815", padding: 10 },
      },
    },
  });
}
