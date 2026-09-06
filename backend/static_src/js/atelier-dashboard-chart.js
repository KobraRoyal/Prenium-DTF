const canvas = document.getElementById("atelier-production-chart-canvas");
const source = document.getElementById("atelier-production-chart-data");

if (canvas instanceof HTMLCanvasElement && source && window.Chart) {
  const trend = JSON.parse(source.textContent || "{}");
  const styles = getComputedStyle(document.documentElement);
  const brand = styles.getPropertyValue("--brand").trim() || "#ff8775";
  const success = styles.getPropertyValue("--success").trim() || "#287451";
  const muted = styles.getPropertyValue("--muted").trim() || "#6b675c";
  const line = styles.getPropertyValue("--line").trim() || "#e2dccb";

  new window.Chart(canvas, {
    type: "line",
    data: {
      labels: trend.labels || [],
      datasets: [
        {
          label: "Entrées Atelier",
          data: trend.entry_values || [],
          borderColor: brand,
          backgroundColor: `${brand}22`,
          fill: true,
          tension: 0.38,
          pointRadius: 3,
          pointHoverRadius: 5,
          pointBackgroundColor: brand,
        },
        {
          label: "Terminées",
          data: trend.completed_values || [],
          borderColor: success,
          backgroundColor: "transparent",
          tension: 0.38,
          pointRadius: 3,
          pointHoverRadius: 5,
          pointBackgroundColor: success,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: {
        legend: { align: "end", labels: { boxWidth: 10, boxHeight: 10, color: muted, usePointStyle: true } },
        tooltip: { backgroundColor: "#1a1815", padding: 10, displayColors: true },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: muted, font: { size: 11 } }, border: { display: false } },
        y: { beginAtZero: true, ticks: { precision: 0, color: muted, font: { size: 11 } }, grid: { color: line }, border: { display: false } },
      },
    },
  });
}
