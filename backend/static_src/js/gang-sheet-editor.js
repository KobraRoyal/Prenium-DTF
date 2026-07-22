const root = document.querySelector("[data-gang-sheet-editor]");

if (root) {
  const initialNode = document.getElementById("gang-sheet-initial-state");
  let state = JSON.parse(initialNode.textContent);
  let selectedId = null;
  let selectedIds = new Set();
  let alignmentReference = "selection";
  let suppressNextItemClick = false;
  let suppressNextCanvasClick = false;
  let snapEnabled = true;
  let snapGuides = [];
  let touchMultiSelect = false;
  let undoStack = [];
  let redoStack = [];
  let savedLayoutSignature = "";
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
  const canvasClearZone = q("[data-canvas-clear-zone]");
  const round = (value, digits = 2) => Number(Number(value).toFixed(digits));
  const selected = () => state.items.find((item) => item.public_id === selectedId && selectedIds.has(item.public_id));
  const selectedItems = () => state.items.filter((item) => selectedIds.has(item.public_id));
  const effectiveAlignmentReference = () => selectedIds.size > 1 ? alignmentReference : "sheet";
  const HISTORY_LIMIT = 40;

  function layoutSnapshot() {
    return state.items.map(({ public_id, x_mm, y_mm, width_mm, height_mm, rotation }) => ({
      public_id,
      x_mm,
      y_mm,
      width_mm,
      height_mm,
      rotation,
    }));
  }

  function layoutSignature(snapshot = layoutSnapshot()) {
    return JSON.stringify(snapshot);
  }

  savedLayoutSignature = layoutSignature();

  function syncLayoutDirtyState() {
    setDirty(layoutSignature() !== savedLayoutSignature);
  }

  function resetLayoutHistory() {
    undoStack = [];
    redoStack = [];
    renderHistoryControls();
  }

  function commitLayoutMutation(before) {
    if (!before || layoutSignature(before) === layoutSignature()) return false;
    undoStack.push(before);
    if (undoStack.length > HISTORY_LIMIT) undoStack.shift();
    redoStack = [];
    syncLayoutDirtyState();
    renderHistoryControls();
    return true;
  }

  function restoreLayoutSnapshot(snapshot) {
    const valuesById = new Map(snapshot.map((item) => [item.public_id, item]));
    state.items.forEach((item) => {
      const saved = valuesById.get(item.public_id);
      if (!saved) return;
      item.x_mm = saved.x_mm;
      item.y_mm = saved.y_mm;
      item.width_mm = saved.width_mm;
      item.height_mm = saved.height_mm;
      item.rotation = saved.rotation;
    });
  }

  function undoLayoutMutation() {
    if (!canEdit || ["rendering", "validated"].includes(state.status) || !undoStack.length || busy) return;
    const previous = undoStack.pop();
    redoStack.push(layoutSnapshot());
    restoreLayoutSnapshot(previous);
    snapGuides = [];
    syncLayoutDirtyState();
    render();
  }

  function redoLayoutMutation() {
    if (!canEdit || ["rendering", "validated"].includes(state.status) || !redoStack.length || busy) return;
    const next = redoStack.pop();
    undoStack.push(layoutSnapshot());
    restoreLayoutSnapshot(next);
    snapGuides = [];
    syncLayoutDirtyState();
    render();
  }

  function renderHistoryControls() {
    const locked = ["rendering", "validated"].includes(state.status);
    const undo = q("[data-undo-layout]");
    const redo = q("[data-redo-layout]");
    if (undo) undo.disabled = !canEdit || locked || busy || undoStack.length === 0;
    if (redo) redo.disabled = !canEdit || locked || busy || redoStack.length === 0;
  }

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
    const itemNode = selectedIds.size === 1 && selectedId ? canvas.querySelector(`[data-item-id="${selectedId}"]`) : null;
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
      const isSelected = selectedIds.has(item.public_id);
      node.className = `gang-sheet-item${isSelected ? " is-selected" : ""}${selectedId === item.public_id ? " is-primary" : ""}${issueIds.has(item.public_id) ? " has-issue" : ""}`;
      node.dataset.itemId = item.public_id;
      node.style.left = `${(item.x_mm / state.width_mm) * 100}%`;
      node.style.top = `${(item.y_mm / state.height_mm) * 100}%`;
      node.style.width = `${(size.width / state.width_mm) * 100}%`;
      node.style.height = `${(size.height / state.height_mm) * 100}%`;
      node.setAttribute("aria-label", `${item.asset_name}, ${round(item.width_mm / 10, 1)} par ${round(item.height_mm / 10, 1)} centimètres`);
      node.setAttribute("aria-pressed", String(isSelected));
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
      node.addEventListener("click", (event) => {
        if (suppressNextItemClick) {
          suppressNextItemClick = false;
          return;
        }
        selectItem(item.public_id, { additive: touchMultiSelect || event.shiftKey || event.ctrlKey || event.metaKey });
      });
      if (canEdit) {
        node.addEventListener("pointerdown", (event) => startPointerAction(event, item));
      }
      canvas.append(node);
    });
    renderSnapGuides();
    if (selectedIds.size === 1 && selected()) renderSelectedItemToolbar(selected());
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
    const selectionCount = selectedIds.size;
    q("[data-empty-inspector]").hidden = selectionCount > 0;
    q("[data-item-inspector]").hidden = selectionCount !== 1 || !item;
    q("[data-alignment-panel]").hidden = selectionCount === 0;
    const selectionDelete = q("[data-delete-selected]");
    selectionDelete.hidden = selectionCount < 2;
    selectionDelete.textContent = selectionCount > 1
      ? `Supprimer la sélection (${selectionCount})`
      : "Supprimer la sélection";
    if (selectionCount > 0) {
      q("[data-selection-summary]").textContent = `${selectionCount} visuel${selectionCount > 1 ? "s" : ""} sélectionné${selectionCount > 1 ? "s" : ""}`;
      const reference = effectiveAlignmentReference();
      qa("[data-align-reference]").forEach((control) => {
        control.checked = control.value === reference;
      });
      q("[data-alignment-help]").textContent = reference === "selection"
        ? "Les visuels s’alignent sur le cadre global de la sélection."
        : "Les visuels s’alignent dans la zone utile de la planche en respectant ses marges.";
    }
    if (!item || selectionCount !== 1) return;
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
    list.replaceChildren();
    if (!state.issues.length) {
      const ok = document.createElement("li");
      ok.className = "is-ok";
      ok.textContent = "Aucune anomalie de placement.";
      list.append(ok);
      return;
    }
    state.issues.forEach((issue, index) => {
      const row = document.createElement("li");
      row.className = "is-error";
      const focus = document.createElement("button");
      focus.type = "button";
      focus.dataset.issueFocus = String(index);
      focus.textContent = issue.message || (issue.code === "overflow" ? "Un visuel déborde de la zone utile." : "Des visuels se chevauchent.");
      focus.setAttribute("aria-label", `${focus.textContent} Sélectionner sur la planche.`);
      row.append(focus);
      if (issue.code === "overflow" && canEdit) {
        const fix = document.createElement("button");
        fix.type = "button";
        fix.className = "gang-issue-fix";
        fix.dataset.issueFix = String(index);
        fix.textContent = "Ramener dans la planche";
        row.append(fix);
      }
      list.append(row);
    });
  }

  function focusIssue(index) {
    const issue = state.issues[Number(index)];
    if (!issue) return;
    const availableIds = new Set(state.items.map((item) => item.public_id));
    selectedIds = new Set((issue.item_public_ids || []).filter((publicId) => availableIds.has(publicId)));
    selectedId = Array.from(selectedIds)[0] || null;
    if (window.matchMedia("(max-width: 980px)").matches) setMobilePanel("canvas");
    render();
    window.requestAnimationFrame(() => {
      canvas.querySelector(`[data-item-id="${selectedId}"]`)?.focus({ preventScroll: false });
    });
  }

  function fixOverflowIssue(index) {
    const issue = state.issues[Number(index)];
    if (!issue || issue.code !== "overflow" || !canEdit || busy || ["rendering", "validated"].includes(state.status)) return;
    const before = layoutSnapshot();
    const affectedItems = (issue.item_public_ids || [])
      .map((publicId) => state.items.find((candidate) => candidate.public_id === publicId))
      .filter(Boolean);
    const cannotFit = affectedItems.some((item) => {
      const size = effectiveSize(item);
      return size.width > state.width_mm || size.height > state.height_mm;
    });
    if (cannotFit) {
      window.preniumToast?.("Ce visuel est plus grand que la planche. Réduisez ses dimensions avant de le replacer.", "error");
      return;
    }
    affectedItems.forEach((item) => {
      const size = effectiveSize(item);
      item.x_mm = round(Math.max(0, Math.min(item.x_mm, state.width_mm - size.width)));
      item.y_mm = round(Math.max(0, Math.min(item.y_mm, state.height_mm - size.height)));
    });
    if (!commitLayoutMutation(before)) return;
    focusIssue(index);
    window.preniumToast?.("Le visuel a été ramené dans la planche.", "success");
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
      "[data-add-asset], [data-asset-quantity], [data-save-layout], [data-auto-place], [data-input-width], [data-input-height], [data-input-x], [data-input-y], [data-lock-ratio], [data-rotate-item], [data-duplicate-item], [data-delete-item], [data-delete-selected], [data-align], [data-align-reference], [data-distribute], [data-selection-gap], [data-apply-selection-gap], [data-spacing-x], [data-spacing-y], [data-apply-spacing], [data-canvas-rotate-item], [data-canvas-delete-item], [data-snap-toggle], [data-select-all], [data-touch-multiselect], [data-issue-fix]"
    ).forEach((control) => {
      const assetPending = control.matches("[data-add-asset]") && control.dataset.assetReady !== "true";
      control.disabled = !canEdit || locked || assetPending;
    });
    qa("[data-issue-focus]").forEach((control) => {
      control.disabled = busy;
    });
    q("[data-save-layout]").disabled = !canEdit || locked || !dirty || busy;
    q("[data-save-layout]").textContent = busy ? "Enregistrement…" : dirty ? "Enregistrer" : "Enregistré";
    q("[data-auto-place]").disabled = !canEdit || locked || state.items.length === 0 || busy;
    q("[data-apply-spacing]").disabled = !canEdit || locked || state.items.length === 0 || busy;
    qa("[data-align]").forEach((control) => {
      control.disabled = !canEdit || locked || selectedIds.size === 0 || busy;
    });
    qa("[data-align-reference]").forEach((control) => {
      control.disabled = !canEdit || locked || busy || (control.value === "selection" && selectedIds.size < 2);
    });
    qa("[data-distribute]").forEach((control) => {
      control.disabled = !canEdit || locked || busy || selectedIds.size < 3;
    });
    qa("[data-apply-selection-gap]").forEach((control) => {
      control.disabled = !canEdit || locked || busy || selectedIds.size < 2;
    });
    q("[data-selection-gap]").disabled = !canEdit || locked || busy || selectedIds.size < 2;
    q("[data-delete-selected]").disabled = !canEdit || locked || busy || selectedIds.size < 2;
    q("[data-select-all]").disabled = !canEdit || locked || busy || state.items.length === 0;
    q("[data-snap-toggle]").setAttribute("aria-pressed", String(snapEnabled));
    q("[data-touch-multiselect]").setAttribute("aria-pressed", String(touchMultiSelect));
    renderHistoryControls();
    q("[data-download-preview]").hidden = !["ready", "validated"].includes(state.status);
    q("[data-validate-sheet]").disabled = !canEdit || state.status !== "ready" || state.issues.length > 0;
    q("[data-render-sheet]").disabled = !canEdit || state.items.length === 0 || state.issues.length > 0 || locked;
    if (q("[data-create-order-project]")) {
      q("[data-create-order-project]").disabled = !canEdit || state.status !== "validated";
    }
  }

  function clearSelection() {
    selectedId = null;
    selectedIds.clear();
  }

  function selectItem(publicId, { additive = false } = {}) {
    if (!additive) {
      selectedIds = new Set([publicId]);
      selectedId = publicId;
      render();
      return;
    }
    if (selectedIds.has(publicId)) {
      selectedIds.delete(publicId);
      if (selectedId === publicId) selectedId = Array.from(selectedIds).at(-1) || null;
    } else {
      selectedIds.add(publicId);
      selectedId = publicId;
    }
    render();
  }

  function selectAllItems() {
    selectedIds = new Set(state.items.map((item) => item.public_id));
    selectedId = state.items.at(-1)?.public_id || null;
    render();
  }

  function toggleTouchMultiSelect() {
    touchMultiSelect = !touchMultiSelect;
    const control = q("[data-touch-multiselect]");
    control?.classList.toggle("is-active", touchMultiSelect);
    control?.setAttribute("aria-pressed", String(touchMultiSelect));
    root.dataset.touchMultiSelect = String(touchMultiSelect);
    renderStatus();
  }

  function renderSnapGuides() {
    snapGuides.forEach((guide) => {
      const node = document.createElement("span");
      node.className = `gang-snap-guide gang-snap-guide--${guide.axis}`;
      node.dataset.snapGuide = guide.axis;
      node.setAttribute("aria-hidden", "true");
      if (guide.axis === "x") node.style.left = `${(guide.value / state.width_mm) * 100}%`;
      else node.style.top = `${(guide.value / state.height_mm) * 100}%`;
      canvas.append(node);
    });
  }

  function calculateSnapForMove(movingItems, movingStarts, deltaX, deltaY) {
    if (!snapEnabled || !movingItems.length) return { deltaX, deltaY, guides: [] };
    const movingIds = new Set(movingItems.map((item) => item.public_id));
    const bounds = movingItems.reduce((result, item) => {
      const start = movingStarts.get(item.public_id);
      const size = effectiveSize(item);
      return {
        left: Math.min(result.left, start.x + deltaX),
        top: Math.min(result.top, start.y + deltaY),
        right: Math.max(result.right, start.x + deltaX + size.width),
        bottom: Math.max(result.bottom, start.y + deltaY + size.height),
      };
    }, { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity });
    const margin = Math.max(0, Number(state.margin_mm) || 0);
    const xTargets = [margin, state.width_mm / 2, Math.max(margin, state.width_mm - margin)];
    const yTargets = [margin, state.height_mm / 2, Math.max(margin, state.height_mm - margin)];
    state.items.forEach((other) => {
      if (movingIds.has(other.public_id)) return;
      const size = effectiveSize(other);
      xTargets.push(other.x_mm, other.x_mm + size.width / 2, other.x_mm + size.width);
      yTargets.push(other.y_mm, other.y_mm + size.height / 2, other.y_mm + size.height);
    });
    const toleranceX = Math.max(1, Math.min(3, (state.width_mm / Math.max(canvas.clientWidth, 1)) * 7));
    const toleranceY = Math.max(1, Math.min(3, (state.height_mm / Math.max(canvas.clientHeight, 1)) * 7));
    const closest = (anchors, targets, tolerance) => {
      let best = null;
      anchors.forEach((anchor) => targets.forEach((target) => {
        const distance = target - anchor;
        if (Math.abs(distance) <= tolerance && (!best || Math.abs(distance) < Math.abs(best.distance))) {
          best = { distance, target };
        }
      }));
      return best;
    };
    const snapX = closest([bounds.left, (bounds.left + bounds.right) / 2, bounds.right], xTargets, toleranceX);
    const snapY = closest([bounds.top, (bounds.top + bounds.bottom) / 2, bounds.bottom], yTargets, toleranceY);
    return {
      deltaX: deltaX + (snapX?.distance || 0),
      deltaY: deltaY + (snapY?.distance || 0),
      guides: [
        ...(snapX ? [{ axis: "x", value: snapX.target }] : []),
        ...(snapY ? [{ axis: "y", value: snapY.target }] : []),
      ],
    };
  }

  function startRectangleSelection(event) {
    if (event.target !== canvas || event.pointerType === "touch" || event.button !== 0) return;
    event.preventDefault();
    const pointerId = event.pointerId;
    const canvasRect = canvas.getBoundingClientRect();
    const startX = Math.max(0, Math.min(canvasRect.width, event.clientX - canvasRect.left));
    const startY = Math.max(0, Math.min(canvasRect.height, event.clientY - canvasRect.top));
    const additive = event.shiftKey || event.ctrlKey || event.metaKey;
    const previousSelection = new Set(selectedIds);
    const previousSelectedId = selectedId;
    const initialSelection = additive ? new Set(selectedIds) : new Set();
    const marquee = document.createElement("span");
    let moved = false;
    marquee.className = "gang-selection-marquee";
    marquee.dataset.selectionMarquee = "";
    marquee.setAttribute("aria-hidden", "true");
    canvas.append(marquee);
    canvas.setPointerCapture?.(event.pointerId);
    const move = (moveEvent) => {
      if (moveEvent.pointerId !== pointerId) return;
      const currentX = Math.max(0, Math.min(canvasRect.width, moveEvent.clientX - canvasRect.left));
      const currentY = Math.max(0, Math.min(canvasRect.height, moveEvent.clientY - canvasRect.top));
      moved = moved || Math.abs(currentX - startX) > 2 || Math.abs(currentY - startY) > 2;
      const left = Math.min(startX, currentX);
      const top = Math.min(startY, currentY);
      const right = Math.max(startX, currentX);
      const bottom = Math.max(startY, currentY);
      marquee.style.left = `${left}px`;
      marquee.style.top = `${top}px`;
      marquee.style.width = `${right - left}px`;
      marquee.style.height = `${bottom - top}px`;
      const area = {
        left: (left / canvasRect.width) * state.width_mm,
        top: (top / canvasRect.height) * state.height_mm,
        right: (right / canvasRect.width) * state.width_mm,
        bottom: (bottom / canvasRect.height) * state.height_mm,
      };
      selectedIds = new Set(initialSelection);
      state.items.forEach((item) => {
        const size = effectiveSize(item);
        const intersects = item.x_mm < area.right
          && item.x_mm + size.width > area.left
          && item.y_mm < area.bottom
          && item.y_mm + size.height > area.top;
        if (intersects) selectedIds.add(item.public_id);
      });
      Array.from(canvas.querySelectorAll("[data-item-id]")).forEach((node) => {
        const isSelected = selectedIds.has(node.dataset.itemId);
        node.classList.toggle("is-selected", isSelected);
        node.setAttribute("aria-pressed", String(isSelected));
      });
    };
    const cleanup = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", cancel);
      if (canvas.hasPointerCapture?.(pointerId)) canvas.releasePointerCapture(pointerId);
      marquee.remove();
    };
    const end = (endEvent) => {
      if (endEvent.pointerId !== pointerId) return;
      cleanup();
      suppressNextCanvasClick = moved;
      selectedId = Array.from(selectedIds).at(-1) || null;
      render();
      if (moved) window.setTimeout(() => { suppressNextCanvasClick = false; }, 0);
    };
    const cancel = (cancelEvent) => {
      if (cancelEvent.pointerId !== pointerId) return;
      cleanup();
      selectedIds = previousSelection;
      selectedId = previousSelectedId;
      render();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", cancel);
  }

  function startPointerAction(event, item) {
    if (!canEdit || busy || state.status === "validated" || state.status === "rendering" || event.button !== 0) return;
    if (event.shiftKey || event.ctrlKey || event.metaKey) return;
    if (touchMultiSelect && event.pointerType === "touch" && !selectedIds.has(item.public_id)) return;
    event.preventDefault();
    const pointerId = event.pointerId;
    canvas.setPointerCapture?.(pointerId);
    const resizing = event.target.closest("[data-resize-handle]");
    if (!selectedIds.has(item.public_id) || resizing) {
      selectedIds = new Set([item.public_id]);
    }
    selectedId = item.public_id;
    const startX = event.clientX;
    const startY = event.clientY;
    const start = { x: item.x_mm, y: item.y_mm, width: item.width_mm, height: item.height_mm };
    const movingItems = resizing ? [item] : selectedItems();
    const movingStarts = new Map(movingItems.map((movingItem) => [movingItem.public_id, { x: movingItem.x_mm, y: movingItem.y_mm }]));
    const before = layoutSnapshot();
    const wasDirty = dirty;
    let moved = false;
    const move = (moveEvent) => {
      if (moveEvent.pointerId !== pointerId) return;
      const mmPerPxX = state.width_mm / canvas.clientWidth;
      const mmPerPxY = state.height_mm / canvas.clientHeight;
      let deltaX = (moveEvent.clientX - startX) * mmPerPxX;
      let deltaY = (moveEvent.clientY - startY) * mmPerPxY;
      moved = moved || Math.abs(moveEvent.clientX - startX) > 2 || Math.abs(moveEvent.clientY - startY) > 2;
      if (!moved) return;
      if (resizing) {
        resizeItemFromPointer(item, {
          start,
          deltaX,
          deltaY,
          lockRatio: q("[data-lock-ratio]").checked,
        });
      } else {
        const snapped = calculateSnapForMove(movingItems, movingStarts, deltaX, deltaY);
        deltaX = snapped.deltaX;
        deltaY = snapped.deltaY;
        snapGuides = snapped.guides;
        movingItems.forEach((movingItem) => {
          const movingStart = movingStarts.get(movingItem.public_id);
          movingItem.x_mm = round(movingStart.x + deltaX);
          movingItem.y_mm = round(movingStart.y + deltaY);
        });
      }
      setDirty();
      render();
    };
    const cleanup = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", cancel);
      if (canvas.hasPointerCapture?.(pointerId)) canvas.releasePointerCapture(pointerId);
    };
    const end = (endEvent) => {
      if (endEvent.pointerId !== pointerId) return;
      cleanup();
      suppressNextItemClick = moved;
      snapGuides = [];
      if (moved) {
        if (!commitLayoutMutation(before)) setDirty(wasDirty);
      } else {
        setDirty(wasDirty);
      }
      render();
      if (moved) window.setTimeout(() => { suppressNextItemClick = false; }, 0);
    };
    const cancel = (cancelEvent) => {
      if (cancelEvent.pointerId !== pointerId) return;
      cleanup();
      restoreLayoutSnapshot(before);
      suppressNextItemClick = false;
      snapGuides = [];
      setDirty(wasDirty);
      render();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", cancel);
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
    savedLayoutSignature = layoutSignature();
    setDirty(false);
    resetLayoutHistory();
    render();
    if (notify) window.preniumToast?.("Brouillon enregistré.", "success");
  }

  async function reloadState() {
    const payload = await request(root.dataset.stateUrl);
    state = payload.sheet;
    savedLayoutSignature = layoutSignature();
    setDirty(false);
    resetLayoutHistory();
    const availableIds = new Set(state.items.map((item) => item.public_id));
    selectedIds = new Set(Array.from(selectedIds).filter((publicId) => availableIds.has(publicId)));
    if (!selectedId || !selectedIds.has(selectedId)) selectedId = Array.from(selectedIds).at(-1) || null;
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
  q("[data-undo-layout]").addEventListener("click", undoLayoutMutation);
  q("[data-redo-layout]").addEventListener("click", redoLayoutMutation);
  q("[data-snap-toggle]").addEventListener("click", () => {
    snapEnabled = !snapEnabled;
    snapGuides = [];
    q("[data-snap-toggle]").classList.toggle("is-active", snapEnabled);
    q("[data-snap-toggle]").setAttribute("aria-pressed", String(snapEnabled));
  });
  q("[data-select-all]").addEventListener("click", selectAllItems);
  q("[data-touch-multiselect]").addEventListener("click", toggleTouchMultiSelect);
  canvas.addEventListener("pointerdown", startRectangleSelection);
  function clearSelectionFromCanvasBackground(event) {
    if (
      ![canvas, canvasClearZone].includes(event.target)
      || event.shiftKey
      || event.ctrlKey
      || event.metaKey
    ) return;
    if (suppressNextCanvasClick) {
      suppressNextCanvasClick = false;
      return;
    }
    if (!selectedIds.size) return;
    clearSelection();
    render();
  }
  canvasClearZone.addEventListener("click", clearSelectionFromCanvasBackground);

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

  function selectionBounds(items) {
    return items.reduce((bounds, item) => {
      const size = effectiveSize(item);
      return {
        left: Math.min(bounds.left, item.x_mm),
        top: Math.min(bounds.top, item.y_mm),
        right: Math.max(bounds.right, item.x_mm + size.width),
        bottom: Math.max(bounds.bottom, item.y_mm + size.height),
      };
    }, { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity });
  }

  function alignmentBounds(items) {
    if (effectiveAlignmentReference() === "selection") return selectionBounds(items);
    const margin = Math.max(0, Number(state.margin_mm) || 0);
    return {
      left: margin,
      top: margin,
      right: Math.max(margin, state.width_mm - margin),
      bottom: Math.max(margin, state.height_mm - margin),
    };
  }

  function alignSelectedItems(direction) {
    const items = selectedItems();
    if (!items.length || !canEdit || ["rendering", "validated"].includes(state.status)) return;
    const before = layoutSnapshot();
    const bounds = alignmentBounds(items);
    const centerX = (bounds.left + bounds.right) / 2;
    const centerY = (bounds.top + bounds.bottom) / 2;
    items.forEach((item) => {
      const size = effectiveSize(item);
      if (direction === "left") item.x_mm = round(bounds.left);
      else if (direction === "center-x") item.x_mm = round(centerX - size.width / 2);
      else if (direction === "right") item.x_mm = round(bounds.right - size.width);
      else if (direction === "top") item.y_mm = round(bounds.top);
      else if (direction === "center-y") item.y_mm = round(centerY - size.height / 2);
      else if (direction === "bottom") item.y_mm = round(bounds.bottom - size.height);
    });
    const labels = {
      left: "à gauche",
      "center-x": "au centre horizontal",
      right: "à droite",
      top: "en haut",
      "center-y": "au centre vertical",
      bottom: "en bas",
    };
    const referenceLabel = effectiveAlignmentReference() === "selection" ? "la sélection" : "la planche";
    commitLayoutMutation(before);
    render();
    window.preniumToast?.(`${items.length} visuel${items.length > 1 ? "s" : ""} aligné${items.length > 1 ? "s" : ""} ${labels[direction]} sur ${referenceLabel}.`, "success");
  }

  function distributeSelectedItems(axis) {
    const items = selectedItems();
    if (items.length < 3 || !canEdit || busy || ["rendering", "validated"].includes(state.status)) return;
    const before = layoutSnapshot();
    const horizontal = axis === "horizontal";
    const sorted = [...items].sort((first, second) => horizontal
      ? first.x_mm - second.x_mm
      : first.y_mm - second.y_mm);
    const first = sorted[0];
    const last = sorted.at(-1);
    const firstStart = horizontal ? first.x_mm : first.y_mm;
    const lastSize = effectiveSize(last);
    const lastEnd = (horizontal ? last.x_mm + lastSize.width : last.y_mm + lastSize.height);
    const totalSize = sorted.reduce((total, item) => {
      const size = effectiveSize(item);
      return total + (horizontal ? size.width : size.height);
    }, 0);
    const gap = (lastEnd - firstStart - totalSize) / (sorted.length - 1);
    if (gap < 0) {
      window.preniumToast?.("La sélection manque d’espace pour être répartie sans chevauchement.", "error");
      return;
    }
    let cursor = firstStart;
    sorted.forEach((item) => {
      if (horizontal) item.x_mm = round(cursor);
      else item.y_mm = round(cursor);
      const size = effectiveSize(item);
      cursor += (horizontal ? size.width : size.height) + gap;
    });
    commitLayoutMutation(before);
    render();
    window.preniumToast?.(`Répartition ${horizontal ? "horizontale" : "verticale"} appliquée.`, "success");
  }

  function applyPreciseGap(axis) {
    const items = selectedItems();
    if (items.length < 2 || !canEdit || busy || ["rendering", "validated"].includes(state.status)) return;
    const input = q("[data-selection-gap]");
    const gap = Math.max(0, Math.min(1000, Number(input.value) || 0));
    input.value = round(gap, 2);
    const before = layoutSnapshot();
    const horizontal = axis === "horizontal";
    const sorted = [...items].sort((first, second) => horizontal
      ? first.x_mm - second.x_mm
      : first.y_mm - second.y_mm);
    let cursor = horizontal ? sorted[0].x_mm : sorted[0].y_mm;
    const requiredSpan = sorted.reduce((total, item) => {
      const size = effectiveSize(item);
      return total + (horizontal ? size.width : size.height);
    }, 0) + gap * (sorted.length - 1);
    const placementLimit = horizontal ? state.width_mm : state.maximum_height_mm;
    if (cursor < 0 || cursor + requiredSpan > placementLimit) {
      window.preniumToast?.(`L’écart demandé ferait déborder la sélection ${horizontal ? "de la largeur" : "de la hauteur maximale"} de la planche.`, "error");
      return;
    }
    sorted.forEach((item) => {
      if (horizontal) item.x_mm = round(cursor);
      else item.y_mm = round(cursor);
      const size = effectiveSize(item);
      cursor += (horizontal ? size.width : size.height) + gap;
    });
    commitLayoutMutation(before);
    render();
    window.preniumToast?.(`Écart ${horizontal ? "horizontal" : "vertical"} fixé à ${round(gap, 2)} mm.`, "success");
  }

  q("[data-save-layout]").addEventListener("click", () => saveLayout().catch((error) => window.preniumToast?.(error.message, "error")));
  q("[data-auto-place]").addEventListener("click", autoPlaceWithSpacing);
  q("[data-apply-spacing]").addEventListener("click", autoPlaceWithSpacing);
  qa("[data-align-reference]").forEach((control) => {
    control.addEventListener("change", () => {
      alignmentReference = control.value;
      renderInspector();
      renderStatus();
    });
  });
  qa("[data-align]").forEach((control) => {
    control.addEventListener("click", () => alignSelectedItems(control.dataset.align));
  });
  qa("[data-distribute]").forEach((control) => {
    control.addEventListener("click", () => distributeSelectedItems(control.dataset.distribute));
  });
  qa("[data-apply-selection-gap]").forEach((control) => {
    control.addEventListener("click", () => applyPreciseGap(control.dataset.applySelectionGap));
  });
  q("[data-render-sheet]").addEventListener("click", () => runAction("render", { saveFirst: true }));
  q("[data-validate-sheet]").addEventListener("click", () => runAction("validate"));
  q("[data-create-order-project]")?.addEventListener("click", () => runAction("create-order-project"));
  function rotateSelected() {
    const item = selected();
    if (item && canEdit && !busy && !["rendering", "validated"].includes(state.status)) {
      const before = layoutSnapshot();
      item.rotation = (Number(item.rotation) + 90) % 360;
      commitLayoutMutation(before);
      render();
    }
  }
  q("[data-rotate-item]").addEventListener("click", rotateSelected);
  async function duplicateSelected() {
    const item = selected();
    if (!item || !canEdit || busy || ["rendering", "validated"].includes(state.status)) return;
    try {
      await saveLayout({ notify: false });
      const url = root.dataset.itemUrlTemplate.replace("00000000-0000-0000-0000-000000000000", item.public_id).replace("ACTION", "duplicate");
      await request(url, { method: "POST" }); await reloadState(); window.preniumToast?.("Occurrence dupliquée.", "success");
    } catch (error) { window.preniumToast?.(error.message, "error"); }
  }
  q("[data-duplicate-item]").addEventListener("click", duplicateSelected);

  async function deleteSelected() {
    const items = selectedItems();
    if (!items.length || !canEdit || busy || ["rendering", "validated"].includes(state.status)) return;
    const itemPublicIds = items.map((item) => item.public_id);
    if (itemPublicIds.length > 1) {
      const confirmed = window.confirm(
        `Supprimer définitivement les ${itemPublicIds.length} visuels sélectionnés de cette planche ?`
      );
      if (!confirmed) return;
    }
    try {
      if (dirty) await saveLayout({ notify: false });
      const payload = await request(root.dataset.batchDeleteUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item_public_ids: itemPublicIds }),
      });
      clearSelection();
      await reloadState();
      const deletedCount = Number(payload.deleted_count) || itemPublicIds.length;
      window.preniumToast?.(
        `${deletedCount} visuel${deletedCount > 1 ? "s" : ""} supprimé${deletedCount > 1 ? "s" : ""}.`,
        "success"
      );
    } catch (error) { window.preniumToast?.(error.message, "error"); }
  }
  q("[data-delete-item]").addEventListener("click", deleteSelected);
  q("[data-delete-selected]").addEventListener("click", deleteSelected);

  root.addEventListener("click", (event) => {
    const issueFix = event.target.closest("[data-issue-fix]");
    if (issueFix && !issueFix.disabled) {
      fixOverflowIssue(issueFix.dataset.issueFix);
      return;
    }
    const issueFocus = event.target.closest("[data-issue-focus]");
    if (issueFocus && !issueFocus.disabled) {
      focusIssue(issueFocus.dataset.issueFocus);
      return;
    }
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
      const before = layoutSnapshot();
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
      commitLayoutMutation(before);
      render();
    });
  });

  window.addEventListener("keydown", (event) => {
    if (event.target.closest("input, textarea, select")) return;
    const modifier = event.metaKey || event.ctrlKey;
    if (modifier && event.key.toLowerCase() === "y") {
      event.preventDefault();
      redoLayoutMutation();
    } else if (modifier && event.key.toLowerCase() === "z") {
      event.preventDefault();
      if (event.shiftKey) redoLayoutMutation();
      else undoLayoutMutation();
    } else if (modifier && event.key.toLowerCase() === "a") {
      event.preventDefault();
      selectAllItems();
    } else if (modifier && event.key.toLowerCase() === "s" && canEdit && !busy && !["rendering", "validated"].includes(state.status)) {
      event.preventDefault();
      saveLayout().catch((error) => window.preniumToast?.(error.message, "error"));
    } else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "d" && canEdit && selectedIds.size === 1) {
      event.preventDefault();
      duplicateSelected();
    } else if (event.key.toLowerCase() === "r" && canEdit && selectedIds.size === 1 && selected()) {
      event.preventDefault();
      rotateSelected();
    } else if ((event.key === "Delete" || event.key === "Backspace") && canEdit && selectedIds.size > 0) {
      event.preventDefault();
      deleteSelected();
    } else if (event.key === "Escape") {
      clearSelection();
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
