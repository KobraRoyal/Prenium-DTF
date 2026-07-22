const root = document.querySelector("[data-gang-sheet-editor]");

if (root) {
  const initialNode = document.getElementById("gang-sheet-initial-state");
  let state = JSON.parse(initialNode.textContent);
  let selectedId = null;
  let busy = false;
  let dirty = false;
  let zoom = 1;
  let pollTimer = null;
  let galleryWasPending = qPendingGallery();
  const canEdit = root.dataset.canEdit === "true";
  const canvas = root.querySelector("[data-sheet-canvas]");
  const csrf = root.querySelector("[data-csrf]").value;
  const q = (selector) => root.querySelector(selector);
  const qa = (selector) => Array.from(root.querySelectorAll(selector));
  const round = (value, digits = 2) => Number(Number(value).toFixed(digits));
  const selected = () => state.items.find((item) => item.public_id === selectedId);

  function setDirty(value = true) {
    dirty = value;
    root.dataset.dirty = String(dirty);
  }

  function renderZoom() {
    const stage = q("[data-editor-panel='canvas']");
    const availableWidth = Math.max(320, (stage?.clientWidth || 0) - 64);
    const baseWidth = Math.min(700, availableWidth);
    canvas.style.width = `${Math.round(baseWidth * zoom)}px`;
    q("[data-zoom-value]").textContent = `${Math.round(zoom * 100)} %`;
    window.requestAnimationFrame(() => {
      positionSelectedItemToolbar();
    });
  }

  function setMobilePanel(panelName) {
    qa("[data-mobile-panel-tab]").forEach((tab) => {
      const active = tab.dataset.mobilePanelTab === panelName;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    qa("[data-editor-panel]").forEach((panel) => {
      panel.classList.toggle("is-mobile-active", panel.dataset.editorPanel === panelName);
    });
    if (panelName === "canvas") window.requestAnimationFrame(renderZoom);
  }

  function qPendingGallery() {
    return root?.querySelector("[data-asset-list]")?.dataset.hasPending === "true";
  }

  function effectiveSize(item) {
    return [90, 270].includes(Number(item.rotation))
      ? { width: item.height_mm, height: item.width_mm }
      : { width: item.width_mm, height: item.height_mm };
  }

  function resizeItemFromPointer(item, { start, deltaX, deltaY, lockRatio }) {
    const quarterTurn = [90, 270].includes(Number(item.rotation));
    const ratio = start.height / start.width;
    if (quarterTurn) {
      item.height_mm = Math.max(1, round(start.height + deltaX));
      item.width_mm = lockRatio
        ? Math.max(1, round(item.height_mm / ratio))
        : Math.max(1, round(start.width + deltaY));
      return;
    }
    item.width_mm = Math.max(1, round(start.width + deltaX));
    item.height_mm = lockRatio
      ? Math.max(1, round(item.width_mm * ratio))
      : Math.max(1, round(start.height + deltaY));
  }

  function createItemAction({ label, icon, attribute, danger = false }) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `gang-sheet-item-action${danger ? " is-danger" : ""}`;
    button.setAttribute(attribute, "");
    const iconNode = document.createElement("span");
    iconNode.setAttribute("aria-hidden", "true");
    iconNode.textContent = icon;
    const labelNode = document.createElement("span");
    labelNode.textContent = label;
    button.append(iconNode, labelNode);
    return button;
  }

  function positionSelectedItemToolbar() {
    const toolbar = canvas.querySelector("[data-item-toolbar]");
    const itemNode = selectedId ? canvas.querySelector(`[data-item-id="${selectedId}"]`) : null;
    if (!toolbar || !itemNode) return;
    const gap = 6;
    const canvasRect = canvas.getBoundingClientRect();
    const itemRect = itemNode.getBoundingClientRect();
    const toolbarRect = toolbar.getBoundingClientRect();
    const contentLeft = canvasRect.left + canvas.clientLeft;
    const contentTop = canvasRect.top + canvas.clientTop;
    const idealLeft = itemRect.left - contentLeft + (itemRect.width - toolbarRect.width) / 2;
    const maxLeft = Math.max(gap, canvas.clientWidth - toolbarRect.width - gap);
    const left = Math.max(gap, Math.min(idealLeft, maxLeft));
    let top = itemRect.top - contentTop - toolbarRect.height - gap;
    if (top < gap) top = itemRect.bottom - contentTop + gap;
    const maxTop = Math.max(gap, canvas.clientHeight - toolbarRect.height - gap);
    toolbar.style.left = `${round(left)}px`;
    toolbar.style.top = `${round(Math.max(gap, Math.min(top, maxTop)))}px`;
    toolbar.style.visibility = "visible";
  }

  function renderSelectedItemToolbar(item) {
    const toolbar = document.createElement("div");
    toolbar.className = "gang-sheet-item-toolbar";
    toolbar.dataset.itemToolbar = "";
    toolbar.setAttribute("role", "toolbar");
    toolbar.setAttribute("aria-label", `Actions rapides pour ${item.asset_name}`);
    toolbar.style.visibility = "hidden";
    const rotateButton = createItemAction({
      label: "Pivoter",
      icon: "↻",
      attribute: "data-canvas-rotate-item",
    });
    rotateButton.setAttribute("aria-label", `Pivoter ${item.asset_name} de 90 degrés`);
    const deleteButton = createItemAction({
      label: "Supprimer",
      icon: "×",
      attribute: "data-canvas-delete-item",
      danger: true,
    });
    deleteButton.setAttribute("aria-label", `Supprimer ${item.asset_name} de la planche`);
    toolbar.append(rotateButton, deleteButton);
    canvas.append(toolbar);
    window.requestAnimationFrame(positionSelectedItemToolbar);
  }

  function refreshCalculatedState() {
    const maxBottom = state.items.reduce((max, item) => {
      const size = effectiveSize(item);
      return Math.max(max, item.y_mm + size.height);
    }, 0);
    const rawHeight = Math.max(
      maxBottom + state.margin_mm,
      state.height_mm ? (state.spacing_y_mm ?? state.spacing_mm) : 1
    );
    state.height_mm = Math.min(
      state.maximum_height_mm,
      Math.max(
        state.minimum_height_mm,
        state.height_step_mm || 1,
        Math.ceil(rawHeight / state.height_step_mm) * state.height_step_mm
      )
    );
    state.surface_sqm = round((state.width_mm * state.height_mm) / 1000000, 4);
    state.estimated_price_eur = round(state.surface_sqm * state.unit_price_eur, 2);
    state.issues = clientIssues();
  }

  function clientIssues() {
    const issues = [];
    const rects = state.items.map((item) => {
      const size = effectiveSize(item);
      return { item, x: item.x_mm, y: item.y_mm, right: item.x_mm + size.width, bottom: item.y_mm + size.height };
    });
    rects.forEach((rect) => {
      if (rect.x < 0 || rect.y < 0 || rect.right > state.width_mm || rect.bottom > state.height_mm) {
        issues.push({ code: "overflow", item_public_ids: [rect.item.public_id], message: "Le visuel déborde de la planche." });
      }
    });
    rects.forEach((first, index) => {
      rects.slice(index + 1).forEach((second) => {
        const overlaps = !(first.right <= second.x || second.right <= first.x || first.bottom <= second.y || second.bottom <= first.y);
        if (overlaps) {
          issues.push({ code: "overlap", item_public_ids: [first.item.public_id, second.item.public_id], message: "Deux visuels se chevauchent." });
        }
      });
    });
    return issues;
  }

  function render() {
    refreshCalculatedState();
    canvas.style.aspectRatio = `${state.width_mm} / ${state.height_mm}`;
    renderZoom();
    canvas.innerHTML = "";
    const issueIds = new Set(state.issues.flatMap((issue) => issue.item_public_ids));
    state.items.forEach((item) => {
      const size = effectiveSize(item);
      const node = document.createElement("button");
      node.type = "button";
      node.className = `gang-sheet-item${selectedId === item.public_id ? " is-selected" : ""}${issueIds.has(item.public_id) ? " has-issue" : ""}`;
      node.dataset.itemId = item.public_id;
      node.style.left = `${(item.x_mm / state.width_mm) * 100}%`;
      node.style.top = `${(item.y_mm / state.height_mm) * 100}%`;
      node.style.width = `${(size.width / state.width_mm) * 100}%`;
      node.style.height = `${(size.height / state.height_mm) * 100}%`;
      node.setAttribute("aria-label", `${item.asset_name}, ${round(item.width_mm / 10, 1)} par ${round(item.height_mm / 10, 1)} centimètres`);
      const image = document.createElement("img");
      image.src = item.preview_url;
      image.alt = "";
      image.draggable = false;
      image.style.transform = `translate(-50%, -50%) rotate(${item.rotation}deg)`;
      if ([90, 270].includes(Number(item.rotation))) {
        image.style.width = `${(item.width_mm / item.height_mm) * 100}%`;
        image.style.height = `${(item.height_mm / item.width_mm) * 100}%`;
      }
      const preview = document.createElement("span");
      preview.className = "gang-sheet-item__preview";
      preview.append(image);
      const label = document.createElement("span");
      label.className = "gang-sheet-item__label";
      label.textContent = `${round(item.width_mm / 10, 1)} × ${round(item.height_mm / 10, 1)} cm`;
      const handle = document.createElement("span");
      handle.className = "gang-sheet-item__resize";
      handle.dataset.resizeHandle = "";
      node.append(preview, label, handle);
      node.addEventListener("click", () => selectItem(item.public_id));
      if (canEdit) {
        node.addEventListener("pointerdown", (event) => startPointerAction(event, item));
      }
      canvas.append(node);
    });
    if (selected()) renderSelectedItemToolbar(selected());
    if (!state.items.length) {
      const empty = document.createElement("div");
      empty.className = "gang-sheet-canvas__empty";
      empty.innerHTML = "<strong>Votre planche est vide</strong><span>Choisissez un visuel dans la galerie pour démarrer.</span>";
      canvas.append(empty);
    }
    renderMetrics();
    renderAssetGallery();
    renderInspector();
    renderIssues();
    renderWorkflow();
    renderStatus();
  }

  function renderMetrics() {
    const artworkArea = state.items.reduce((total, item) => total + item.width_mm * item.height_mm, 0);
    const usage = state.width_mm * state.height_mm > 0 ? (artworkArea / (state.width_mm * state.height_mm)) * 100 : 0;
    q("[data-metric-width]").textContent = `${round(state.width_mm / 10, 1)} cm`;
    q("[data-metric-height]").textContent = `${round(state.height_mm / 10, 1)} cm`;
    q("[data-metric-items]").textContent = state.items.length;
    q("[data-metric-usage]").textContent = `${round(usage, 1)} %`;
    q("[data-metric-surface]").textContent = `${Number(state.surface_sqm).toFixed(4)} m²`;
    q("[data-metric-price]").textContent = `${Number(state.estimated_price_eur).toFixed(2)} €`;
    q("[data-canvas-format]").textContent = `${round(state.width_mm / 10, 1)} × ${round(state.height_mm / 10, 1)} cm`;
    q("[data-mobile-issue-count]").textContent = state.issues.length;
  }

  function renderAssetGallery() {
    const counts = state.items.reduce((result, item) => {
      result[item.asset_version_public_id] = (result[item.asset_version_public_id] || 0) + 1;
      return result;
    }, {});
    qa("[data-asset-usage]").forEach((node) => {
      const count = counts[node.dataset.assetUsage] || 0;
      node.textContent = count ? `${count} exemplaire${count > 1 ? "s" : ""} sur la planche` : "Pas encore utilisé";
    });
  }

  function renderInspector() {
    const item = selected();
    q("[data-empty-inspector]").hidden = Boolean(item);
    q("[data-item-inspector]").hidden = !item;
    if (!item) return;
    q("[data-selected-name]").textContent = item.asset_name;
    q("[data-input-width]").value = round(item.width_mm / 10, 2);
    q("[data-input-height]").value = round(item.height_mm / 10, 2);
    q("[data-input-x]").value = round(item.x_mm / 10, 2);
    q("[data-input-y]").value = round(item.y_mm / 10, 2);
  }

  function syncSpacingControls() {
    q("[data-spacing-x]").value = round(state.spacing_x_mm ?? state.spacing_mm, 2);
    q("[data-spacing-y]").value = round(state.spacing_y_mm ?? state.spacing_mm, 2);
  }

  function renderIssues() {
    const list = q("[data-issues-list]");
    root.dataset.hasIssues = String(state.issues.length > 0);
    if (!state.issues.length) {
      list.innerHTML = '<li class="is-ok">Aucune anomalie de placement.</li>';
      return;
    }
    const grouped = state.issues.reduce((acc, issue) => {
      acc[issue.code] = (acc[issue.code] || 0) + 1;
      return acc;
    }, {});
    list.innerHTML = Object.entries(grouped)
      .map(([code, count]) => `<li class="is-error">${count} ${code === "overflow" ? "débordement" : "chevauchement"}${count > 1 ? "s" : ""}</li>`)
      .join("");
  }

  function renderWorkflow() {
    const hasProject = root.dataset.hasProject === "true";
    const status = state.status;
    const steps = {
      files: "complete",
      composition: ["ready", "validated"].includes(status) ? "complete" : "active",
      validation:
        status === "validated"
          ? "complete"
          : ["rendering", "ready", "render_failed"].includes(status)
            ? "active"
            : "pending",
      order: hasProject ? "complete" : status === "validated" ? "active" : "pending",
    };
    const stepNumbers = { files: "1", composition: "2", validation: "3", order: "4" };
    qa("[data-workflow-step]").forEach((node) => {
      const step = node.dataset.workflowStep;
      const stepState = steps[step];
      node.classList.toggle("is-active", stepState === "active");
      node.classList.toggle("is-complete", stepState === "complete");
      if (stepState === "active") node.setAttribute("aria-current", "step");
      else node.removeAttribute("aria-current");
      node.querySelector(":scope > span").textContent =
        stepState === "complete" ? "✓" : stepNumbers[step];
    });
  }

  function renderStatus() {
    const labels = {
      draft: "Brouillon modifiable",
      rendering: "Rendu haute définition en cours…",
      ready: "Rendu prêt — validation possible",
      validated: "Planche validée pour la production",
      render_failed: state.render_error || "Le rendu a échoué",
    };
    q("[data-status-text]").textContent = busy
      ? "Enregistrement en cours…"
      : dirty
        ? "Modifications non enregistrées"
        : labels[state.status] || state.status;
    q("[data-status-detail]").textContent = dirty
      ? "Enregistrez pour sécuriser cette version."
      : state.status === "validated"
        ? "La composition est verrouillée et prête pour la commande."
        : "Toutes les modifications sont enregistrées.";
    q("[data-issue-count]").textContent = state.issues.length
      ? `${state.issues.length} anomalie${state.issues.length > 1 ? "s" : ""}`
      : "Placement valide";
    root.dataset.dirty = String(dirty);
    root.dataset.sheetStatus = state.status;
    const locked = ["rendering", "validated"].includes(state.status);
    qa(
      "[data-add-asset], [data-asset-quantity], [data-save-layout], [data-auto-place], [data-input-width], [data-input-height], [data-input-x], [data-input-y], [data-lock-ratio], [data-rotate-item], [data-duplicate-item], [data-delete-item], [data-spacing-x], [data-spacing-y], [data-apply-spacing], [data-canvas-rotate-item], [data-canvas-delete-item]"
    ).forEach((control) => {
      const assetPending = control.matches("[data-add-asset]") && control.dataset.assetReady !== "true";
      control.disabled = !canEdit || locked || assetPending;
    });
    q("[data-save-layout]").disabled = !canEdit || locked || !dirty || busy;
    q("[data-save-layout]").textContent = busy ? "Enregistrement…" : dirty ? "Enregistrer" : "Enregistré";
    q("[data-auto-place]").disabled = !canEdit || locked || state.items.length === 0 || busy;
    q("[data-apply-spacing]").disabled = !canEdit || locked || state.items.length === 0 || busy;
    q("[data-download-preview]").hidden = !["ready", "validated"].includes(state.status);
    q("[data-validate-sheet]").disabled = !canEdit || state.status !== "ready" || state.issues.length > 0;
    q("[data-render-sheet]").disabled = !canEdit || state.items.length === 0 || state.issues.length > 0 || locked;
    if (q("[data-create-order-project]")) {
      q("[data-create-order-project]").disabled = !canEdit || state.status !== "validated";
    }
  }

  function selectItem(publicId) {
    selectedId = publicId;
    render();
  }

  function startPointerAction(event, item) {
    if (state.status === "validated" || state.status === "rendering") return;
    event.preventDefault();
    selectedId = item.public_id;
    const resizing = event.target.closest("[data-resize-handle]");
    const startX = event.clientX;
    const startY = event.clientY;
    const start = { x: item.x_mm, y: item.y_mm, width: item.width_mm, height: item.height_mm };
    const move = (moveEvent) => {
      const mmPerPxX = state.width_mm / canvas.clientWidth;
      const mmPerPxY = state.height_mm / canvas.clientHeight;
      if (resizing) {
        const deltaX = (moveEvent.clientX - startX) * mmPerPxX;
        const deltaY = (moveEvent.clientY - startY) * mmPerPxY;
        resizeItemFromPointer(item, {
          start,
          deltaX,
          deltaY,
          lockRatio: q("[data-lock-ratio]").checked,
        });
      } else {
        item.x_mm = round(start.x + (moveEvent.clientX - startX) * mmPerPxX);
        item.y_mm = round(start.y + (moveEvent.clientY - startY) * mmPerPxY);
      }
      setDirty();
      render();
    };
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end, { once: true });
  }

  function setBusy(value) {
    busy = value;
    renderStatus();
  }

  async function request(url, options = {}) {
    setBusy(true);
    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        ...options,
        headers: {
          "X-CSRFToken": csrf,
          "X-Requested-With": "XMLHttpRequest",
          ...(options.headers || {}),
        },
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error?.message || "L’action n’a pas pu être effectuée.");
      }
      return payload;
    } finally {
      setBusy(false);
    }
  }

  async function saveLayout({ notify = true } = {}) {
    const payload = await request(root.dataset.layoutUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        revision: state.revision,
        items: state.items.map(({ public_id, x_mm, y_mm, width_mm, height_mm, rotation }) => ({ public_id, x_mm, y_mm, width_mm, height_mm, rotation })),
      }),
    });
    state.revision = payload.revision;
    state.height_mm = payload.height_mm;
    state.surface_sqm = payload.surface_sqm;
    state.estimated_price_eur = payload.estimated_price_eur;
    state.issues = payload.issues;
    state.status = "draft";
    setDirty(false);
    render();
    if (notify) window.preniumToast?.("Brouillon enregistré.", "success");
  }

  async function reloadState() {
    const payload = await request(root.dataset.stateUrl);
    state = payload.sheet;
    setDirty(false);
    if (!state.items.some((item) => item.public_id === selectedId)) selectedId = null;
    syncSpacingControls();
    render();
  }

  async function runAction(action, { saveFirst = false, body = null } = {}) {
    try {
      if (saveFirst) await saveLayout({ notify: false });
      const url = root.dataset.actionUrlTemplate.replace("ACTION", action);
      const payload = await request(url, { method: "POST", body });
      window.preniumToast?.(payload.message, "success");
      if (payload.redirect_url) {
        window.location.assign(payload.redirect_url);
        return;
      }
      await reloadState();
      if (action === "render") startPolling();
    } catch (error) {
      window.preniumToast?.(error.message, "error");
    }
  }

  const cropConfigurator = q("[data-b2b-configurator]");
  const cropFileInput = q("[data-configurator-file]");
  const cropManifestInput = q("[data-crop-manifest]");
  const cropManualButton = q("[data-crop-manual]");
  const cropAutoButton = q("[data-crop-auto]");
  const cropResetButton = q("[data-crop-reset]");
  const cropStatus = q("[data-crop-status]");
  const cropFileNav = q("[data-crop-file-nav]");
  const cropFileLabel = q("[data-crop-file-label]");
  const cropHelp = q("[data-crop-help]");
  const cropMinimum = 0.02;
  let cropFileIndex = 0;
  let cropAvailable = false;
  let cropBoxes = [];
  let cropModes = [];
  let cropAutoBasis = [];
  let cropAutoRun = 0;

  const fullCrop = () => ({ x: 0, y: 0, width: 1, height: 1 });
  const normalizedCrop = (crop) => ({
    x: round(crop.x, 6),
    y: round(crop.y, 6),
    width: round(crop.width, 6),
    height: round(crop.height, 6),
  });
  const cropIsFull = (crop) => (
    crop.x === 0 && crop.y === 0 && crop.width === 1 && crop.height === 1
  );
  const currentCrop = () => cropBoxes[cropFileIndex] || fullCrop();
  const currentCropMode = () => cropModes[cropFileIndex] || "manual";

  function syncCropManifest() {
    if (!(cropManifestInput instanceof HTMLInputElement)) return;
    cropManifestInput.value = JSON.stringify(
      cropBoxes.map((crop, index) => ({
        index,
        mode: cropModes[index] || "manual",
        ...normalizedCrop(crop),
      }))
    );
  }

  function activeCropMedia() {
    return cropConfigurator?.querySelector(
      "[data-configurator-preview]:not([hidden]), [data-configurator-document-preview]:not([hidden])"
    );
  }

  function activeCropElement() {
    const media = activeCropMedia();
    return media?.closest("[data-configurator-bounds]")?.querySelector("[data-gang-crop-box]") || null;
  }

  function median(values) {
    if (!values.length) return 255;
    values.sort((left, right) => left - right);
    const middle = Math.floor(values.length / 2);
    return values.length % 2 ? values[middle] : Math.round((values[middle - 1] + values[middle]) / 2);
  }

  function boundedAutoInterval(start, end) {
    let boundedStart = Math.max(0, Math.min(1, start));
    let boundedEnd = Math.max(0, Math.min(1, end));
    if (boundedEnd - boundedStart >= cropMinimum) return [boundedStart, boundedEnd];
    const center = (boundedStart + boundedEnd) / 2;
    boundedStart = Math.max(0, center - cropMinimum / 2);
    boundedEnd = Math.min(1, boundedStart + cropMinimum);
    boundedStart = Math.max(0, boundedEnd - cropMinimum);
    return [boundedStart, boundedEnd];
  }

  function detectPreviewAutoCrop(media) {
    const sourceWidth = media instanceof HTMLImageElement ? media.naturalWidth : media.width;
    const sourceHeight = media instanceof HTMLImageElement ? media.naturalHeight : media.height;
    if (!sourceWidth || !sourceHeight) return fullCrop();
    const maxSide = 900;
    const scale = Math.min(1, maxSide / Math.max(sourceWidth, sourceHeight));
    const width = Math.max(1, Math.round(sourceWidth * scale));
    const height = Math.max(1, Math.round(sourceHeight * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { alpha: true, willReadFrequently: true });
    if (context === null) return fullCrop();
    context.clearRect(0, 0, width, height);
    context.drawImage(media, 0, 0, width, height);
    const pixels = context.getImageData(0, 0, width, height).data;
    let hasTransparency = false;
    for (let offset = 3; offset < pixels.length; offset += 4) {
      if (pixels[offset] < 250) {
        hasTransparency = true;
        break;
      }
    }

    const borderChannels = [[], [], []];
    if (!hasTransparency) {
      const samplePixel = (x, y) => {
        const offset = (y * width + x) * 4;
        borderChannels[0].push(pixels[offset]);
        borderChannels[1].push(pixels[offset + 1]);
        borderChannels[2].push(pixels[offset + 2]);
      };
      for (let x = 0; x < width; x += 1) {
        samplePixel(x, 0);
        if (height > 1) samplePixel(x, height - 1);
      }
      for (let y = 1; y < height - 1; y += 1) {
        samplePixel(0, y);
        if (width > 1) samplePixel(width - 1, y);
      }
    }
    const background = borderChannels.map(median);
    let left = width;
    let top = height;
    let right = -1;
    let bottom = -1;
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const offset = (y * width + x) * 4;
        const visible = hasTransparency
          ? pixels[offset + 3] > 3
          : Math.max(
            Math.abs(pixels[offset] - background[0]),
            Math.abs(pixels[offset + 1] - background[1]),
            Math.abs(pixels[offset + 2] - background[2])
          ) > 18;
        if (!visible) continue;
        left = Math.min(left, x);
        top = Math.min(top, y);
        right = Math.max(right, x + 1);
        bottom = Math.max(bottom, y + 1);
      }
    }
    if (right < left || bottom < top) return fullCrop();
    const padding = 2;
    const [x0, x1] = boundedAutoInterval(
      Math.max(0, left - padding) / width,
      Math.min(width, right + padding) / width
    );
    const [y0, y1] = boundedAutoInterval(
      Math.max(0, top - padding) / height,
      Math.min(height, bottom + padding) / height
    );
    return normalizedCrop({ x: x0, y: y0, width: x1 - x0, height: y1 - y0 });
  }

  function renderCropBox() {
    qa("[data-gang-crop-box]").forEach((node) => { node.hidden = true; });
    const crop = currentCrop();
    const node = activeCropElement();
    if (!(node instanceof HTMLElement) || !cropAvailable || cropIsFull(crop)) return;
    node.hidden = false;
    node.style.left = `${crop.x * 100}%`;
    node.style.top = `${crop.y * 100}%`;
    node.style.width = `${crop.width * 100}%`;
    node.style.height = `${crop.height * 100}%`;
  }

  function renderCropControls() {
    const files = Array.from(cropFileInput?.files || []);
    const crop = currentCrop();
    const mode = currentCropMode();
    const hasFile = Boolean(files[cropFileIndex]);
    if (cropFileNav instanceof HTMLElement) cropFileNav.hidden = files.length < 2;
    if (cropFileLabel instanceof HTMLElement && files[cropFileIndex]) {
      cropFileLabel.textContent = `${cropFileIndex + 1}/${files.length} · ${files[cropFileIndex].name}`;
    }
    if (cropManualButton instanceof HTMLButtonElement) {
      cropManualButton.disabled = !cropAvailable;
      cropManualButton.classList.toggle("is-active", mode === "manual");
      cropManualButton.setAttribute("aria-pressed", String(mode === "manual"));
    }
    if (cropAutoButton instanceof HTMLButtonElement) {
      cropAutoButton.disabled = !hasFile;
      cropAutoButton.classList.toggle("is-active", mode === "auto");
      cropAutoButton.setAttribute("aria-pressed", String(mode === "auto"));
    }
    if (cropResetButton instanceof HTMLButtonElement) {
      cropResetButton.disabled = !hasFile || (mode === "manual" && cropIsFull(crop));
    }
    if (cropStatus instanceof HTMLElement) {
      const dimensions = cropIsFull(crop)
        ? "visuel complet conservé"
        : `${Math.round(crop.width * 100)} % × ${Math.round(crop.height * 100)} % conservés`;
      cropStatus.textContent = mode === "auto"
        ? `Auto · ${cropAutoBasis[cropFileIndex] || dimensions}`
        : `Manuel · ${dimensions}`;
    }
    if (cropHelp instanceof HTMLElement) {
      if (mode === "auto") {
        cropHelp.textContent = cropAvailable
          ? "Auto détecte les pixels visibles dans l’aperçu ; le serveur confirme les objets vectoriels, raster ou mixtes depuis l’original."
          : "Auto sera calculé par le serveur depuis le fichier original lors de l’import.";
      } else {
        cropHelp.textContent = cropAvailable
          ? "Déplacez le cadre ou ses poignées. Toute modification d’une proposition Auto repasse en Manuel."
          : "Le mode Manuel nécessite un aperçu interactif de ce format.";
      }
    }
    renderCropBox();
  }

  function updateCurrentCrop(nextCrop, { manualOverride = false } = {}) {
    if (manualOverride) {
      cropModes[cropFileIndex] = "manual";
      cropAutoBasis[cropFileIndex] = "";
    }
    cropBoxes[cropFileIndex] = normalizedCrop(nextCrop);
    syncCropManifest();
    renderCropControls();
  }

  async function applyAutoCrop() {
    const run = ++cropAutoRun;
    cropModes[cropFileIndex] = "auto";
    cropAutoBasis[cropFileIndex] = cropAvailable
      ? "analyse du contenu en cours…"
      : "calcul sécurisé à l’import";
    syncCropManifest();
    renderCropControls();
    if (!cropAvailable) return;
    await new Promise((resolve) => requestAnimationFrame(resolve));
    const media = activeCropMedia();
    if (!(media instanceof HTMLImageElement || media instanceof HTMLCanvasElement)) return;
    const detectedCrop = detectPreviewAutoCrop(media);
    if (run !== cropAutoRun || currentCropMode() !== "auto") return;
    cropAutoBasis[cropFileIndex] = media instanceof HTMLCanvasElement
      ? "illustration + pixels détectés"
      : "pixels visibles détectés";
    updateCurrentCrop(detectedCrop);
    activeCropElement()?.focus();
  }

  function requestCropFilePreview(index) {
    const files = Array.from(cropFileInput?.files || []);
    if (!files.length) return;
    cropAutoRun += 1;
    cropFileIndex = (index + files.length) % files.length;
    cropAvailable = false;
    renderCropControls();
    cropConfigurator?.dispatchEvent(
      new CustomEvent("b2b:preview-file-request", {
        bubbles: true,
        detail: { file: files[cropFileIndex] },
      })
    );
  }

  function startCropPointerAction(event, cropNode) {
    if (!cropAvailable || event.button !== 0) return;
    const bounds = cropNode.closest("[data-configurator-bounds]");
    if (!(bounds instanceof HTMLElement)) return;
    event.preventDefault();
    const startRect = bounds.getBoundingClientRect();
    const startX = event.clientX;
    const startY = event.clientY;
    const start = { ...currentCrop() };
    const handle = event.target.closest("[data-crop-handle]")?.dataset.cropHandle || "move";
    cropNode.setPointerCapture?.(event.pointerId);

    const move = (moveEvent) => {
      const dx = (moveEvent.clientX - startX) / Math.max(startRect.width, 1);
      const dy = (moveEvent.clientY - startY) / Math.max(startRect.height, 1);
      let next = { ...start };
      if (handle === "move") {
        next.x = Math.min(1 - start.width, Math.max(0, start.x + dx));
        next.y = Math.min(1 - start.height, Math.max(0, start.y + dy));
      } else {
        if (handle.includes("w")) {
          const right = start.x + start.width;
          next.x = Math.min(right - cropMinimum, Math.max(0, start.x + dx));
          next.width = right - next.x;
        }
        if (handle.includes("e")) {
          next.width = Math.min(1 - start.x, Math.max(cropMinimum, start.width + dx));
        }
        if (handle.includes("n")) {
          const bottom = start.y + start.height;
          next.y = Math.min(bottom - cropMinimum, Math.max(0, start.y + dy));
          next.height = bottom - next.y;
        }
        if (handle.includes("s")) {
          next.height = Math.min(1 - start.y, Math.max(cropMinimum, start.height + dy));
        }
      }
      updateCurrentCrop(next, { manualOverride: true });
    };
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end, { once: true });
  }

  cropFileInput?.addEventListener("change", () => {
    cropAutoRun += 1;
    cropFileIndex = 0;
    cropBoxes = Array.from(cropFileInput.files || [], () => fullCrop());
    cropModes = Array.from(cropFileInput.files || [], () => "manual");
    cropAutoBasis = Array.from(cropFileInput.files || [], () => "");
    cropAvailable = false;
    syncCropManifest();
    renderCropControls();
  });
  cropConfigurator?.addEventListener("b2b:preview-ready", (event) => {
    const currentFile = cropFileInput?.files?.[cropFileIndex];
    if (event.detail?.file !== currentFile) return;
    cropAvailable = true;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      renderCropControls();
      if (currentCropMode() === "auto") applyAutoCrop();
    }));
  });
  cropConfigurator?.addEventListener("b2b:preview-unavailable", (event) => {
    const currentFile = cropFileInput?.files?.[cropFileIndex];
    if (event.detail?.file !== currentFile) return;
    cropAvailable = false;
    renderCropControls();
  });
  cropManualButton?.addEventListener("click", () => {
    cropModes[cropFileIndex] = "manual";
    cropAutoBasis[cropFileIndex] = "";
    const crop = currentCrop();
    updateCurrentCrop(cropIsFull(crop) ? { x: 0.05, y: 0.05, width: 0.9, height: 0.9 } : crop);
    activeCropElement()?.focus();
  });
  cropAutoButton?.addEventListener("click", applyAutoCrop);
  cropResetButton?.addEventListener("click", () => updateCurrentCrop(fullCrop(), { manualOverride: true }));
  q("[data-crop-file-previous]")?.addEventListener("click", () => requestCropFilePreview(cropFileIndex - 1));
  q("[data-crop-file-next]")?.addEventListener("click", () => requestCropFilePreview(cropFileIndex + 1));
  qa("[data-gang-crop-box]").forEach((node) => {
    node.addEventListener("pointerdown", (event) => startCropPointerAction(event, node));
    node.addEventListener("keydown", (event) => {
      const deltas = {
        ArrowLeft: [-0.01, 0],
        ArrowRight: [0.01, 0],
        ArrowUp: [0, -0.01],
        ArrowDown: [0, 0.01],
      };
      if (!deltas[event.key]) return;
      event.preventDefault();
      const [dx, dy] = deltas[event.key];
      const crop = currentCrop();
      updateCurrentCrop({
        ...crop,
        x: Math.min(1 - crop.width, Math.max(0, crop.x + dx)),
        y: Math.min(1 - crop.height, Math.max(0, crop.y + dy)),
      }, { manualOverride: true });
      activeCropElement()?.focus();
    });
  });

  function startPolling() {
    window.clearTimeout(pollTimer);
    const poll = async () => {
      try {
        await reloadState();
        if (state.status === "rendering") pollTimer = window.setTimeout(poll, 2000);
        else if (state.status === "ready") window.preniumToast?.("Rendu HD terminé. L’aperçu est disponible.", "success");
        else if (state.status === "render_failed") window.preniumToast?.("Le rendu HD a échoué.", "error");
      } catch (error) {
        pollTimer = window.setTimeout(poll, 4000);
      }
    };
    pollTimer = window.setTimeout(poll, 1500);
  }

  root.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-add-asset]");
    if (!button || button.disabled) return;
    const card = button.closest("[data-asset-card]");
    const quantity = Math.max(1, Math.min(200, Number(card.querySelector("[data-asset-quantity]").value) || 1));
    const body = new FormData();
    body.append("asset_version_public_id", button.dataset.addAsset);
    body.append("quantity", quantity);
    body.append("auto_place", "1");
    try {
      if (state.items.length) await saveLayout({ notify: false });
      const payload = await request(root.dataset.addUrl, { method: "POST", body });
      await reloadState();
      window.preniumToast?.(`${payload.created_count} exemplaire${payload.created_count > 1 ? "s" : ""} ajouté${payload.created_count > 1 ? "s" : ""} et placé${payload.created_count > 1 ? "s" : ""}.`, "success");
    } catch (error) { window.preniumToast?.(error.message, "error"); }
  });

  function filterAssetGallery() {
    const term = q("[data-asset-search]").value.trim().toLocaleLowerCase("fr");
    qa("[data-asset-card]").forEach((card) => {
      card.hidden = Boolean(term) && !card.dataset.assetName.includes(term);
    });
  }

  q("[data-asset-search]").addEventListener("input", filterAssetGallery);

  qa("[data-mobile-panel-tab]").forEach((tab) => {
    tab.addEventListener("click", () => setMobilePanel(tab.dataset.mobilePanelTab));
  });

  q("[data-zoom-out]").addEventListener("click", () => {
    zoom = Math.max(0.5, round(zoom - 0.25, 2));
    renderZoom();
  });
  q("[data-zoom-reset]").addEventListener("click", () => {
    zoom = 1;
    renderZoom();
  });
  q("[data-zoom-in]").addEventListener("click", () => {
    zoom = Math.min(1.5, round(zoom + 0.25, 2));
    renderZoom();
  });

  root.addEventListener("htmx:afterSwap", (event) => {
    if (!event.target.matches("[data-asset-list]")) return;
    renderAssetGallery();
    renderStatus();
    filterAssetGallery();
    const isPending = qPendingGallery();
    if (galleryWasPending && !isPending) {
      window.preniumToast?.("Analyse terminée. Les visuels prêts sont disponibles.", "success");
    }
    galleryWasPending = isPending;
  });

  function spacingRequestBody() {
    const spacingX = Math.max(0, Math.min(100, Number(q("[data-spacing-x]").value) || 0));
    const spacingY = Math.max(0, Math.min(100, Number(q("[data-spacing-y]").value) || 0));
    q("[data-spacing-x]").value = round(spacingX, 2);
    q("[data-spacing-y]").value = round(spacingY, 2);
    const body = new FormData();
    body.append("spacing_x_mm", spacingX);
    body.append("spacing_y_mm", spacingY);
    return body;
  }

  function autoPlaceWithSpacing() {
    return runAction("auto-place", { saveFirst: true, body: spacingRequestBody() });
  }

  q("[data-save-layout]").addEventListener("click", () => saveLayout().catch((error) => window.preniumToast?.(error.message, "error")));
  q("[data-auto-place]").addEventListener("click", autoPlaceWithSpacing);
  q("[data-apply-spacing]").addEventListener("click", autoPlaceWithSpacing);
  q("[data-render-sheet]").addEventListener("click", () => runAction("render", { saveFirst: true }));
  q("[data-validate-sheet]").addEventListener("click", () => runAction("validate"));
  q("[data-create-order-project]")?.addEventListener("click", () => runAction("create-order-project"));
  function rotateSelected() {
    const item = selected();
    if (item) {
      item.rotation = (Number(item.rotation) + 90) % 360;
      setDirty();
      render();
    }
  }
  q("[data-rotate-item]").addEventListener("click", rotateSelected);
  async function duplicateSelected() {
    const item = selected(); if (!item) return;
    try {
      await saveLayout({ notify: false });
      const url = root.dataset.itemUrlTemplate.replace("00000000-0000-0000-0000-000000000000", item.public_id).replace("ACTION", "duplicate");
      await request(url, { method: "POST" }); await reloadState(); window.preniumToast?.("Occurrence dupliquée.", "success");
    } catch (error) { window.preniumToast?.(error.message, "error"); }
  }
  q("[data-duplicate-item]").addEventListener("click", duplicateSelected);

  async function deleteSelected() {
    const item = selected(); if (!item) return;
    try {
      if (dirty) await saveLayout({ notify: false });
      const url = root.dataset.itemUrlTemplate.replace("00000000-0000-0000-0000-000000000000", item.public_id).replace("ACTION", "delete");
      await request(url, { method: "POST" }); selectedId = null; await reloadState(); window.preniumToast?.("Occurrence supprimée.", "success");
    } catch (error) { window.preniumToast?.(error.message, "error"); }
  }
  q("[data-delete-item]").addEventListener("click", deleteSelected);

  root.addEventListener("click", (event) => {
    const rotateButton = event.target.closest("[data-canvas-rotate-item]");
    if (rotateButton && !rotateButton.disabled) {
      rotateSelected();
      return;
    }
    const deleteButton = event.target.closest("[data-canvas-delete-item]");
    if (deleteButton && !deleteButton.disabled) deleteSelected();
  });

  [["[data-input-width]", "width_mm"], ["[data-input-height]", "height_mm"], ["[data-input-x]", "x_mm"], ["[data-input-y]", "y_mm"]].forEach(([selector, key]) => {
    q(selector).addEventListener("change", (event) => {
      const item = selected(); if (!item) return;
      const next = round(Number(event.target.value) * 10);
      if (key === "width_mm" && q("[data-lock-ratio]").checked) {
        const ratio = item.height_mm / item.width_mm;
        item.width_mm = next;
        item.height_mm = round(next * ratio);
      } else if (key === "height_mm" && q("[data-lock-ratio]").checked) {
        const ratio = item.width_mm / item.height_mm;
        item.height_mm = next;
        item.width_mm = round(next * ratio);
      } else {
        item[key] = next;
      }
      setDirty();
      render();
    });
  });

  window.addEventListener("keydown", (event) => {
    if (event.target.closest("input, textarea, select")) return;
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      saveLayout().catch((error) => window.preniumToast?.(error.message, "error"));
    } else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "d") {
      event.preventDefault();
      duplicateSelected();
    } else if (event.key.toLowerCase() === "r" && selected()) {
      rotateSelected();
    } else if ((event.key === "Delete" || event.key === "Backspace") && selected()) {
      event.preventDefault();
      deleteSelected();
    } else if (event.key === "Escape") {
      selectedId = null;
      render();
    }
  });

  window.addEventListener("beforeunload", (event) => {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
  window.addEventListener("resize", renderZoom);
  syncSpacingControls();
  setMobilePanel("canvas");
  render();
  if (state.status === "rendering") startPolling();
}
