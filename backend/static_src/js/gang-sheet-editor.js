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

  function refreshCalculatedState() {
    const maxBottom = state.items.reduce((max, item) => {
      const size = effectiveSize(item);
      return Math.max(max, item.y_mm + size.height);
    }, 0);
    const rawHeight = Math.max(maxBottom + state.margin_mm, state.height_mm ? state.spacing_mm : 1);
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
      const label = document.createElement("span");
      label.textContent = `${round(item.width_mm / 10, 1)} × ${round(item.height_mm / 10, 1)} cm`;
      const handle = document.createElement("span");
      handle.className = "gang-sheet-item__resize";
      handle.dataset.resizeHandle = "";
      node.append(image, label, handle);
      node.addEventListener("click", () => selectItem(item.public_id));
      if (canEdit) {
        node.addEventListener("pointerdown", (event) => startPointerAction(event, item));
      }
      canvas.append(node);
    });
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
    q("[data-grid-spacing-x]").value = round(state.spacing_mm, 2);
    q("[data-grid-spacing-y]").value = round(state.spacing_mm, 2);
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
      "[data-add-asset], [data-asset-quantity], [data-save-layout], [data-auto-place], [data-input-width], [data-input-height], [data-input-x], [data-input-y], [data-lock-ratio], [data-rotate-item], [data-duplicate-item], [data-delete-item], [data-grid-rows], [data-grid-columns], [data-grid-spacing-x], [data-grid-spacing-y], [data-create-grid]"
    ).forEach((control) => {
      const assetPending = control.matches("[data-add-asset]") && control.dataset.assetReady !== "true";
      control.disabled = !canEdit || locked || assetPending;
    });
    q("[data-save-layout]").disabled = !canEdit || locked || !dirty || busy;
    q("[data-save-layout]").textContent = busy ? "Enregistrement…" : dirty ? "Enregistrer" : "Enregistré";
    q("[data-auto-place]").disabled = !canEdit || locked || state.items.length === 0 || busy;
    q("[data-create-grid]").disabled = !canEdit || locked || !selected();
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
    const ratio = start.height / start.width;
    const move = (moveEvent) => {
      const mmPerPxX = state.width_mm / canvas.clientWidth;
      const mmPerPxY = state.height_mm / canvas.clientHeight;
      if (resizing) {
        const deltaX = (moveEvent.clientX - startX) * mmPerPxX;
        const deltaY = (moveEvent.clientY - startY) * mmPerPxY;
        item.width_mm = Math.max(1, round(start.width + deltaX));
        item.height_mm = q("[data-lock-ratio]").checked
          ? Math.max(1, round(item.width_mm * ratio))
          : Math.max(1, round(start.height + deltaY));
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
    render();
  }

  async function runAction(action, { saveFirst = false } = {}) {
    try {
      if (saveFirst) await saveLayout({ notify: false });
      const url = root.dataset.actionUrlTemplate.replace("ACTION", action);
      const payload = await request(url, { method: "POST" });
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

  q("[data-save-layout]").addEventListener("click", () => saveLayout().catch((error) => window.preniumToast?.(error.message, "error")));
  q("[data-auto-place]").addEventListener("click", () => runAction("auto-place", { saveFirst: true }));
  q("[data-render-sheet]").addEventListener("click", () => runAction("render", { saveFirst: true }));
  q("[data-validate-sheet]").addEventListener("click", () => runAction("validate"));
  q("[data-create-order-project]")?.addEventListener("click", () => runAction("create-order-project"));
  q("[data-rotate-item]").addEventListener("click", () => {
    const item = selected();
    if (item) {
      item.rotation = (Number(item.rotation) + 90) % 360;
      setDirty();
      render();
    }
  });
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

  q("[data-create-grid]").addEventListener("click", async () => {
    const item = selected(); if (!item) return;
    const rows = Number(q("[data-grid-rows]").value) || 1;
    const columns = Number(q("[data-grid-columns]").value) || 1;
    const body = new FormData();
    body.append("rows", rows);
    body.append("columns", columns);
    body.append("spacing_x_mm", Number(q("[data-grid-spacing-x]").value) || 0);
    body.append("spacing_y_mm", Number(q("[data-grid-spacing-y]").value) || 0);
    try {
      await saveLayout({ notify: false });
      const url = root.dataset.itemUrlTemplate.replace("00000000-0000-0000-0000-000000000000", item.public_id).replace("ACTION", "grid");
      await request(url, { method: "POST", body });
      await reloadState();
      window.preniumToast?.(`Grille ${rows} × ${columns} créée.`, "success");
    } catch (error) { window.preniumToast?.(error.message, "error"); }
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
      selected().rotation = (Number(selected().rotation) + 90) % 360;
      setDirty();
      render();
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
  setMobilePanel("canvas");
  render();
  if (state.status === "rendering") startPolling();
}
