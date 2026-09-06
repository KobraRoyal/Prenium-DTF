const canvas = document.getElementById("atelier-production-chart-canvas");
const source = document.getElementById("atelier-production-chart-data");

if (canvas instanceof HTMLCanvasElement && source && window.Chart) {
  const trend = JSON.parse(source.textContent || "{}");
  const styles = getComputedStyle(document.documentElement);
  const brand = styles.getPropertyValue("--brand").trim() || "#ff8775";
  const success = styles.getPropertyValue("--success").trim() || "#287451";
  const muted = styles.getPropertyValue("--muted").trim() || "#6b675c";
  const line = styles.getPropertyValue("--line").trim() || "#e2dccb";

  // With indexed tooltips, Chart.js otherwise anchors between series. Keeping
  // the tooltip on the highest value makes it clearly belong to its data point.
  window.Chart.Tooltip.positioners.topmost = (items) => {
    const topmost = items.reduce(
      (candidate, item) => (!candidate || item.element.y < candidate.element.y ? item : candidate),
      null,
    );
    return topmost ? { x: topmost.element.x, y: topmost.element.y } : false;
  };

  new window.Chart(canvas, {
    type: "line",
    data: {
      labels: trend.labels || [],
      datasets: [
        {
          label: "Nouvelles commandes",
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
        tooltip: {
          backgroundColor: "#1a1815",
          displayColors: true,
          padding: 10,
          position: "topmost",
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: muted, font: { size: 11 } }, border: { display: false } },
        y: { beginAtZero: true, ticks: { precision: 0, color: muted, font: { size: 11 } }, grid: { color: line }, border: { display: false } },
      },
    },
  });
}
