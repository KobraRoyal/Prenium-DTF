const BATCH_HEADER = "X-Atelier-Batch";
const BATCH_ORDER_IDS_HEADER = "X-Prenium-Batch-Order-Ids";
const PANEL_ID = "atelier-dashboard-panel";
const VIEWER_ID = "atelier-batch-pdf-viewer";

const EMPTY_WORKLIST_HTML = `
  <div class="atelier-worklist__empty">
    <div class="empty-state text-center">
      <h3 class="mt-0 font-display text-lg text-[color:var(--ink)]">Aucun OF en attente</h3>
      <p class="muted mt-2">Tous les OF ont été émis. Nouvelles commandes et contrôle : pilotage Atelier.</p>
    </div>
  </div>
`;

let activeBlobUrl = null;
let viewerEscapeHandler = null;
let batchInFlight = false;

function parseToastHeader(response) {
  const raw = response.headers.get("X-Prenium-Toast");
  if (!raw || typeof window.preniumToast !== "function") {
    return;
  }
  try {
    const data = JSON.parse(raw);
    window.preniumToast(data.message, data.variant || (response.ok ? "success" : "error"));
  } catch {
    window.preniumToast(raw, response.ok ? "success" : "error");
  }
}

function filenameFromDisposition(header) {
  if (!header) {
    return "OF-lot.pdf";
  }
  const match = /filename="([^"]+)"/.exec(header);
  return match ? match[1] : "OF-lot.pdf";
}

function closePdfViewer() {
  const viewer = document.getElementById(VIEWER_ID);
  if (!viewer) {
    return;
  }
  const iframe = viewer.querySelector("iframe");
  if (iframe instanceof HTMLIFrameElement) {
    // Couper onload avant de vider src : sinon certains navigateurs
    // relancent print() / rechargent le PDF au moment de la fermeture.
    iframe.onload = null;
    iframe.src = "about:blank";
  }
  viewer.hidden = true;
  viewer.setAttribute("aria-hidden", "true");
  document.body.classList.remove("atelier-batch-pdf-viewer-open");
  if (activeBlobUrl) {
    URL.revokeObjectURL(activeBlobUrl);
    activeBlobUrl = null;
  }
  if (viewerEscapeHandler) {
    document.removeEventListener("keydown", viewerEscapeHandler);
    viewerEscapeHandler = null;
  }
}

function ensurePdfViewer() {
  let viewer = document.getElementById(VIEWER_ID);
  if (viewer) {
    return viewer;
  }

  viewer = document.createElement("div");
  viewer.id = VIEWER_ID;
  viewer.className = "atelier-batch-pdf-viewer";
  viewer.hidden = true;
  viewer.setAttribute("role", "dialog");
  viewer.setAttribute("aria-modal", "true");
  viewer.setAttribute("aria-labelledby", "atelier-batch-pdf-viewer-label");
  viewer.innerHTML = `
    <div class="atelier-batch-pdf-viewer__backdrop" data-batch-pdf-close tabindex="-1"></div>
    <div class="atelier-batch-pdf-viewer__panel">
      <header class="atelier-batch-pdf-viewer__toolbar">
        <p class="atelier-batch-pdf-viewer__title" id="atelier-batch-pdf-viewer-label">Ordres de fabrication</p>
        <div class="atelier-batch-pdf-viewer__actions">
          <button type="button" class="ui-btn ui-btn-primary ui-btn-sm" data-batch-pdf-print>Imprimer</button>
          <button type="button" class="ui-btn ui-btn-secondary ui-btn-sm" data-batch-pdf-close>Fermer</button>
        </div>
      </header>
      <iframe class="atelier-batch-pdf-viewer__frame" title="Aperçu des ordres de fabrication"></iframe>
    </div>
  `;
  document.body.append(viewer);

  viewer.querySelector("[data-batch-pdf-print]")?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const frame = viewer.querySelector("iframe");
    if (!(frame instanceof HTMLIFrameElement) || !frame.contentWindow) {
      return;
    }
    frame.contentWindow.focus();
    frame.contentWindow.print();
  });
  viewer.querySelectorAll("[data-batch-pdf-close]").forEach((element) => {
    element.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      closePdfViewer();
    });
  });

  return viewer;
}

function openPdfPreview(blob, filename) {
  closePdfViewer();
  const url = URL.createObjectURL(blob);
  activeBlobUrl = url;
  const viewer = ensurePdfViewer();
  const iframe = viewer.querySelector("iframe");
  const label = viewer.querySelector("#atelier-batch-pdf-viewer-label");
  const printButton = viewer.querySelector("[data-batch-pdf-print]");
  if (label) {
    label.textContent = filename.replace(/\.pdf$/i, "") || "Ordres de fabrication";
  }
  if (!(iframe instanceof HTMLIFrameElement)) {
    return;
  }

  // Aperçu uniquement : l’utilisateur clique sur « Imprimer » quand il est prêt.
  iframe.onload = null;
  iframe.src = url;
  viewer.hidden = false;
  viewer.removeAttribute("aria-hidden");
  document.body.classList.add("atelier-batch-pdf-viewer-open");
  if (printButton instanceof HTMLButtonElement) {
    printButton.focus();
  }

  viewerEscapeHandler = (event) => {
    if (event.key === "Escape") {
      closePdfViewer();
    }
  };
  document.addEventListener("keydown", viewerEscapeHandler);
}

function setBatchPrintingState(panel, printing) {
  if (!panel) {
    return;
  }
  panel.classList.toggle("is-batch-printing", printing);
  panel.querySelectorAll(
    "button[type='submit'][form='atelier-worklist-form'], #atelier-worklist-form button[type='submit']"
  ).forEach((button) => {
    if (!(button instanceof HTMLButtonElement)) {
      return;
    }
    button.classList.toggle("is-loading", printing);
    button.toggleAttribute("aria-busy", printing);
    if (printing) {
      button.dataset.batchWasDisabled = button.disabled ? "true" : "false";
      button.disabled = true;
      return;
    }
    if (button.dataset.batchWasDisabled === "false") {
      button.disabled = false;
    }
    delete button.dataset.batchWasDisabled;
  });
}

function parsePrintedOrderIds(response, formData) {
  const raw = response.headers.get(BATCH_ORDER_IDS_HEADER);
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed.map(String);
      }
    } catch {
      /* Fallback sur la sélection envoyée. */
    }
  }
  return formData.getAll("order_public_ids").map(String);
}

function collectWorklistMetrics(panel) {
  const metrics = {
    unprinted: 0,
    pending_review: 0,
    changes_requested: 0,
    files_validated: 0,
  };
  const seen = new Set();
  panel.querySelectorAll("[data-worklist-order-id]").forEach((element) => {
    const orderId = element.dataset.worklistOrderId;
    if (!orderId || seen.has(orderId)) {
      return;
    }
    seen.add(orderId);
    metrics.unprinted += 1;
    const status = element.dataset.reviewStatus;
    if (status === "missing_files" || status === "pending") {
      metrics.pending_review += 1;
    }
    if (status === "changes_requested") {
      metrics.changes_requested += 1;
    }
    if (status === "approved") {
      metrics.files_validated += 1;
    }
  });
  return metrics;
}

function updateKpiValue(panel, label, value) {
  panel.querySelectorAll(".ui-kpi-card").forEach((card) => {
    const cardLabel = card.querySelector(".ui-kpi-card__top .muted")?.textContent?.trim();
    if (cardLabel !== label) {
      return;
    }
    const valueNode = card.querySelector(".ui-kpi-card__value");
    if (valueNode) {
      valueNode.textContent = String(value);
    }
    card.classList.toggle("is-ready", label === "OF non imprimés" && value > 0);
    card.classList.toggle("is-attention", label === "À contrôler" && value > 0);
    card.classList.toggle("is-danger", label === "Corrections client" && value > 0);
    if (label === "Fichiers validés") {
      card.classList.toggle("is-ready", value > 0);
    }
  });
}

function syncWorklistCommandUi(panel, form, metrics) {
  const badge = panel.querySelector(".atelier-worklist-command__head .badge");
  if (badge) {
    badge.textContent = `${metrics.unprinted} en attente`;
  }

  const batchLimit = Number.parseInt(form.dataset.batchPrintLimit || "20", 10);
  const batchCount = Math.min(metrics.unprinted, Number.isFinite(batchLimit) ? batchLimit : 20);
  const selectAllButton = panel.querySelector(
    ".atelier-worklist-command__tools button[type='button']"
  );
  if (selectAllButton instanceof HTMLButtonElement) {
    selectAllButton.disabled = metrics.unprinted === 0;
  }

  const batchButton = panel.querySelector("[form='atelier-worklist-form'][name='batch_mode'][value='all_unprinted']");
  if (batchButton instanceof HTMLButtonElement) {
    batchButton.disabled = metrics.unprinted === 0;
    if (metrics.unprinted === 0) {
      batchButton.textContent = "Imprimer le lot";
      batchButton.removeAttribute("title");
    } else if (metrics.unprinted > batchCount) {
      batchButton.textContent = `Imprimer le lot (${batchCount} plus récents)`;
      batchButton.title = `${metrics.unprinted} OF en attente — ce lot imprime les ${batchCount} plus récentes. Relancez ensuite pour le reste.`;
    } else {
      batchButton.textContent = `Imprimer le lot (${metrics.unprinted})`;
      batchButton.title = "Émet le PDF groupé de tous les OF non imprimés.";
    }
  }
}

function ensureEmptyWorklist(form) {
  if (form.querySelector("[data-worklist-order-id]")) {
    return;
  }
  form.querySelector(".atelier-worklist-table")?.remove();
  if (!form.querySelector(".atelier-worklist__empty")) {
    form.insertAdjacentHTML("beforeend", EMPTY_WORKLIST_HTML);
  }
}

function clearAlpineSelection(panel) {
  const surface = panel.querySelector(".atelier-dashboard-surface");
  if (!surface || !window.Alpine) {
    return;
  }
  const data = window.Alpine.$data(surface);
  if (data && Array.isArray(data.selected)) {
    data.selected = [];
  }
}

function purgePrintedOrdersFromWorklist(panel, form, printedIds) {
  const idSet = new Set(printedIds.map(String));
  panel.querySelectorAll("[data-worklist-order-id]").forEach((element) => {
    if (idSet.has(element.dataset.worklistOrderId || "")) {
      element.remove();
    }
  });

  ensureEmptyWorklist(form);
  const metrics = collectWorklistMetrics(panel);
  updateKpiValue(panel, "OF non imprimés", metrics.unprinted);
  updateKpiValue(panel, "À contrôler", metrics.pending_review);
  updateKpiValue(panel, "Corrections client", metrics.changes_requested);
  updateKpiValue(panel, "Fichiers validés", metrics.files_validated);
  syncWorklistCommandUi(panel, form, metrics);
  clearAlpineSelection(panel);
}

async function handleBatchSubmit(event) {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.matches("[data-atelier-batch]")) {
    return;
  }
  event.preventDefault();
  if (batchInFlight) {
    return;
  }
  batchInFlight = true;

  const panel = document.getElementById(PANEL_ID);
  const submitter = event.submitter;
  const formData = new FormData(form);
  if (submitter instanceof HTMLButtonElement && submitter.name === "batch_mode") {
    formData.set("batch_mode", submitter.value);
  }

  setBatchPrintingState(panel, true);
  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: formData,
      credentials: "same-origin",
      headers: { [BATCH_HEADER]: "1" },
    });
    const contentType = response.headers.get("Content-Type") || "";

    if (response.ok && contentType.includes("application/pdf")) {
      const blob = await response.blob();
      const printedIds = parsePrintedOrderIds(response, formData);
      openPdfPreview(blob, filenameFromDisposition(response.headers.get("Content-Disposition")));
      parseToastHeader(response);
      if (panel && printedIds.length) {
        purgePrintedOrdersFromWorklist(panel, form, printedIds);
      }
      return;
    }

    parseToastHeader(response);
    if (!response.headers.get("X-Prenium-Toast") && typeof window.preniumToast === "function") {
      window.preniumToast("Impression impossible — réessayez.", "error");
    }
  } catch {
    if (typeof window.preniumToast === "function") {
      window.preniumToast("Erreur réseau — réessayez.", "error");
    }
  } finally {
    batchInFlight = false;
    const currentPanel = document.getElementById(PANEL_ID);
    setBatchPrintingState(currentPanel, false);
  }
}

function initBatchSubmitCapture() {
  if (document.body.dataset.atelierBatchSubmitReady === "true") {
    return;
  }
  document.body.dataset.atelierBatchSubmitReady = "true";
  document.addEventListener(
    "submit",
    (event) => {
      handleBatchSubmit(event);
    },
    true
  );
}

function bootAtelierDashboardBatch() {
  initBatchSubmitCapture();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootAtelierDashboardBatch);
} else {
  bootAtelierDashboardBatch();
}
