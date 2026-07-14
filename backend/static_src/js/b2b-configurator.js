const previewObjectUrls = new WeakMap();
const previewRenderTokens = new WeakMap();
const previewFitObservers = new WeakMap();
const previewZoomMin = 1;
const previewZoomMax = 4;
const previewZoomStep = 0.5;
const browserPreviewMimeTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
const pdfJsModuleUrl = "/static/vendor/pdfjs/pdf.js";
const pdfJsWorkerUrl = "/static/vendor/pdfjs/pdf.worker.js";
let pdfJsPromise = null;
let configuratorEventsBound = false;

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

function setPreviewBackground(root, value, activeControl = null) {
  const stage = root.querySelector("[data-configurator-stage]");
  if (!(stage instanceof HTMLElement)) {
    return;
  }
  const checker = value === "checker";
  stage.classList.toggle("is-checker", checker);
  if (checker) {
    stage.style.removeProperty("background-color");
    stage.style.setProperty("--b2b-preview-bg", "#ffffff");
  } else {
    stage.style.backgroundColor = value;
    stage.style.setProperty("--b2b-preview-bg", value);
  }
  root.querySelectorAll("[data-configurator-bg]").forEach((button) => {
    const active = button === activeControl;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  const customControl = root.querySelector("[data-configurator-custom-bg-control]");
  const isCustomActive = !checker && activeControl === null;
  if (customControl instanceof HTMLElement) {
    customControl.classList.toggle("is-active", isCustomActive);
    if (!checker && typeof value === "string" && value.startsWith("#")) {
      syncHexColorControlSwatch(customControl, value);
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
  try {
    const pdfJs = await loadPdfJs();
    const fileBuffer = await file.arrayBuffer();
    if (previewRenderTokens.get(root) !== renderToken) {
      return;
    }
    const loadingTask = pdfJs.getDocument({ data: new Uint8Array(fileBuffer) });
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
    revealConfiguratorParams(root);
    scheduleFitPreviewMedia(root);
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
  } finally {
    if (pdfDocument !== null) {
      await pdfDocument.destroy();
    }
  }
}

function previewSelectedFile(root, file) {
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

  const isBrowserImage = browserPreviewMimeTypes.has(file.type);
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isBrowserImage && !isPdf) {
    setPlaceholder(placeholder, "Aperçu en préparation", file.name);
    if (pixels instanceof HTMLElement) {
      pixels.textContent = "Le fichier sera analysé en arrière-plan dès son ajout.";
    }
    revealConfiguratorParams(root);
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
    revealConfiguratorParams(root);
    scheduleFitPreviewMedia(root);
  };
  preview.onerror = () => {
    if (previewRenderTokens.get(root) !== renderToken) {
      return;
    }
    setPreviewMediaVisible(preview, false);
    setPlaceholder(placeholder, "Aperçu indisponible", file.name);
  };
  preview.src = objectUrl;
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
    const trigger = hexControl.querySelector("[data-hex-color-trigger]");
    if (trigger instanceof HTMLButtonElement) {
      trigger.disabled = enabled;
    }
  }
  if (hexInput instanceof HTMLInputElement) {
    hexInput.readOnly = enabled;
    if (enabled) {
      hexInput.value = "";
    } else if (!hexInput.value.trim()) {
      hexInput.value = "#FFFFFF";
    }
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
  const width = popover.offsetWidth || 152;
  const height = popover.offsetHeight || 120;
  const gap = 6;
  const margin = 8;
  let top = rect.bottom + gap;
  if (top + height > window.innerHeight - margin) {
    top = rect.top - height - gap;
  }
  top = Math.max(margin, Math.min(top, window.innerHeight - height - margin));
  let left = rect.left;
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
        applySupportColorPickerValue(fieldset, "#ffffff");
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

function initB2BConfigurators(scope = document, { force = false } = {}) {
  scope.querySelectorAll("[data-b2b-configurator]").forEach((root) => {
    initConfigurator(root, { force });
  });
  initSupportColorFields(scope, { force });
  scope.querySelectorAll("dialog[data-dialog-auto-open]").forEach((dialog) => {
    if (dialog instanceof HTMLDialogElement && !dialog.open) {
      dialog.showModal();
      initB2BConfigurators(dialog, { force: true });
    }
  });
}

function bindConfiguratorEvents() {
  if (configuratorEventsBound) {
    return;
  }
  configuratorEventsBound = true;

  document.body.addEventListener("change", (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || !input.matches("[data-configurator-file]")) {
      return;
    }
    const root = findConfiguratorRoot(input);
    if (!root) {
      return;
    }
    const file = input.files?.[0];
    if (file) {
      previewSelectedFile(root, file);
    }
  });

  document.body.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }
    const zoomControl = target.closest(
      "[data-preview-zoom-in], [data-preview-zoom-out], [data-preview-zoom-reset]"
    );
    if (zoomControl instanceof HTMLButtonElement) {
      const root = findConfiguratorRoot(zoomControl);
      if (root) {
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
        const label = thinZoneToggle.querySelector("[data-thin-zone-toggle-label]");
        if (label) {
          label.textContent = willShow
            ? "Zones sous 0,5 mm affichées"
            : "Zones sous 0,5 mm masquées";
        }
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
        const label = semiTransparencyToggle.querySelector("[data-semi-transparency-toggle-label]");
        if (label) {
          label.textContent = willShow
            ? "Semi-transparences affichées"
            : "Semi-transparences masquées";
        }
      }
      return;
    }
    const opener = target.closest("[data-dialog-open]");
    if (opener instanceof HTMLElement) {
      const dialog = document.getElementById(opener.dataset.dialogOpen || "");
      if (dialog instanceof HTMLDialogElement && !dialog.open) {
        dialog.showModal();
        initB2BConfigurators(dialog, { force: true });
      }
      return;
    }
    const closer = target.closest("[data-dialog-close]");
    if (closer instanceof HTMLElement) {
      const dialog = closer.closest("dialog");
      if (dialog instanceof HTMLDialogElement) {
        dialog.close();
      }
      return;
    }
    if (target instanceof HTMLDialogElement) {
      target.close();
    }
  });

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
  bindConfiguratorEvents();
  initB2BConfigurators(scope);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => mountConfigurator());
} else {
  mountConfigurator();
}

document.body.addEventListener("htmx:afterSwap", (event) => {
  const target = event.detail?.target;
  closeAllHexColorPopovers();
  if (target instanceof HTMLElement) {
    initB2BConfigurators(target, { force: true });
    return;
  }
  initB2BConfigurators(document, { force: true });
});

document.body.addEventListener("htmx:afterOnLoad", (event) => {
  const elt = event.detail?.elt;
  if (
    event.detail?.successful
    && elt instanceof HTMLFormElement
    && elt.matches("[data-add-visual-confirm]")
  ) {
    document.getElementById("add-visual-dialog")?.close();
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
