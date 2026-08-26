const previewObjectUrls = new WeakMap();
const previewRenderTokens = new WeakMap();
const previewFitObservers = new WeakMap();
/** Dialogs already auto-opened (or dismissed) — avoid htmx:load reopen loops. */
const autoOpenedDialogs = new WeakSet();
const previewZoomMin = 1;
const previewZoomMax = 4;
const previewZoomStep = 0.5;
const browserPreviewMimeTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
const pdfJsModuleUrl = "/static/vendor/pdfjs/pdf.js";
const pdfJsWorkerUrl = "/static/vendor/pdfjs/pdf.worker.js";
let pdfJsPromise = null;
let configuratorEventsBound = false;
let projectDialogToRestore = "";
/** Dialog à ne pas rouvrir après un confirm support / validation réussi. */
let projectDialogCloseOnSuccess = "";

function loadPdfJs() {
  if (pdfJsPromise === null) {
    pdfJsPromise = import(pdfJsModuleUrl).then((pdfJs) => {
      pdfJs.GlobalWorkerOptions.workerSrc = pdfJsWorkerUrl;
      return pdfJs;
    });
  }
  return pdfJsPromise;
}

function findConfiguratorRoot(node) {
  if (!(node instanceof Element)) {
    return null;
  }
  const root = node.closest("[data-b2b-configurator]");
  return root instanceof HTMLElement ? root : null;
}

function setPlaceholder(placeholder, title, detail) {
  if (!(placeholder instanceof HTMLElement)) {
    return;
  }
  const strong = document.createElement("strong");
  const span = document.createElement("span");
  strong.textContent = title;
  span.textContent = detail;
  placeholder.replaceChildren(strong, span);
  placeholder.hidden = false;
}

function formatUploadSize(sizeBytes) {
  const bytes = Math.max(0, Number(sizeBytes) || 0);
  const units = [
    { size: 1024 * 1024, suffix: "Mo" },
    { size: 1024, suffix: "Ko" },
  ];
  const unit = units.find(({ size }) => bytes >= size);
  if (!unit) {
    return `${bytes} octet${bytes > 1 ? "s" : ""}`;
  }
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(bytes / unit.size)} ${unit.suffix}`;
}

function clearConfiguratorPreview(root, title, detail) {
  previewRenderTokens.set(root, Symbol("preview-cleared"));
  const previousUrl = previewObjectUrls.get(root);
  if (previousUrl) {
    URL.revokeObjectURL(previousUrl);
    previewObjectUrls.delete(root);
  }
  root.querySelectorAll("[data-configurator-preview]").forEach((preview) => {
    if (preview instanceof HTMLImageElement) {
      preview.removeAttribute("src");
      setPreviewMediaVisible(preview, false);
    }
  });
  root.querySelectorAll("[data-configurator-document-preview]").forEach((preview) => {
    if (preview instanceof HTMLCanvasElement) {
      const context = preview.getContext("2d", { alpha: true });
      context?.clearRect(0, 0, preview.width, preview.height);
      preview.width = 0;
      preview.height = 0;
      setPreviewMediaVisible(preview, false);
    }
  });
  setPlaceholder(root.querySelector("[data-configurator-placeholder]"), title, detail);
  resetPreviewMediaSizing(root);
  clearPreflightQuality(root);
}

function dpiThresholds(root) {
  const recommended = Number.parseInt(root?.dataset?.recommendedDpi || "300", 10);
  const minimum = Number.parseInt(root?.dataset?.minAcceptableDpi || "200", 10);
  return {
    recommended: Number.isFinite(recommended) && recommended > 0 ? recommended : 300,
    minimum: Number.isFinite(minimum) && minimum > 0 ? minimum : 200,
  };
}

function setQualityStripState(node, level, label, meta) {
  if (!(node instanceof HTMLElement)) {
    return;
  }
  node.classList.remove("is-good", "is-warning", "is-error", "is-pending");
  node.classList.add(`is-${level}`);
  const labelNode = node.querySelector(
    "[data-preflight-dpi-label], [data-preflight-fade-label], [data-preflight-thin-label]"
  );
  const metaNode = node.querySelector(
    "[data-preflight-dpi-meta], [data-preflight-fade-meta], [data-preflight-thin-meta]"
  );
  if (labelNode) labelNode.textContent = label;
  if (metaNode) metaNode.textContent = meta || "";
  if (meta) {
    node.setAttribute("title", meta);
  } else {
    node.removeAttribute("title");
  }
}

function clearPreflightOverlays(root) {
  root?.querySelectorAll("[data-preflight-thin-overlay], [data-preflight-fade-overlay]").forEach((node) => {
    node.remove();
  });
  const chrome = root?.querySelector("[data-preflight-overlay-chrome]");
  if (chrome instanceof HTMLElement) {
    chrome.hidden = true;
    chrome.querySelectorAll("[data-preflight-thin-toggle], [data-preflight-fade-toggle]").forEach((button) => {
      if (button instanceof HTMLButtonElement) {
        button.hidden = true;
        button.classList.add("is-active");
        button.setAttribute("aria-pressed", "true");
      }
    });
  }
}

function clearPreflightQuality(root) {
  const panel = root?.querySelector("[data-configurator-preflight]");
  if (!(panel instanceof HTMLElement)) {
    return;
  }
  panel.hidden = true;
  setQualityStripState(
    panel.querySelector("[data-preflight-dpi]"),
    "pending",
    "Résolution",
    ""
  );
  setQualityStripState(
    panel.querySelector("[data-preflight-fade]"),
    "pending",
    "Dégradés",
    ""
  );
  setQualityStripState(
    panel.querySelector("[data-preflight-thin]"),
    "pending",
    "Finesse",
    ""
  );
  clearPreflightOverlays(root);
}

function resolveDpiLevel(dpi, { recommended, minimum }) {
  if (!(dpi > 0)) {
    return {
      level: "warning",
      label: "Résolution à vérifier",
      meta: "DPI indisponible avant l’analyse technique.",
    };
  }
  if (dpi >= recommended) {
    return {
      level: "good",
      label: "Résolution OK",
      meta: `${Math.round(dpi)} DPI · objectif ${recommended} DPI atteint.`,
    };
  }
  if (dpi >= minimum) {
    return {
      level: "warning",
      label: "Résolution acceptable",
      meta: `${Math.round(dpi)} DPI · objectif ${recommended} DPI.`,
    };
  }
  return {
    level: "error",
    label: "Résolution insuffisante",
    meta: `${Math.round(dpi)} DPI · pixellisation probable sous ${minimum} DPI.`,
  };
}

function detectSemiTransparencyFromMedia(media) {
  const sourceWidth =
    media instanceof HTMLImageElement
      ? media.naturalWidth
      : media instanceof HTMLCanvasElement
        ? media.width
        : 0;
  const sourceHeight =
    media instanceof HTMLImageElement
      ? media.naturalHeight
      : media instanceof HTMLCanvasElement
        ? media.height
        : 0;
  if (!sourceWidth || !sourceHeight) {
    return { detected: false, skipped: true };
  }

  const maxSide = 480;
  const scale = Math.min(1, maxSide / Math.max(sourceWidth, sourceHeight));
  const width = Math.max(1, Math.round(sourceWidth * scale));
  const height = Math.max(1, Math.round(sourceHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true, alpha: true });
  if (!context) {
    return { detected: false, skipped: true };
  }
  context.clearRect(0, 0, width, height);
  context.drawImage(media, 0, 0, width, height);
  let data;
  try {
    data = context.getImageData(0, 0, width, height).data;
  } catch (_error) {
    return { detected: false, skipped: true };
  }

  const minAlpha = 16;
  const maxAlpha = 250;
  const minPixels = 48;
  const minCoveragePercent = 0.02;
  let softPixels = 0;
  let opaqueOrSoft = 0;
  const softMask = new Uint8Array(width * height);
  for (let index = 3, pixel = 0; index < data.length; index += 4, pixel += 1) {
    const alpha = data[index];
    if (alpha <= 0) continue;
    opaqueOrSoft += 1;
    if (alpha >= minAlpha && alpha <= maxAlpha) {
      softPixels += 1;
      softMask[pixel] = 1;
    }
  }
  const coverage = opaqueOrSoft > 0 ? (softPixels / opaqueOrSoft) * 100 : 0;
  return {
    detected: softPixels >= minPixels && coverage >= minCoveragePercent,
    coveragePercent: Number(coverage.toFixed(2)),
    pixelCount: softPixels,
    skipped: false,
    width,
    height,
    mask: softMask,
  };
}

function morphOpenBinaryMask(mask, width, height, radius) {
  if (radius < 1) {
    return mask;
  }
  const erode = new Uint8Array(mask.length);
  const opened = new Uint8Array(mask.length);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let keep = 1;
      for (let dy = -radius; dy <= radius && keep; dy += 1) {
        const yy = y + dy;
        if (yy < 0 || yy >= height) {
          keep = 0;
          break;
        }
        for (let dx = -radius; dx <= radius; dx += 1) {
          const xx = x + dx;
          if (xx < 0 || xx >= width || !mask[yy * width + xx]) {
            keep = 0;
            break;
          }
        }
      }
      erode[y * width + x] = keep;
    }
  }
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let hit = 0;
      for (let dy = -radius; dy <= radius && !hit; dy += 1) {
        const yy = y + dy;
        if (yy < 0 || yy >= height) continue;
        for (let dx = -radius; dx <= radius; dx += 1) {
          const xx = x + dx;
          if (xx < 0 || xx >= width) continue;
          if (erode[yy * width + xx]) {
            hit = 1;
            break;
          }
        }
      }
      opened[y * width + x] = hit;
    }
  }
  return opened;
}

function detectThinZonesFromMedia(media, dpi = 300) {
  const sourceWidth =
    media instanceof HTMLImageElement
      ? media.naturalWidth
      : media instanceof HTMLCanvasElement
        ? media.width
        : 0;
  const sourceHeight =
    media instanceof HTMLImageElement
      ? media.naturalHeight
      : media instanceof HTMLCanvasElement
        ? media.height
        : 0;
  if (!sourceWidth || !sourceHeight) {
    return { detected: false, skipped: true };
  }

  const maxSide = 480;
  const scale = Math.min(1, maxSide / Math.max(sourceWidth, sourceHeight));
  const width = Math.max(1, Math.round(sourceWidth * scale));
  const height = Math.max(1, Math.round(sourceHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true, alpha: true });
  if (!context) {
    return { detected: false, skipped: true };
  }
  context.clearRect(0, 0, width, height);
  context.drawImage(media, 0, 0, width, height);
  let data;
  try {
    data = context.getImageData(0, 0, width, height).data;
  } catch (_error) {
    return { detected: false, skipped: true };
  }

  const alphaThreshold = 32;
  const foreground = new Uint8Array(width * height);
  let foregroundPixels = 0;
  for (let index = 3, pixel = 0; index < data.length; index += 4, pixel += 1) {
    if (data[index] >= alphaThreshold) {
      foreground[pixel] = 1;
      foregroundPixels += 1;
    }
  }
  if (!foregroundPixels) {
    return { detected: false, skipped: false, width, height, mask: foreground, pixelCount: 0 };
  }

  const safeDpi = dpi > 0 ? dpi : 300;
  const pixelsPerMm = (safeDpi / 25.4) * scale;
  const thresholdPixels = pixelsPerMm * 0.5;
  if (thresholdPixels < 1) {
    return {
      detected: false,
      skipped: false,
      resolutionLimited: true,
      width,
      height,
      mask: new Uint8Array(width * height),
      pixelCount: 0,
    };
  }

  const radius = Math.max(1, Math.min(8, Math.round((thresholdPixels - 1) / 2)));
  const opened = morphOpenBinaryMask(foreground, width, height, radius);
  const thinMask = new Uint8Array(width * height);
  let thinPixels = 0;
  for (let index = 0; index < foreground.length; index += 1) {
    if (foreground[index] && !opened[index]) {
      thinMask[index] = 1;
      thinPixels += 1;
    }
  }
  const coverage = foregroundPixels > 0 ? (thinPixels / foregroundPixels) * 100 : 0;
  return {
    detected: thinPixels >= 16 && coverage >= 0.05,
    coveragePercent: Number(coverage.toFixed(2)),
    pixelCount: thinPixels,
    skipped: false,
    width,
    height,
    mask: thinMask,
  };
}

function paintMaskOverlay(mask, width, height, rgba) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    return null;
  }
  const image = context.createImageData(width, height);
  const [red, green, blue, alpha] = rgba;
  for (let pixel = 0; pixel < mask.length; pixel += 1) {
    if (!mask[pixel]) continue;
    const index = pixel * 4;
    image.data[index] = red;
    image.data[index + 1] = green;
    image.data[index + 2] = blue;
    image.data[index + 3] = alpha;
  }
  context.putImageData(image, 0, 0);
  return canvas;
}

function ensurePreflightOverlayChrome(root) {
  let chrome = root.querySelector("[data-preflight-overlay-chrome]");
  if (chrome instanceof HTMLElement) {
    return chrome;
  }
  const previewColumn = root.querySelector(".b2b-configurator__preview");
  if (!(previewColumn instanceof HTMLElement)) {
    return null;
  }
  chrome = document.createElement("div");
  chrome.className = "b2b-preview-chrome b2b-preflight-overlay-chrome";
  chrome.dataset.preflightOverlayChrome = "";
  chrome.hidden = true;

  const overlays = document.createElement("div");
  overlays.className = "b2b-quality-overlays";
  overlays.setAttribute("role", "group");
  overlays.setAttribute("aria-label", "Mise en évidence prévol");

  const actions = document.createElement("div");
  actions.className = "b2b-quality-overlays__actions";

  const thinToggle = document.createElement("button");
  thinToggle.type = "button";
  thinToggle.className = "ui-btn ui-btn-secondary ui-btn-sm is-active";
  thinToggle.setAttribute("aria-pressed", "true");
  thinToggle.dataset.preflightThinToggle = "";
  thinToggle.hidden = true;
  const thinSwatch = document.createElement("span");
  thinSwatch.className = "b2b-thin-zone-swatch";
  thinSwatch.setAttribute("aria-hidden", "true");
  const thinLabel = document.createElement("span");
  thinLabel.dataset.preflightThinToggleLabel = "";
  thinLabel.textContent = "Zones < 0,5 mm";
  thinToggle.append(thinSwatch, thinLabel);

  const fadeToggle = document.createElement("button");
  fadeToggle.type = "button";
  fadeToggle.className = "ui-btn ui-btn-secondary ui-btn-sm is-active";
  fadeToggle.setAttribute("aria-pressed", "true");
  fadeToggle.dataset.preflightFadeToggle = "";
  fadeToggle.hidden = true;
  const fadeSwatch = document.createElement("span");
  fadeSwatch.className = "b2b-semi-transparency-swatch";
  fadeSwatch.setAttribute("aria-hidden", "true");
  const fadeLabel = document.createElement("span");
  fadeLabel.dataset.preflightFadeToggleLabel = "";
  fadeLabel.textContent = "Dégradés";
  fadeToggle.append(fadeSwatch, fadeLabel);

  actions.append(thinToggle, fadeToggle);
  overlays.append(actions);
  chrome.append(overlays);

  const backgroundTools = previewColumn.querySelector(".b2b-background-tools");
  if (backgroundTools) {
    previewColumn.insertBefore(chrome, backgroundTools);
  } else {
    previewColumn.appendChild(chrome);
  }
  return chrome;
}

function syncPreflightOverlays(root, { thin = null, fade = null } = {}) {
  clearPreflightOverlays(root);
  const bounds =
    root.querySelector("[data-configurator-bounds]:not([hidden])") ||
    root.querySelector("[data-configurator-bounds][data-configurator-bounds-visible]") ||
    root.querySelector("[data-configurator-bounds]");
  if (!(bounds instanceof HTMLElement)) {
    return;
  }
  const chrome = ensurePreflightOverlayChrome(root);
  const thinDetected = Boolean(thin?.detected && thin.mask);
  const fadeDetected = Boolean(fade?.detected && fade.mask);
  if (!thinDetected && !fadeDetected) {
    if (chrome instanceof HTMLElement) chrome.hidden = true;
    return;
  }

  if (thinDetected) {
    const overlay = paintMaskOverlay(thin.mask, thin.width, thin.height, [239, 44, 72, 170]);
    if (overlay) {
      overlay.className = "b2b-thin-zone-overlay";
      overlay.dataset.preflightThinOverlay = "";
      overlay.setAttribute("aria-hidden", "true");
      bounds.appendChild(overlay);
    }
  }
  if (fadeDetected) {
    const overlay = paintMaskOverlay(fade.mask, fade.width, fade.height, [255, 152, 0, 150]);
    if (overlay) {
      overlay.className = "b2b-semi-transparency-overlay";
      overlay.dataset.preflightFadeOverlay = "";
      overlay.setAttribute("aria-hidden", "true");
      bounds.appendChild(overlay);
    }
  }

  if (!(chrome instanceof HTMLElement)) {
    return;
  }
  chrome.hidden = false;
  const thinToggle = chrome.querySelector("[data-preflight-thin-toggle]");
  const fadeToggle = chrome.querySelector("[data-preflight-fade-toggle]");
  if (thinToggle instanceof HTMLButtonElement) {
    thinToggle.hidden = !thinDetected;
    thinToggle.classList.toggle("is-active", thinDetected);
    thinToggle.setAttribute("aria-pressed", thinDetected ? "true" : "false");
  }
  if (fadeToggle instanceof HTMLButtonElement) {
    fadeToggle.hidden = !fadeDetected;
    fadeToggle.classList.toggle("is-active", fadeDetected);
    fadeToggle.setAttribute("aria-pressed", fadeDetected ? "true" : "false");
  }
}

function updatePreflightQuality(root, { dpi = null, estimated = false, media = null, documentKind = "raster" } = {}) {
  const panel = root?.querySelector("[data-configurator-preflight]");
  if (!(panel instanceof HTMLElement)) {
    return;
  }
  panel.hidden = false;
  const thresholds = dpiThresholds(root);
  const dpiStrip = panel.querySelector("[data-preflight-dpi]");
  const fadeStrip = panel.querySelector("[data-preflight-fade]");
  const thinStrip = panel.querySelector("[data-preflight-thin]");

  if (documentKind === "pdf") {
    setQualityStripState(
      dpiStrip,
      "pending",
      "Résolution à confirmer",
      "Document PDF · contrôle DPI complet après analyse."
    );
    setQualityStripState(
      fadeStrip,
      "pending",
      "Dégradés à confirmer",
      "Le contrôle des semi-transparences se fait après l’import."
    );
    setQualityStripState(
      thinStrip,
      "pending",
      "Finesse à confirmer",
      "Zones < 0,5 mm contrôlées après l’analyse technique."
    );
    clearPreflightOverlays(root);
    return;
  }

  if (documentKind === "deferred") {
    setQualityStripState(
      dpiStrip,
      "pending",
      "Résolution à confirmer",
      "Aperçu limité · analyse technique après import."
    );
    setQualityStripState(
      fadeStrip,
      "pending",
      "Dégradés à confirmer",
      "Contrôle des semi-transparences après import."
    );
    setQualityStripState(
      thinStrip,
      "pending",
      "Finesse à confirmer",
      "Zones < 0,5 mm après analyse technique."
    );
    clearPreflightOverlays(root);
    return;
  }

  const dpiState = resolveDpiLevel(dpi, thresholds);
  if (estimated && dpiState.meta) {
    dpiState.meta = `${dpiState.meta} Estimation locale.`;
  }
  setQualityStripState(dpiStrip, dpiState.level, dpiState.label, dpiState.meta);

  if (!(media instanceof HTMLImageElement || media instanceof HTMLCanvasElement)) {
    setQualityStripState(
      fadeStrip,
      "pending",
      "Dégradés à confirmer",
      "Aperçu indisponible pour le contrôle local."
    );
    setQualityStripState(
      thinStrip,
      "pending",
      "Finesse à confirmer",
      "Aperçu indisponible pour le contrôle local."
    );
    clearPreflightOverlays(root);
    return;
  }

  const fade = detectSemiTransparencyFromMedia(media);
  if (fade.skipped) {
    setQualityStripState(
      fadeStrip,
      "pending",
      "Dégradés à confirmer",
      "Contrôle local indisponible · analyse serveur à l’import."
    );
  } else if (fade.detected) {
    setQualityStripState(
      fadeStrip,
      "warning",
      "Dégradés détectés",
      "Semi-transparences probables (ombres, anti-alias, dégradés)."
    );
  } else {
    setQualityStripState(
      fadeStrip,
      "good",
      "Pas de dégradé",
      "Aucune semi-transparence significative détectée en local."
    );
  }

  const thin = detectThinZonesFromMedia(media, dpi || 300);
  if (thin.skipped) {
    setQualityStripState(
      thinStrip,
      "pending",
      "Finesse à confirmer",
      "Contrôle local indisponible · analyse serveur à l’import."
    );
  } else if (thin.resolutionLimited) {
    setQualityStripState(
      thinStrip,
      "pending",
      "Finesse à confirmer",
      "Résolution d’aperçu insuffisante pour mesurer 0,5 mm."
    );
  } else if (thin.detected) {
    setQualityStripState(
      thinStrip,
      "warning",
      "Détails fins",
      "Zones probablement < 0,5 mm · à vérifier avant production."
    );
  } else {
    setQualityStripState(
      thinStrip,
      "good",
      "Finesse OK",
      "Pas de zone fine significative détectée en local."
    );
  }

  syncPreflightOverlays(root, {
    thin: thin.skipped || thin.resolutionLimited ? null : thin,
    fade: fade.skipped ? null : fade,
  });
}

function validateConfiguratorFiles(root, input) {
  const files = Array.from(input.files || []);
  const maxFiles = Number.parseInt(input.dataset.maxFiles || "0", 10);
  const maxFileBytes = Number.parseInt(input.dataset.maxFileBytes || "0", 10);
  const maxTotalBytes = Number.parseInt(input.dataset.maxTotalBytes || "0", 10);
  let message = "";

  if (maxFiles > 0 && files.length > maxFiles) {
    message = `Sélectionnez au maximum ${maxFiles} fichiers à la fois.`;
  } else if (maxTotalBytes > 0 && files.reduce((total, file) => total + file.size, 0) > maxTotalBytes) {
    message = `La sélection dépasse ${formatUploadSize(maxTotalBytes)}. Réduisez le nombre de fichiers.`;
  } else if (maxFileBytes > 0) {
    const oversizedFile = files.find((file) => file.size > maxFileBytes);
    if (oversizedFile) {
      message = `« ${oversizedFile.name} » pèse ${formatUploadSize(oversizedFile.size)}. La limite est de ${formatUploadSize(maxFileBytes)} par fichier.`;
    }
  }

  input.setCustomValidity(message);
  if (message) {
    input.setAttribute("aria-invalid", "true");
  } else {
    input.removeAttribute("aria-invalid");
  }
  const error = root.querySelector("[data-configurator-file-error]");
  if (error instanceof HTMLElement) {
    error.textContent = message;
    error.hidden = !message;
  }
  const submit = root.closest("form")?.querySelector("[data-configurator-submit]");
  if (submit instanceof HTMLButtonElement) {
    submit.disabled = Boolean(message);
  }
  return message;
}

function notifyPreviewState(root, eventName, file, media = null) {
  root.dispatchEvent(
    new CustomEvent(eventName, {
      bubbles: true,
      detail: { file, media },
    })
  );
}

/** Restrict image URL sinks to blob: / same-origin (CodeQL js/xss-through-dom). */
function assignTrustedImageSrc(image, rawUrl) {
  if (!(image instanceof HTMLImageElement) || typeof rawUrl !== "string" || !rawUrl) {
    return false;
  }
  if (rawUrl.startsWith("blob:")) {
    image.src = rawUrl;
    return true;
  }
  try {
    const parsed = new URL(rawUrl, window.location.href);
    if (parsed.protocol === "blob:") {
      image.src = parsed.href;
      return true;
    }
    if (parsed.origin === window.location.origin) {
      image.src = `${parsed.pathname}${parsed.search}${parsed.hash}`;
      return true;
    }
  } catch {
    return false;
  }
  return false;
}

function setPreviewBackground(root, value, activeControl = null) {
  const stage = root.querySelector("[data-configurator-stage]");
  if (!(stage instanceof HTMLElement)) {
    return;
  }
  const checker = value === "checker";
  const safeColor =
    typeof value === "string" && value.startsWith("#") ? normalizeHexColor(value) : null;
  stage.classList.toggle("is-checker", checker);
  if (checker || !safeColor) {
    if (checker) {
      stage.style.removeProperty("background-color");
      stage.style.setProperty("--b2b-preview-bg", "#ffffff");
    }
  } else {
    stage.style.backgroundColor = safeColor;
    stage.style.setProperty("--b2b-preview-bg", safeColor);
  }
  root.querySelectorAll("[data-configurator-bg]").forEach((button) => {
    const active = button === activeControl;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  const customControl = root.querySelector("[data-configurator-custom-bg-control]");
  const isCustomActive = !checker && activeControl === null && Boolean(safeColor);
  if (customControl instanceof HTMLElement) {
    customControl.classList.toggle("is-active", isCustomActive);
    if (safeColor) {
      syncHexColorControlSwatch(customControl, safeColor);
    }
  }
}

function findPreviewBounds(node) {
  if (!(node instanceof Element)) {
    return null;
  }
  const bounds = node.closest("[data-configurator-bounds]");
  return bounds instanceof HTMLElement ? bounds : null;
}

function setPreviewMediaVisible(media, visible) {
  if (!(media instanceof HTMLElement)) {
    return;
  }
  const bounds = findPreviewBounds(media);
  media.hidden = !visible;
  if (bounds instanceof HTMLElement) {
    bounds.hidden = !visible;
    bounds.classList.toggle("is-preview-bounds", visible);
  }
  if (visible) {
    const root = findConfiguratorRoot(media);
    if (root) {
      scheduleFitPreviewMedia(root);
    }
  }
}

function getStageInnerSize(stage) {
  const style = getComputedStyle(stage);
  const padX = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
  const padY = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
  return {
    width: Math.max(stage.clientWidth - padX, 1),
    height: Math.max(stage.clientHeight - padY, 1),
  };
}

function getPreviewMediaNaturalSize(media) {
  if (media instanceof HTMLImageElement) {
    return { width: media.naturalWidth, height: media.naturalHeight };
  }
  if (media instanceof HTMLCanvasElement) {
    const width =
      Number.parseFloat(media.dataset.previewWidth || "") || media.width;
    const height =
      Number.parseFloat(media.dataset.previewHeight || "") || media.height;
    return { width, height };
  }
  return { width: 0, height: 0 };
}

function findActivePreviewMedia(root) {
  if (!(root instanceof HTMLElement)) {
    return null;
  }
  const media = root.querySelector(
    "[data-configurator-preview]:not([hidden]), [data-configurator-document-preview]:not([hidden])"
  );
  return media instanceof HTMLElement ? media : null;
}

function findActivePreviewBounds(root) {
  const media = findActivePreviewMedia(root);
  return media instanceof HTMLElement ? findPreviewBounds(media) : null;
}

function fitPreviewMedia(root) {
  if (!(root instanceof HTMLElement)) {
    return;
  }
  const stage = root.querySelector("[data-configurator-stage]");
  const media = findActivePreviewMedia(root);
  const bounds = media instanceof HTMLElement ? findPreviewBounds(media) : null;
  if (!(stage instanceof HTMLElement) || !(bounds instanceof HTMLElement) || !(media instanceof HTMLElement)) {
    return;
  }
  const { width: availableW, height: availableH } = getStageInnerSize(stage);
  const { width: naturalW, height: naturalH } = getPreviewMediaNaturalSize(media);
  if (!naturalW || !naturalH || !availableW || !availableH) {
    return;
  }
  const scale = Math.min(availableW / naturalW, availableH / naturalH, 1);
  const displayW = Math.max(1, Math.round(naturalW * scale));
  const displayH = Math.max(1, Math.round(naturalH * scale));
  bounds.dataset.previewBaseWidth = String(displayW);
  bounds.dataset.previewBaseHeight = String(displayH);
  media.classList.add("is-preview-fitted");
  applyPreviewZoom(root, readPreviewZoom(root), { preserveCenter: false });
}

function scheduleFitPreviewMedia(root) {
  if (!(root instanceof HTMLElement)) {
    return;
  }
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      fitPreviewMedia(root);
    });
  });
}

function resetPreviewMediaSizing(root) {
  if (!(root instanceof HTMLElement)) {
    return;
  }
  root.querySelectorAll("[data-configurator-bounds]").forEach((bounds) => {
    if (!(bounds instanceof HTMLElement)) {
      return;
    }
    bounds.style.width = "";
    bounds.style.height = "";
    delete bounds.dataset.previewBaseWidth;
    delete bounds.dataset.previewBaseHeight;
  });
  root.querySelectorAll("[data-configurator-preview], [data-configurator-document-preview]").forEach((media) => {
    if (!(media instanceof HTMLElement)) {
      return;
    }
    media.style.width = "";
    media.style.height = "";
    media.classList.remove("is-preview-fitted");
  });
  delete root.dataset.previewZoom;
}

function readPreviewZoom(root) {
  const value = Number.parseFloat(root?.dataset.previewZoom || "1");
  return Number.isFinite(value)
    ? Math.min(previewZoomMax, Math.max(previewZoomMin, value))
    : previewZoomMin;
}

function applyPreviewZoom(root, requestedScale, { preserveCenter = true } = {}) {
  if (!(root instanceof HTMLElement)) {
    return;
  }
  const stage = root.querySelector("[data-configurator-stage]");
  const media = findActivePreviewMedia(root);
  const bounds = media instanceof HTMLElement ? findPreviewBounds(media) : null;
  if (
    !(stage instanceof HTMLElement)
    || !(bounds instanceof HTMLElement)
    || !(media instanceof HTMLElement)
  ) {
    return;
  }
  const baseWidth = Number.parseFloat(bounds.dataset.previewBaseWidth || "");
  const baseHeight = Number.parseFloat(bounds.dataset.previewBaseHeight || "");
  if (!baseWidth || !baseHeight) {
    return;
  }

  const scale = Math.min(previewZoomMax, Math.max(previewZoomMin, requestedScale));
  const previousScrollWidth = Math.max(stage.scrollWidth, 1);
  const previousScrollHeight = Math.max(stage.scrollHeight, 1);
  const centerRatioX = preserveCenter
    ? (stage.scrollLeft + stage.clientWidth / 2) / previousScrollWidth
    : 0.5;
  const centerRatioY = preserveCenter
    ? (stage.scrollTop + stage.clientHeight / 2) / previousScrollHeight
    : 0.5;
  const displayWidth = Math.round(baseWidth * scale);
  const displayHeight = Math.round(baseHeight * scale);

  root.dataset.previewZoom = String(scale);
  media.classList.add("is-preview-fitted");
  media.style.width = `${displayWidth}px`;
  media.style.height = `${displayHeight}px`;
  bounds.style.width = `${displayWidth}px`;
  bounds.style.height = `${displayHeight}px`;
  stage.classList.toggle("is-zoomed", scale > previewZoomMin);

  const label = root.querySelector("[data-preview-zoom-label]");
  if (label instanceof HTMLElement) {
    label.textContent = `${Math.round(scale * 100)} %`;
  }
  const zoomOut = root.querySelector("[data-preview-zoom-out]");
  const zoomIn = root.querySelector("[data-preview-zoom-in]");
  if (zoomOut instanceof HTMLButtonElement) {
    zoomOut.disabled = scale <= previewZoomMin;
  }
  if (zoomIn instanceof HTMLButtonElement) {
    zoomIn.disabled = scale >= previewZoomMax;
  }

  requestAnimationFrame(() => {
    if (scale <= previewZoomMin) {
      stage.scrollTo({ left: 0, top: 0 });
      return;
    }
    stage.scrollTo({
      left: Math.max(0, centerRatioX * stage.scrollWidth - stage.clientWidth / 2),
      top: Math.max(0, centerRatioY * stage.scrollHeight - stage.clientHeight / 2),
    });
  });
}

function bindPreviewFitObserver(root) {
  if (!(root instanceof HTMLElement)) {
    return;
  }
  const stage = root.querySelector("[data-configurator-stage]");
  if (!(stage instanceof HTMLElement)) {
    return;
  }
  const existing = previewFitObservers.get(root);
  if (existing) {
    existing.disconnect();
  }
  const observer = new ResizeObserver(() => {
    scheduleFitPreviewMedia(root);
  });
  observer.observe(stage);
  previewFitObservers.set(root, observer);
}

function readUint16BE(bytes, offset) {
  return (bytes[offset] << 8) | bytes[offset + 1];
}

function readUint32BE(bytes, offset) {
  return (
    ((bytes[offset] << 24) | (bytes[offset + 1] << 16) | (bytes[offset + 2] << 8) | bytes[offset + 3]) >>> 0
  );
}

function parsePngDpi(bytes) {
  let offset = 8;
  while (offset + 12 <= bytes.length) {
    const length = readUint32BE(bytes, offset);
    const type = String.fromCharCode(
      bytes[offset + 4],
      bytes[offset + 5],
      bytes[offset + 6],
      bytes[offset + 7]
    );
    if (type === "pHYs" && length >= 9) {
      const unit = bytes[offset + 16];
      const x = readUint32BE(bytes, offset + 8);
      if (unit === 1 && x > 0) {
        return Math.round(x / 39.3701);
      }
    }
    offset += 12 + length;
  }
  return null;
}

function parseJpegDpi(bytes) {
  let offset = 2;
  while (offset + 4 < bytes.length) {
    if (bytes[offset] !== 0xff) {
      offset += 1;
      continue;
    }
    const marker = bytes[offset + 1];
    if (marker === 0xd8) {
      offset += 2;
      continue;
    }
    if (marker === 0xd9 || marker === 0xda) {
      break;
    }
    const segmentLength = readUint16BE(bytes, offset + 2);
    if (segmentLength < 2 || offset + 2 + segmentLength > bytes.length) {
      break;
    }
    if (marker === 0xe0 && segmentLength >= 14) {
      const identifier = String.fromCharCode(
        bytes[offset + 4],
        bytes[offset + 5],
        bytes[offset + 6],
        bytes[offset + 7],
        bytes[offset + 8]
      );
      if (identifier === "JFIF\x00") {
        const units = bytes[offset + 11];
        const xDensity = readUint16BE(bytes, offset + 12);
        if (units === 1 && xDensity > 0) {
          return xDensity;
        }
        if (units === 2 && xDensity > 0) {
          return Math.round(xDensity * 2.54);
        }
      }
    }
    offset += 2 + segmentLength;
  }
  return null;
}

async function readEmbeddedDpiFromFile(file) {
  if (!(file instanceof Blob)) {
    return null;
  }
  try {
    const header = new Uint8Array(await file.slice(0, 512 * 1024).arrayBuffer());
    if (header.length >= 8 && header[0] === 0x89 && header[1] === 0x50) {
      return parsePngDpi(header);
    }
    if (header.length >= 4 && header[0] === 0xff && header[1] === 0xd8) {
      return parseJpegDpi(header);
    }
  } catch (_error) {
    return null;
  }
  return null;
}

async function isPdfCompatibleIllustrator(file) {
  if (!(file instanceof File) || !file.name.toLowerCase().endsWith(".ai")) {
    return false;
  }
  try {
    const signature = new Uint8Array(await file.slice(0, 5).arrayBuffer());
    return (
      signature.length === 5
      && signature[0] === 0x25
      && signature[1] === 0x50
      && signature[2] === 0x44
      && signature[3] === 0x46
      && signature[4] === 0x2d
    );
  } catch (_error) {
    return false;
  }
}

function markPreviewBounds(node, visible = true) {
  setPreviewMediaVisible(node, visible);
}

function syncPreviewBounds(root) {
  if (!(root instanceof HTMLElement)) {
    return;
  }
  root.querySelectorAll("[data-configurator-bounds]").forEach((bounds) => {
    if (!(bounds instanceof HTMLElement)) {
      return;
    }
    const media = bounds.querySelector("[data-configurator-preview], [data-configurator-document-preview]");
    const visible =
      (media instanceof HTMLElement && !media.hidden)
      || bounds.hasAttribute("data-configurator-bounds-visible");
    bounds.hidden = !visible;
    bounds.classList.toggle("is-preview-bounds", visible);
    if (media instanceof HTMLElement && bounds.hasAttribute("data-configurator-bounds-visible")) {
      media.hidden = false;
    }
  });
}

function updateSuggestedSize(root, image, { dpi = 300, detail = null } = {}) {
  const widthInput = root.querySelector("[data-configurator-width]");
  const heightInput = root.querySelector("[data-configurator-height]");
  const pixels = root.querySelector("[data-configurator-pixels]");
  const widthMm = (image.naturalWidth * 25.4) / dpi;
  const heightMm = (image.naturalHeight * 25.4) / dpi;
  if (widthInput instanceof HTMLInputElement && !widthInput.dataset.userEdited) {
    widthInput.value = widthMm.toFixed(2);
  }
  if (heightInput instanceof HTMLInputElement && !heightInput.dataset.userEdited) {
    heightInput.value = heightMm.toFixed(2);
  }
  if (pixels instanceof HTMLElement) {
    pixels.textContent =
      detail ||
      `${image.naturalWidth} × ${image.naturalHeight} px · ${widthMm.toFixed(2)} × ${heightMm.toFixed(2)} mm à ${dpi} DPI`;
  }
}

function updateSuggestedSizeFromPoints(root, widthPt, heightPt, detail) {
  const widthInput = root.querySelector("[data-configurator-width]");
  const heightInput = root.querySelector("[data-configurator-height]");
  const pixels = root.querySelector("[data-configurator-pixels]");
  const widthMm = (widthPt / 72) * 25.4;
  const heightMm = (heightPt / 72) * 25.4;
  if (widthInput instanceof HTMLInputElement && !widthInput.dataset.userEdited) {
    widthInput.value = widthMm.toFixed(2);
  }
  if (heightInput instanceof HTMLInputElement && !heightInput.dataset.userEdited) {
    heightInput.value = heightMm.toFixed(2);
  }
  if (pixels instanceof HTMLElement) {
    pixels.textContent = detail;
  }
}

async function renderPdfPreview(root, file, canvas, placeholder, renderToken) {
  let pdfDocument = null;
  let loadingTask = null;
  try {
    const pdfJs = await loadPdfJs();
    const fileBuffer = await file.arrayBuffer();
    if (previewRenderTokens.get(root) !== renderToken) {
      return;
    }
    loadingTask = pdfJs.getDocument({
      data: new Uint8Array(fileBuffer),
      enableScripting: false,
    });
    pdfDocument = await loadingTask.promise;
    const page = await pdfDocument.getPage(1);
    const baseViewport = page.getViewport({ scale: 1 });
    const maxRenderSide = 1600;
    const scale = Math.min(
      2,
      maxRenderSide / Math.max(baseViewport.width, baseViewport.height, 1)
    );
    const viewport = page.getViewport({ scale });
    const outputScale = Math.min(window.devicePixelRatio || 1, 2);
    const context = canvas.getContext("2d", { alpha: true });
    if (context === null) {
      throw new Error("Canvas 2D indisponible");
    }
    canvas.width = Math.floor(viewport.width * outputScale);
    canvas.height = Math.floor(viewport.height * outputScale);
    canvas.dataset.previewWidth = String(baseViewport.width);
    canvas.dataset.previewHeight = String(baseViewport.height);
    canvas.style.removeProperty("width");
    canvas.style.removeProperty("height");
    context.clearRect(0, 0, canvas.width, canvas.height);
    await page.render({
      canvasContext: context,
      viewport,
      transform: outputScale === 1 ? null : [outputScale, 0, 0, outputScale, 0, 0],
      background: "rgba(0, 0, 0, 0)",
    }).promise;
    if (previewRenderTokens.get(root) !== renderToken) {
      return;
    }
    canvas.hidden = false;
    setPreviewMediaVisible(canvas, true);
    if (placeholder instanceof HTMLElement) {
      placeholder.hidden = true;
    }
    updateSuggestedSizeFromPoints(
      root,
      baseViewport.width,
      baseViewport.height,
      `${Math.round(baseViewport.width)} × ${Math.round(baseViewport.height)} pt · ${((baseViewport.width / 72) * 25.4).toFixed(2)} × ${((baseViewport.height / 72) * 25.4).toFixed(2)} mm artboard · analyse complète à l’envoi`
    );
    updatePreflightQuality(root, { documentKind: "pdf", media: canvas });
    revealConfiguratorParams(root);
    scheduleFitPreviewMedia(root);
    notifyPreviewState(root, "b2b:preview-ready", file, canvas);
  } catch (_error) {
    if (previewRenderTokens.get(root) !== renderToken) {
      return;
    }
    canvas.hidden = true;
    setPlaceholder(
      placeholder,
      "Aperçu PDF indisponible",
      "Le fichier pourra tout de même être analysé après son ajout."
    );
    updatePreflightQuality(root, { documentKind: "deferred" });
    notifyPreviewState(root, "b2b:preview-unavailable", file);
  } finally {
    const destroyTarget =
      typeof pdfDocument?.destroy === "function"
        ? pdfDocument
        : typeof loadingTask?.destroy === "function"
          ? loadingTask
          : null;
    if (destroyTarget !== null) {
      try {
        await destroyTarget.destroy();
      } catch (_cleanupError) {
        // Preview cleanup must never replace the result with a console error.
      }
    }
  }
}

async function previewSelectedFile(root, file) {
  root.dataset.previewZoom = String(previewZoomMin);
  const preview = root.querySelector("[data-configurator-preview]");
  const documentPreview = root.querySelector("[data-configurator-document-preview]");
  const placeholder = root.querySelector("[data-configurator-placeholder]");
  const nameInput = root.querySelector("[data-configurator-name]");
  const pixels = root.querySelector("[data-configurator-pixels]");
  const renderToken = Symbol("preview-render");
  previewRenderTokens.set(root, renderToken);
  if (nameInput instanceof HTMLInputElement && !nameInput.value.trim()) {
    nameInput.value = file.name.replace(/\.[^.]+$/, "");
  }
  if (preview instanceof HTMLImageElement) {
    preview.hidden = true;
    preview.removeAttribute("src");
    preview.style.removeProperty("width");
    preview.style.removeProperty("height");
    preview.classList.remove("is-preview-fitted");
    setPreviewMediaVisible(preview, false);
  }
  if (documentPreview instanceof HTMLCanvasElement) {
    documentPreview.hidden = true;
    const context = documentPreview.getContext("2d", { alpha: true });
    context?.clearRect(0, 0, documentPreview.width, documentPreview.height);
    documentPreview.width = 0;
    documentPreview.height = 0;
    documentPreview.removeAttribute("data-preview-width");
    documentPreview.removeAttribute("data-preview-height");
    documentPreview.style.removeProperty("width");
    documentPreview.style.removeProperty("height");
    setPreviewMediaVisible(documentPreview, false);
  }
  root.querySelectorAll("[data-configurator-bounds]").forEach((bounds) => {
    if (bounds instanceof HTMLElement) {
      bounds.style.removeProperty("width");
      bounds.style.removeProperty("height");
    }
  });

  const previousUrl = previewObjectUrls.get(root);
  if (previousUrl) {
    URL.revokeObjectURL(previousUrl);
    previewObjectUrls.delete(root);
  }

  const normalizedName = file.name.toLowerCase();
  const isBrowserImage = browserPreviewMimeTypes.has(file.type);
  const declaredPdf = file.type === "application/pdf" || normalizedName.endsWith(".pdf");
  if (!declaredPdf && normalizedName.endsWith(".ai")) {
    setPlaceholder(placeholder, "Lecture de l’aperçu Illustrator…", file.name);
  }
  const isPdf = declaredPdf || await isPdfCompatibleIllustrator(file);
  if (previewRenderTokens.get(root) !== renderToken) {
    return;
  }
  if (!isBrowserImage && !isPdf) {
    const isIllustrator = normalizedName.endsWith(".ai");
    setPlaceholder(
      placeholder,
      isIllustrator ? "Aperçu généré après l’import" : "Aperçu en préparation",
      isIllustrator
        ? "Ce fichier Illustrator natif sera rasterisé par le serveur sécurisé."
        : file.name
    );
    if (pixels instanceof HTMLElement) {
      pixels.textContent = isIllustrator
        ? "Le fichier original restera inchangé pendant la génération de l’aperçu."
        : "Le fichier sera analysé en arrière-plan dès son ajout.";
    }
    updatePreflightQuality(root, { documentKind: "deferred" });
    revealConfiguratorParams(root);
    notifyPreviewState(root, "b2b:preview-unavailable", file);
    return;
  }

  setPlaceholder(placeholder, "Chargement de l’aperçu…", file.name);

  if (isPdf && documentPreview instanceof HTMLCanvasElement) {
    renderPdfPreview(root, file, documentPreview, placeholder, renderToken);
    return;
  }

  if (!(preview instanceof HTMLImageElement)) {
    return;
  }
  const objectUrl = URL.createObjectURL(file);
  previewObjectUrls.set(root, objectUrl);
  preview.onload = async () => {
    if (previewRenderTokens.get(root) !== renderToken) {
      return;
    }
    setPreviewMediaVisible(preview, true);
    if (placeholder instanceof HTMLElement) {
      placeholder.hidden = true;
    }
    const embeddedDpi = await readEmbeddedDpiFromFile(file);
    const dpi = embeddedDpi || 300;
    updateSuggestedSize(
      root,
      preview,
      {
        dpi,
        detail: `${preview.naturalWidth} × ${preview.naturalHeight} px · ${((preview.naturalWidth * 25.4) / dpi).toFixed(2)} × ${((preview.naturalHeight * 25.4) / dpi).toFixed(2)} mm à ${dpi} DPI${embeddedDpi ? "" : " (estimation)"}`,
      }
    );
    updatePreflightQuality(root, {
      dpi,
      estimated: !embeddedDpi,
      media: preview,
      documentKind: "raster",
    });
    revealConfiguratorParams(root);
    scheduleFitPreviewMedia(root);
    notifyPreviewState(root, "b2b:preview-ready", file, preview);
  };
  preview.onerror = () => {
    if (previewRenderTokens.get(root) !== renderToken) {
      return;
    }
    setPreviewMediaVisible(preview, false);
    setPlaceholder(placeholder, "Aperçu indisponible", file.name);
    notifyPreviewState(root, "b2b:preview-unavailable", file);
  };
  assignTrustedImageSrc(preview, objectUrl);
}

function bindDimensionInputs(root) {
  root.querySelectorAll("[data-configurator-width], [data-configurator-height]").forEach((input) => {
    if (!(input instanceof HTMLInputElement) || input.dataset.configuratorBound === "true") {
      return;
    }
    input.dataset.configuratorBound = "true";
    input.addEventListener("input", () => {
      input.dataset.userEdited = "true";
    });
  });
}

function initExistingPreview(root) {
  const preview = root.querySelector("[data-configurator-preview]");
  if (!(preview instanceof HTMLImageElement) || !preview.getAttribute("src")) {
    return;
  }
  if (preview.complete && preview.naturalWidth > 0) {
    setPreviewMediaVisible(preview, true);
    const placeholder = root.querySelector("[data-configurator-placeholder]");
    if (placeholder instanceof HTMLElement) {
      placeholder.hidden = true;
    }
    scheduleFitPreviewMedia(root);
    return;
  }
  preview.addEventListener(
    "load",
    () => {
      setPreviewMediaVisible(preview, true);
      const placeholder = root.querySelector("[data-configurator-placeholder]");
      if (placeholder instanceof HTMLElement) {
        placeholder.hidden = true;
      }
      scheduleFitPreviewMedia(root);
    },
    { once: true }
  );
}

function normalizeHexColor(raw) {
  const cleaned = String(raw || "").trim().replace(/^#?/, "").slice(0, 6);
  if (!/^[0-9a-fA-F]{6}$/.test(cleaned)) {
    return null;
  }
  return `#${cleaned.toLowerCase()}`;
}

function getHexPopoverMountTarget(control) {
  const dialog = control.closest("dialog");
  if (dialog instanceof HTMLElement) {
    return dialog;
  }
  return document.body;
}

function syncHexColorControlSwatch(control, rawValue) {
  const normalized = normalizeHexColor(rawValue);
  if (!(control instanceof HTMLElement) || !normalized) {
    return null;
  }
  control.style.setProperty("--swatch-color", normalized);
  const trigger = control.querySelector("[data-hex-color-trigger]");
  if (trigger instanceof HTMLElement) {
    trigger.style.setProperty("--swatch-color", normalized);
  }
  const popover =
    control._hexPopoverEl instanceof HTMLElement
      ? control._hexPopoverEl
      : control.querySelector("[data-hex-color-popover]");
  const popoverInput =
    control._hexPopoverInput instanceof HTMLInputElement
      ? control._hexPopoverInput
      : control.querySelector("[data-hex-color-popover-input]");
  if (popoverInput instanceof HTMLInputElement) {
    popoverInput.value = normalized.toUpperCase();
  }
  const nativePicker =
    control._hexNativePicker instanceof HTMLInputElement
      ? control._hexNativePicker
      : control.querySelector("[data-hex-color-native]");
  if (nativePicker instanceof HTMLInputElement) {
    nativePicker.value = normalized;
  }
  const live =
    (popover instanceof HTMLElement && popover.querySelector("[data-hex-color-live]")) ||
    control.querySelector("[data-hex-color-live]");
  if (live instanceof HTMLElement) {
    live.style.setProperty("--swatch-color", normalized);
  }
  const presetRoot = popover instanceof HTMLElement ? popover : control;
  presetRoot.querySelectorAll("[data-hex-color-preset]").forEach((btn) => {
    if (!(btn instanceof HTMLButtonElement)) {
      return;
    }
    const active = normalizeHexColor(btn.dataset.hexColorPreset) === normalized;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-pressed", String(active));
  });
  return normalized;
}

function mountHexPopover(control, popover) {
  if (popover.dataset.portaled === "true") {
    return;
  }
  const anchor = document.createComment("hex-popover-anchor");
  control._hexPopoverAnchor = anchor;
  control._hexPopoverMount = getHexPopoverMountTarget(control);
  popover.before(anchor);
  control._hexPopoverMount.appendChild(popover);
  popover.dataset.portaled = "true";
}

function unmountHexPopover(control, popover) {
  if (popover.dataset.portaled !== "true" || !(control._hexPopoverAnchor instanceof Comment)) {
    return;
  }
  control._hexPopoverAnchor.after(popover);
  control._hexPopoverAnchor.remove();
  delete control._hexPopoverAnchor;
  delete control._hexPopoverMount;
  delete popover.dataset.portaled;
}

function setMulticolorMode(fieldset, enabled) {
  const rainbowButton = fieldset.querySelector("[data-support-color-multicolor]");
  const hexControl = fieldset.querySelector("[data-hex-color-control]");
  const hexInput = fieldset.querySelector("[data-support-color-hex]");
  const hidden = fieldset.querySelector("[data-support-color-multicolor-input]");
  if (rainbowButton instanceof HTMLButtonElement) {
    rainbowButton.classList.toggle("is-active", enabled);
    rainbowButton.setAttribute("aria-pressed", enabled ? "true" : "false");
  }
  if (hidden instanceof HTMLInputElement) {
    hidden.value = enabled ? "on" : "";
  }
  if (hexControl instanceof HTMLElement) {
    hexControl.classList.toggle("is-active", false);
    const trigger = hexControl.querySelector("[data-hex-color-trigger]");
    if (trigger instanceof HTMLButtonElement) {
      trigger.disabled = enabled;
    }
  }
  if (hexInput instanceof HTMLInputElement) {
    hexInput.readOnly = enabled;
    if (enabled) {
      hexInput.value = "";
      // Multicouleur : le hex vide ne doit pas bloquer la soumission HTML5.
      hexInput.removeAttribute("required");
      hexInput.removeAttribute("aria-required");
      hexInput.setCustomValidity("");
    } else if (fieldset.hasAttribute("data-support-color-required")) {
      hexInput.setAttribute("required", "true");
      hexInput.setAttribute("aria-required", "true");
    }
  }
  updateSupportColorStatus(fieldset);
}

function updateSupportColorStatus(fieldset) {
  const hidden = fieldset.querySelector("[data-support-color-multicolor-input]");
  const hexControl = fieldset.querySelector("[data-hex-color-control]");
  const hexInput = fieldset.querySelector("[data-support-color-hex]");
  const status = fieldset.querySelector("[data-support-color-status]");
  const isMulticolor = hidden instanceof HTMLInputElement && hidden.value === "on";
  const normalized =
    hexInput instanceof HTMLInputElement ? normalizeHexColor(hexInput.value) : null;
  if (hexControl instanceof HTMLElement) {
    hexControl.classList.toggle("is-active", !isMulticolor && Boolean(normalized));
    hexControl.classList.toggle("is-empty", !normalized);
  }
  if (status instanceof HTMLElement) {
    status.textContent = isMulticolor
      ? "Multicouleur sélectionné"
      : normalized
        ? `Couleur ${normalized.toUpperCase()} sélectionnée`
        : "Aucune couleur n’est présélectionnée";
  }
}

function applySupportColorPickerValue(fieldset, rawValue) {
  const hexControl = fieldset.querySelector("[data-hex-color-control]");
  const hexInput = fieldset.querySelector("[data-support-color-hex]");
  const normalized = normalizeHexColor(rawValue);
  if (!normalized) {
    return;
  }
  if (hexControl instanceof HTMLElement) {
    syncHexColorControlSwatch(hexControl, normalized);
  }
  if (hexInput instanceof HTMLInputElement) {
    hexInput.value = normalized.toUpperCase();
  }
  setMulticolorMode(fieldset, false);
  updateSupportColorStatus(fieldset);
}

function syncSupportColorFromHex(fieldset) {
  const hexInput = fieldset.querySelector("[data-support-color-hex]");
  if (!(hexInput instanceof HTMLInputElement)) {
    return;
  }
  let display = hexInput.value.trim().toUpperCase();
  if (display && !display.startsWith("#")) {
    display = `#${display}`;
  }
  hexInput.value = display;
  const normalized = normalizeHexColor(display);
  if (normalized) {
    applySupportColorPickerValue(fieldset, normalized);
  } else {
    const hidden = fieldset.querySelector("[data-support-color-multicolor-input]");
    if (hidden instanceof HTMLInputElement) {
      hidden.value = "";
    }
    hexInput.readOnly = false;
    updateSupportColorStatus(fieldset);
  }
}

function initSupportColorField(fieldset) {
  if (!(fieldset instanceof HTMLElement) || fieldset.dataset.supportColorReady === "true") {
    return;
  }
  fieldset.dataset.supportColorReady = "true";
  const hidden = fieldset.querySelector("[data-support-color-multicolor-input]");
  if (hidden instanceof HTMLInputElement && hidden.value === "on") {
    setMulticolorMode(fieldset, true);
  } else {
    syncSupportColorFromHex(fieldset);
  }
}

function handleSupportColorFieldEvent(event) {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) {
    return;
  }
  const fieldset = target.closest("[data-support-color-field]");
  if (!(fieldset instanceof HTMLElement)) {
    return;
  }
  if (target.matches("[data-support-color-hex]")) {
    syncSupportColorFromHex(fieldset);
  }
}

function closeAllHexColorPopovers() {
  document.querySelectorAll("[data-hex-color-popover]").forEach((node) => {
    if (!(node instanceof HTMLElement)) {
      return;
    }
    const control =
      node.closest("[data-hex-color-control]") ||
      (node.dataset.hexColorControlId
        ? document.querySelector(`[data-hex-color-id="${node.dataset.hexColorControlId}"]`)
        : null);
    node.hidden = true;
    if (control instanceof HTMLElement) {
      unmountHexPopover(control, node);
      const trigger = control.querySelector("[data-hex-color-trigger]");
      if (trigger instanceof HTMLButtonElement) {
        trigger.setAttribute("aria-expanded", "false");
      }
    }
  });
}

function positionHexPopover(trigger, popover, triggerRect = null) {
  popover.hidden = false;
  popover.style.visibility = "hidden";
  const rect = triggerRect || trigger.getBoundingClientRect();
  const width = popover.offsetWidth || 248;
  const height = popover.offsetHeight || 280;
  const gap = 8;
  const margin = 10;
  let top = rect.bottom + gap;
  if (top + height > window.innerHeight - margin) {
    top = rect.top - height - gap;
  }
  top = Math.max(margin, Math.min(top, window.innerHeight - height - margin));
  let left = rect.left;
  // Si le nuancier dépasse à droite, l’aligner sur le bord droit du déclencheur.
  if (left + width > window.innerWidth - margin) {
    left = rect.right - width;
  }
  left = Math.max(margin, Math.min(left, window.innerWidth - width - margin));
  popover.style.position = "fixed";
  popover.style.top = `${top}px`;
  popover.style.left = `${left}px`;
  popover.style.zIndex = "10050";
  popover.style.visibility = "visible";
}

function bindHexColorGlobalEvents() {
  if (bindHexColorGlobalEvents.initialized) {
    return;
  }
  bindHexColorGlobalEvents.initialized = true;

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (
      target instanceof Element &&
      (target.closest("[data-hex-color-control]") || target.closest("[data-hex-color-popover]"))
    ) {
      return;
    }
    closeAllHexColorPopovers();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeAllHexColorPopovers();
    }
  });

  document.addEventListener(
    "close",
    (event) => {
      if (event.target instanceof HTMLDialogElement) {
        closeAllHexColorPopovers();
      }
    },
    true
  );
}

function initHexColorControl(control) {
  if (!(control instanceof HTMLElement) || control.dataset.hexColorReady === "true") {
    return;
  }
  control.dataset.hexColorReady = "true";
  const controlId =
    control.dataset.hexColorId ||
    (control.dataset.hexColorId = `hex-control-${Math.random().toString(36).slice(2, 10)}`);

  const trigger = control.querySelector("[data-hex-color-trigger]");
  const popover = control.querySelector("[data-hex-color-popover]");
  const popoverInput = control.querySelector("[data-hex-color-popover-input]");
  const nativePicker = control.querySelector("[data-hex-color-native]");
  if (
    !(trigger instanceof HTMLButtonElement) ||
    !(popover instanceof HTMLElement) ||
    !(popoverInput instanceof HTMLInputElement)
  ) {
    return;
  }
  popover.dataset.hexColorControlId = controlId;
  control._hexPopoverEl = popover;
  control._hexPopoverInput = popoverInput;
  control._hexNativePicker = nativePicker instanceof HTMLInputElement ? nativePicker : null;

  const isPreview = control.hasAttribute("data-configurator-custom-bg-control");
  const fieldset = control.closest("[data-support-color-field]");
  const hexField = fieldset?.querySelector("[data-support-color-hex]");

  function closePopover() {
    popover.hidden = true;
    unmountHexPopover(control, popover);
    trigger.setAttribute("aria-expanded", "false");
  }

  function openPopover() {
    closeAllHexColorPopovers();
    const source =
      hexField instanceof HTMLInputElement && hexField.value.trim()
        ? hexField.value
        : popoverInput.value;
    const normalized = normalizeHexColor(source) || "#ffffff";
    syncHexColorControlSwatch(control, normalized);
    const triggerRect = trigger.getBoundingClientRect();
    mountHexPopover(control, popover);
    positionHexPopover(trigger, popover, triggerRect);
    trigger.setAttribute("aria-expanded", "true");
    requestAnimationFrame(() => {
      popoverInput.focus();
      popoverInput.select();
    });
  }

  function applyColor(rawValue) {
    const normalized = syncHexColorControlSwatch(control, rawValue);
    if (!normalized) {
      return;
    }
    if (isPreview) {
      const root = findConfiguratorRoot(control);
      if (root) {
        setPreviewBackground(root, normalized);
      }
      return;
    }
    if (fieldset instanceof HTMLElement) {
      applySupportColorPickerValue(fieldset, normalized);
    }
  }

  trigger.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (trigger.disabled) {
      return;
    }
    if (popover.hidden) {
      openPopover();
    } else {
      closePopover();
    }
  });

  function syncPopoverHexInput() {
    let display = popoverInput.value.trim().toUpperCase();
    if (display && !display.startsWith("#")) {
      display = `#${display}`;
    }
    if (display !== popoverInput.value) {
      popoverInput.value = display;
    }
    return display;
  }

  popoverInput.addEventListener("input", () => {
    applyColor(syncPopoverHexInput());
  });

  popoverInput.addEventListener("change", () => {
    applyColor(syncPopoverHexInput());
  });

  popoverInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      applyColor(syncPopoverHexInput());
      closePopover();
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closePopover();
    }
  });

  popover.addEventListener("mousedown", (event) => {
    event.stopPropagation();
  });

  popover.addEventListener("click", (event) => {
    event.stopPropagation();
  });

  if (nativePicker instanceof HTMLInputElement) {
    nativePicker.addEventListener("input", () => {
      applyColor(nativePicker.value);
    });
    nativePicker.addEventListener("change", () => {
      applyColor(nativePicker.value);
    });
  }

  popover.querySelectorAll("[data-hex-color-preset]").forEach((btn) => {
    if (!(btn instanceof HTMLButtonElement)) {
      return;
    }
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      applyColor(btn.dataset.hexColorPreset || "");
    });
  });
}

function initHexColorControls(scope = document, { force = false } = {}) {
  bindHexColorGlobalEvents();
  scope.querySelectorAll("[data-hex-color-control]").forEach((control) => {
    if (force) {
      delete control.dataset.hexColorReady;
    }
    initHexColorControl(control);
  });
}

function bindSupportColorEvents() {
  if (bindSupportColorEvents.initialized) {
    return;
  }
  bindSupportColorEvents.initialized = true;

  document.body.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }
    const rainbowButton = target.closest("[data-support-color-multicolor]");
    if (!(rainbowButton instanceof HTMLButtonElement)) {
      return;
    }
    const fieldset = rainbowButton.closest("[data-support-color-field]");
    if (fieldset instanceof HTMLElement) {
      const isActive = rainbowButton.classList.contains("is-active");
      if (isActive) {
        setMulticolorMode(fieldset, false);
      } else {
        setMulticolorMode(fieldset, true);
      }
    }
  });

  document.body.addEventListener("input", handleSupportColorFieldEvent);
  document.body.addEventListener("change", handleSupportColorFieldEvent);
}

function initSupportColorFields(scope = document, { force = false } = {}) {
  bindSupportColorEvents();
  initHexColorControls(scope, { force });
  scope.querySelectorAll("[data-support-color-field]").forEach((fieldset) => {
    if (force) {
      delete fieldset.dataset.supportColorReady;
    }
    initSupportColorField(fieldset);
  });
}

function revealConfiguratorParams(root) {
  if (!(root instanceof HTMLElement)) {
    return;
  }
  root.querySelectorAll("[data-configurator-params]").forEach((section) => {
    section.hidden = false;
  });
  const hint = root.querySelector("[data-configurator-hint]");
  if (hint instanceof HTMLElement) {
    hint.hidden = true;
  }
}

function initConfigurator(root, { force = false } = {}) {
  if (!(root instanceof HTMLElement)) {
    return;
  }
  if (force) {
    delete root.dataset.configuratorReady;
    resetPreviewMediaSizing(root);
  }
  if (root.dataset.configuratorReady === "true") {
    return;
  }
  root.dataset.configuratorReady = "true";
  bindDimensionInputs(root);
  initExistingPreview(root);
  syncPreviewBounds(root);
  bindPreviewFitObserver(root);
  scheduleFitPreviewMedia(root);
  initSupportColorFields(root, { force });
  initHexColorControls(root, { force });
  setPreviewBackground(root, "checker", root.querySelector('[data-configurator-bg="checker"]'));
}

function clearOrderProjectValidateQuery() {
  try {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("validate")) {
      return;
    }
    url.searchParams.delete("validate");
    const next = `${url.pathname}${url.search}${url.hash}`;
    window.history.replaceState({}, "", next);
  } catch (_error) {
    /* ignore URL API failures */
  }
}

function dismissAutoOpenDialog(dialog) {
  if (!(dialog instanceof HTMLDialogElement)) {
    return;
  }
  autoOpenedDialogs.add(dialog);
  dialog.removeAttribute("data-dialog-auto-open");
  if (dialog.id === "add-visual-dialog" || dialog.hasAttribute("data-add-visual-dialog")) {
    clearOrderProjectValidateQuery();
  }
}

function openAutoOpenDialogs(scope = document) {
  if (!scope || typeof scope.querySelectorAll !== "function") {
    return;
  }
  scope.querySelectorAll("dialog[data-dialog-auto-open]").forEach((dialog) => {
    if (!(dialog instanceof HTMLDialogElement) || dialog.open) {
      return;
    }
    // Same DOM node: open once. Fresh HTMX nodes are new objects → reopen OK.
    if (autoOpenedDialogs.has(dialog)) {
      return;
    }
    autoOpenedDialogs.add(dialog);
    dialog.showModal();
    initB2BConfigurators(dialog, { force: true });
  });
}

function initB2BConfigurators(scope = document, { force = false } = {}) {
  scope.querySelectorAll("[data-b2b-configurator]").forEach((root) => {
    initConfigurator(root, { force });
  });
  initSupportColorFields(scope, { force });
  openAutoOpenDialogs(scope);
}

function openConfiguratorDialog(dialog) {
  if (!(dialog instanceof HTMLDialogElement)) {
    return;
  }
  if (!dialog.open) {
    dialog.showModal();
  }
  initB2BConfigurators(dialog, { force: true });
}

function updateSelectedFilesSummary(root, input) {
  const summary = root.querySelector("[data-selected-files-summary]");
  if (!(summary instanceof HTMLElement)) {
    return;
  }
  const files = Array.from(input.files || []);
  if (files.length === 0) {
    summary.textContent = "Aucun fichier sélectionné.";
    return;
  }
  summary.textContent = files.length === 1
    ? files[0].name
    : `${files.length} fichiers sélectionnés · aperçu du premier fichier`;
}

function openFilePickerBeforeDialog(opener) {
  const dialog = document.getElementById(opener.dataset.filePickerDialog || "");
  if (!(dialog instanceof HTMLDialogElement)) {
    return;
  }
  const targetInput = dialog.querySelector("[data-configurator-file]");
  if (!(targetInput instanceof HTMLInputElement) || targetInput.disabled) {
    return;
  }

  const picker = document.createElement("input");
  picker.type = "file";
  picker.accept = targetInput.accept;
  picker.multiple = targetInput.multiple;
  picker.addEventListener(
    "change",
    () => {
      if (!picker.files?.length) {
        return;
      }
      const form = targetInput.closest("form");
      if (form instanceof HTMLFormElement) {
        form.reset();
      }
      // FileList d’un autre input : assigner via DataTransfer (reset vide sinon le fichier).
      const transfer = new DataTransfer();
      Array.from(picker.files).forEach((file) => transfer.items.add(file));
      targetInput.files = transfer.files;
      openConfiguratorDialog(dialog);
      targetInput.dispatchEvent(new Event("change", { bubbles: true }));
    },
    { once: true }
  );
  picker.click();
}

function bindOrderStartPickVisual() {
  document.body.addEventListener("click", (event) => {
    const trigger = event.target;
    if (!(trigger instanceof Element)) {
      return;
    }
    const button = trigger.closest("[data-order-start-pick-visual]");
    if (!(button instanceof HTMLButtonElement)) {
      return;
    }
    event.preventDefault();
    const form = button.closest("form[data-order-start-form]");
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    const nameInput = form.querySelector("#id-name, [name='name']");
    if (nameInput instanceof HTMLInputElement && !nameInput.value.trim()) {
      nameInput.reportValidity();
      nameInput.focus();
      return;
    }
    if (typeof form.reportValidity === "function" && !form.reportValidity()) {
      return;
    }
    const fileInput = form.querySelector("[data-order-start-file]");
    if (!(fileInput instanceof HTMLInputElement)) {
      form.requestSubmit?.() || form.submit();
      return;
    }
    const hint = form.querySelector("[data-order-start-file-hint]");
    const accept = fileInput.accept || "";
    const picker = document.createElement("input");
    picker.type = "file";
    picker.accept = accept;
    picker.addEventListener(
      "change",
      () => {
        if (!picker.files?.length) {
          if (hint instanceof HTMLElement) {
            hint.hidden = false;
            hint.textContent = "Choisissez un fichier pour continuer.";
          }
          return;
        }
        const transfer = new DataTransfer();
        Array.from(picker.files).forEach((file) => transfer.items.add(file));
        fileInput.files = transfer.files;
        if (hint instanceof HTMLElement) {
          hint.hidden = false;
          hint.textContent = `Fichier sélectionné : ${picker.files[0].name}`;
        }
        button.disabled = true;
        form.requestSubmit?.() || form.submit();
      },
      { once: true }
    );
    picker.click();
  });
}

function bindPreviewPanDrag() {
  let activeStage = null;
  let pointerId = null;
  let originX = 0;
  let originY = 0;
  let originScrollLeft = 0;
  let originScrollTop = 0;

  const endPan = (event) => {
    if (!(activeStage instanceof HTMLElement)) {
      return;
    }
    if (pointerId !== null && event?.pointerId !== undefined && event.pointerId !== pointerId) {
      return;
    }
    try {
      if (pointerId !== null && activeStage.hasPointerCapture?.(pointerId)) {
        activeStage.releasePointerCapture(pointerId);
      }
    } catch (_error) {
      /* ignore capture release races */
    }
    activeStage.classList.remove("is-panning");
    activeStage = null;
    pointerId = null;
  };

  document.body.addEventListener("pointerdown", (event) => {
    if (!(event.target instanceof Element) || event.button !== 0) {
      return;
    }
    if (event.target.closest("button, a, input, label, [data-preview-zoom-in], [data-preview-zoom-out], [data-preview-zoom-reset]")) {
      return;
    }
    const stage = event.target.closest("[data-configurator-stage].is-zoomed");
    if (!(stage instanceof HTMLElement)) {
      return;
    }
    if (stage.scrollWidth <= stage.clientWidth + 1 && stage.scrollHeight <= stage.clientHeight + 1) {
      return;
    }
    activeStage = stage;
    pointerId = event.pointerId;
    originX = event.clientX;
    originY = event.clientY;
    originScrollLeft = stage.scrollLeft;
    originScrollTop = stage.scrollTop;
    stage.classList.add("is-panning");
    try {
      stage.setPointerCapture(pointerId);
    } catch (_error) {
      /* pointer capture optional */
    }
    event.preventDefault();
  });

  document.body.addEventListener("pointermove", (event) => {
    if (!(activeStage instanceof HTMLElement) || event.pointerId !== pointerId) {
      return;
    }
    activeStage.scrollLeft = originScrollLeft - (event.clientX - originX);
    activeStage.scrollTop = originScrollTop - (event.clientY - originY);
  });

  document.body.addEventListener("pointerup", endPan);
  document.body.addEventListener("pointercancel", endPan);
  document.body.addEventListener("lostpointercapture", endPan);
}

function bindConfiguratorEvents() {
  if (configuratorEventsBound) {
    return;
  }
  configuratorEventsBound = true;
  bindOrderStartPickVisual();
  bindPreviewPanDrag();

  document.body.addEventListener("change", (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || !input.matches("[data-configurator-file]")) {
      return;
    }
    const root = findConfiguratorRoot(input);
    if (!root) {
      return;
    }
    updateSelectedFilesSummary(root, input);
    const validationMessage = validateConfiguratorFiles(root, input);
    if (validationMessage) {
      clearConfiguratorPreview(root, "Import impossible", validationMessage);
      window.preniumToast?.(validationMessage, "error");
      return;
    }
    const file = input.files?.[0];
    if (file) {
      previewSelectedFile(root, file);
    }
  });

  document.body.addEventListener("b2b:preview-file-request", (event) => {
    const root = event.target;
    const file = event.detail?.file;
    if (root instanceof HTMLElement && file instanceof File) {
      previewSelectedFile(root, file);
    }
  });

  document.body.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }
    const filePickerOpener = target.closest("[data-file-picker-dialog]");
    if (filePickerOpener instanceof HTMLElement) {
      event.preventDefault();
      openFilePickerBeforeDialog(filePickerOpener);
      return;
    }
    const zoomControl = target.closest(
      "[data-preview-zoom-in], [data-preview-zoom-out], [data-preview-zoom-reset]"
    );
    if (zoomControl instanceof HTMLButtonElement) {
      const root = findConfiguratorRoot(zoomControl);
      if (root) {
        const bounds = findActivePreviewBounds(root);
        if (
          !(bounds instanceof HTMLElement)
          || !bounds.dataset.previewBaseWidth
          || !bounds.dataset.previewBaseHeight
        ) {
          fitPreviewMedia(root);
        }
        const current = readPreviewZoom(root);
        const next = zoomControl.hasAttribute("data-preview-zoom-in")
          ? current + previewZoomStep
          : zoomControl.hasAttribute("data-preview-zoom-out")
            ? current - previewZoomStep
            : previewZoomMin;
        applyPreviewZoom(root, next, {
          preserveCenter: !zoomControl.hasAttribute("data-preview-zoom-reset"),
        });
      }
      return;
    }
    const bgButton = target.closest("[data-configurator-bg]");
    if (bgButton instanceof HTMLElement) {
      const root = findConfiguratorRoot(bgButton);
      if (root) {
        setPreviewBackground(root, bgButton.dataset.configuratorBg || "checker", bgButton);
      }
      return;
    }
    const thinZoneToggle = target.closest("[data-thin-zone-toggle]");
    if (thinZoneToggle instanceof HTMLButtonElement) {
      const root = findConfiguratorRoot(thinZoneToggle);
      const overlay = root?.querySelector("[data-thin-zone-overlay]");
      if (overlay instanceof HTMLImageElement) {
        const willShow = overlay.hidden;
        overlay.hidden = !willShow;
        thinZoneToggle.setAttribute("aria-pressed", String(willShow));
        thinZoneToggle.classList.toggle("is-active", willShow);
      }
      return;
    }
    const preflightThinToggle = target.closest("[data-preflight-thin-toggle]");
    if (preflightThinToggle instanceof HTMLButtonElement) {
      const root = findConfiguratorRoot(preflightThinToggle);
      const overlay = root?.querySelector("[data-preflight-thin-overlay]");
      if (overlay instanceof HTMLCanvasElement) {
        const willShow = overlay.hidden;
        overlay.hidden = !willShow;
        preflightThinToggle.setAttribute("aria-pressed", String(willShow));
        preflightThinToggle.classList.toggle("is-active", willShow);
      }
      return;
    }
    const preflightFadeToggle = target.closest("[data-preflight-fade-toggle]");
    if (preflightFadeToggle instanceof HTMLButtonElement) {
      const root = findConfiguratorRoot(preflightFadeToggle);
      const overlay = root?.querySelector("[data-preflight-fade-overlay]");
      if (overlay instanceof HTMLCanvasElement) {
        const willShow = overlay.hidden;
        overlay.hidden = !willShow;
        preflightFadeToggle.setAttribute("aria-pressed", String(willShow));
        preflightFadeToggle.classList.toggle("is-active", willShow);
      }
      return;
    }
    const semiTransparencyToggle = target.closest("[data-semi-transparency-toggle]");
    if (semiTransparencyToggle instanceof HTMLButtonElement) {
      const root = findConfiguratorRoot(semiTransparencyToggle);
      const overlay = root?.querySelector("[data-semi-transparency-overlay]");
      if (overlay instanceof HTMLImageElement) {
        const willShow = overlay.hidden;
        overlay.hidden = !willShow;
        semiTransparencyToggle.setAttribute("aria-pressed", String(willShow));
        semiTransparencyToggle.classList.toggle("is-active", willShow);
      }
      return;
    }
    const opener = target.closest("[data-dialog-open]");
    if (opener instanceof HTMLElement) {
      const dialog = document.getElementById(opener.dataset.dialogOpen || "");
      openConfiguratorDialog(dialog);
      return;
    }
    const closer = target.closest("[data-dialog-close]");
    if (closer instanceof HTMLElement) {
      const dialog = closer.closest("dialog");
      if (dialog instanceof HTMLDialogElement) {
        dismissAutoOpenDialog(dialog);
        dialog.close();
      }
      return;
    }
    if (target instanceof HTMLDialogElement) {
      dismissAutoOpenDialog(target);
      target.close();
    }
  });

  document.body.addEventListener("close", (event) => {
    const dialog = event.target;
    if (dialog instanceof HTMLDialogElement) {
      dismissAutoOpenDialog(dialog);
    }
  }, true);

  document.addEventListener(
    "toggle",
    (event) => {
      const dialog = event.target;
      if (dialog instanceof HTMLDialogElement && dialog.open) {
        initB2BConfigurators(dialog, { force: true });
      }
    },
    true
  );
}

function mountConfigurator(scope = document) {
  try {
    bindConfiguratorEvents();
    initB2BConfigurators(scope);
  } catch (error) {
    console.error("[b2b-configurator] mount failed", error);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => mountConfigurator());
} else {
  mountConfigurator();
}

function onBodyReady(callback) {
  if (document.body) {
    callback();
    return;
  }
  document.addEventListener("DOMContentLoaded", callback, { once: true });
}

function findOpenVisualDialog(root) {
  if (!(root instanceof HTMLElement)) {
    return null;
  }
  if (
    root instanceof HTMLDialogElement
    && root.open
    && root.id.startsWith("visual-dialog-")
  ) {
    return root;
  }
  const dialogs = root.querySelectorAll("dialog[id^='visual-dialog-']");
  for (const dialog of dialogs) {
    if (dialog instanceof HTMLDialogElement && dialog.open) {
      return dialog;
    }
  }
  return null;
}

onBodyReady(() => {
  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail?.target;
    closeAllHexColorPopovers();
    if (target instanceof HTMLElement) {
      initB2BConfigurators(target, { force: true });
      return;
    }
    initB2BConfigurators(document, { force: true });
  });

  document.body.addEventListener("htmx:beforeRequest", (event) => {
    const elt = event.detail?.elt;
    if (!(elt instanceof HTMLElement)) {
      return;
    }
    const dialog = elt.closest("dialog[id^='visual-dialog-']");
    if (!(dialog instanceof HTMLDialogElement) || !dialog.open) {
      return;
    }
    const confirmForm =
      elt.matches("form[data-visual-confirm], form[data-add-visual-confirm]")
        ? elt
        : elt.closest("form[data-visual-confirm], form[data-add-visual-confirm]");
    if (confirmForm instanceof HTMLFormElement) {
      // Validation / enregistrement support : fermer la modal après succès.
      projectDialogCloseOnSuccess = dialog.id;
      projectDialogToRestore = "";
      return;
    }
    // Autres actions HTMX dans la modal (remplacer fichier…) : la rouvrir après swap.
    projectDialogToRestore = dialog.id;
  });

  document.body.addEventListener("htmx:afterSettle", () => {
    // Pendant un confirm support, ne jamais rouvrir ici (afterOnLoad gère succès / erreur).
    if (projectDialogCloseOnSuccess) {
      return;
    }
    if (!projectDialogToRestore) {
      return;
    }
    const dialog = document.getElementById(projectDialogToRestore);
    projectDialogToRestore = "";
    if (dialog instanceof HTMLDialogElement && !dialog.open) {
      dialog.showModal();
      initB2BConfigurators(dialog, { force: true });
    }
  });

  document.body.addEventListener("htmx:afterOnLoad", (event) => {
    const elt = event.detail?.elt;
    const xhr = event.detail?.xhr;
    const successful = Boolean(event.detail?.successful);
    const status = Number(xhr?.status || 0);
    const ok = successful || (status >= 200 && status < 300);

    if (
      ok
      && elt instanceof HTMLFormElement
      && elt.matches("[data-add-visual-confirm]")
    ) {
      const addDialog = document.getElementById("add-visual-dialog");
      if (addDialog instanceof HTMLDialogElement) {
        dismissAutoOpenDialog(addDialog);
        addDialog.close();
      }
    }

    if (
      ok
      && elt instanceof HTMLFormElement
      && elt.matches("[data-add-visual-form]")
    ) {
      // Après envoi : ouvrir la modale d’analyse (nouveau nœud HTMX).
      requestAnimationFrame(() => {
        openAutoOpenDialogs(document);
        const addDialog = document.getElementById("add-visual-dialog");
        if (
          addDialog instanceof HTMLDialogElement
          && !addDialog.open
          && addDialog.querySelector("#add-visual-validation-panel")
        ) {
          openConfiguratorDialog(addDialog);
        }
      });
    }

    if (!projectDialogCloseOnSuccess) {
      return;
    }

    const dialogId = projectDialogCloseOnSuccess;
    projectDialogCloseOnSuccess = "";
    projectDialogToRestore = "";

    if (ok) {
      // Succès : modal reste fermée.
      return;
    }

    // Erreur : rouvrir immédiatement (afterSettle a déjà eu lieu).
    const dialog = document.getElementById(dialogId);
    if (dialog instanceof HTMLDialogElement && !dialog.open) {
      dialog.showModal();
      initB2BConfigurators(dialog, { force: true });
    }
  });

  document.body.addEventListener("htmx:load", (event) => {
    const element = event.detail?.elt;
    mountConfigurator(element instanceof HTMLElement ? element : document);
  });

  document.body.addEventListener("htmx:beforeCleanupElement", (event) => {
    const cleanupRoot = event.detail?.elt;
    if (!(cleanupRoot instanceof HTMLElement)) {
      return;
    }
    // Ne pas forcer la réouverture si on ferme volontairement après confirm.
    if (!projectDialogCloseOnSuccess) {
      const openProjectDialog = findOpenVisualDialog(cleanupRoot);
      if (openProjectDialog instanceof HTMLDialogElement) {
        projectDialogToRestore = openProjectDialog.id;
      }
    }
    closeAllHexColorPopovers();
    cleanupRoot.querySelectorAll("[data-hex-color-control]").forEach((control) => {
      if (control instanceof HTMLElement) {
        delete control.dataset.hexColorReady;
        delete control._hexPopoverAnchor;
        delete control._hexPopoverMount;
        delete control._hexPopoverEl;
        delete control._hexPopoverInput;
        delete control._hexNativePicker;
      }
    });
    const configurators = cleanupRoot.matches("[data-b2b-configurator]")
      ? [cleanupRoot]
      : cleanupRoot.querySelectorAll("[data-b2b-configurator]");
    configurators.forEach((configurator) => {
      const objectUrl = previewObjectUrls.get(configurator);
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
        previewObjectUrls.delete(configurator);
      }
      delete configurator.dataset.configuratorReady;
    });
  });
});
