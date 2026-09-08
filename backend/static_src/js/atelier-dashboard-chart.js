const canvas = document.getElementById("atelier-production-chart-canvas");
const source = document.getElementById("atelier-production-chart-data");
const revenueCanvas = document.getElementById("atelier-revenue-chart-canvas");
const revenueSource = document.getElementById("atelier-revenue-chart-data");
const meterageCanvas = document.getElementById("atelier-meterage-chart-canvas");
const meterageSource = document.getElementById("atelier-meterage-chart-data");

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

if (meterageCanvas instanceof HTMLCanvasElement && meterageSource && window.Chart) {
  const trend = JSON.parse(meterageSource.textContent || "{}");
  const styles = getComputedStyle(document.documentElement);
  const accent = styles.getPropertyValue("--accent").trim() || "#a83bc4";
  const muted = styles.getPropertyValue("--muted").trim() || "#6b675c";
  const line = styles.getPropertyValue("--line").trim() || "#e2dccb";
  const meters = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });

  new window.Chart(meterageCanvas, {
    type: "line",
    data: {
      labels: trend.labels || [],
      datasets: [{
        label: "Métrage imprimé",
        data: trend.meterage_values || [],
        borderColor: accent,
        backgroundColor: `${accent}20`,
        fill: true,
        tension: 0.35,
        pointRadius: 3,
        pointHoverRadius: 5,
        pointBackgroundColor: accent,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#1a1815",
          padding: 10,
          callbacks: { label: (context) => `Métrage : ${meters.format(context.parsed.y || 0)} m` },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: muted, font: { size: 11 } }, border: { display: false } },
        y: {
          beginAtZero: true,
          ticks: { color: muted, font: { size: 11 }, callback: (value) => `${meters.format(value)} m` },
          grid: { color: line },
          border: { display: false },
        },
      },
    },
  });
}

if (revenueCanvas instanceof HTMLCanvasElement && revenueSource && window.Chart) {
  const trend = JSON.parse(revenueSource.textContent || "{}");
  const styles = getComputedStyle(document.documentElement);
  const brand = styles.getPropertyValue("--brand").trim() || "#ff8775";
  const muted = styles.getPropertyValue("--muted").trim() || "#6b675c";
  const line = styles.getPropertyValue("--line").trim() || "#e2dccb";
  const euro = new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  });

  new window.Chart(revenueCanvas, {
    type: "bar",
    data: {
      labels: trend.labels || [],
      datasets: [{
        label: "CA TTC",
        data: trend.revenue_values || [],
        backgroundColor: `${brand}99`,
        borderColor: brand,
        borderWidth: 1,
        borderRadius: 6,
        maxBarThickness: 38,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#1a1815",
          padding: 10,
          callbacks: { label: (context) => `CA TTC : ${euro.format(context.parsed.y || 0)}` },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: muted, font: { size: 11 } }, border: { display: false } },
        y: {
          beginAtZero: true,
          ticks: { color: muted, font: { size: 11 }, callback: (value) => euro.format(value) },
          grid: { color: line },
          border: { display: false },
        },
      },
    },
  });
}
