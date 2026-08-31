const BATCH_HEADER = "X-Atelier-Batch";
const PANEL_ID = "atelier-dashboard-panel";
const VIEWER_ID = "atelier-batch-pdf-viewer";

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

function refreshDashboardPanel(form) {
  const refreshUrl = form.dataset.dashboardRefreshUrl;
  if (refreshUrl && window.htmx && typeof window.htmx.ajax === "function") {
    window.htmx.ajax("GET", refreshUrl, {
      target: `#${PANEL_ID}`,
      swap: "outerHTML",
    });
    return;
  }
  window.location.reload();
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
      openPdfPreview(blob, filenameFromDisposition(response.headers.get("Content-Disposition")));
      parseToastHeader(response);
      refreshDashboardPanel(form);
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
