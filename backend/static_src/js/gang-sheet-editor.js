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
  let pendingValidateAfterRender = false;
  let resizeFrame = null;
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
    return state.items.map(({ public_id, x_mm, y_mm, width_mm, height_mm, rotation, layout_group_id }) => ({
      public_id,
      x_mm,
      y_mm,
      width_mm,
      height_mm,
      rotation,
      layout_group_id: layout_group_id || null,
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
      item.layout_group_id = saved.layout_group_id || null;
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
    const scroll = q("[data-canvas-scroll]") || stage;
    const availableWidth = Math.max(320, (scroll?.clientWidth || stage?.clientWidth || 0) - 64);
    const baseWidth = Math.min(700, availableWidth);
    canvas.style.width = `${Math.round(baseWidth * zoom)}px`;
    q("[data-zoom-value]").textContent = `${Math.round(zoom * 100)} %`;
    window.requestAnimationFrame(() => {
      positionSelectedItemToolbar();
      positionSelectionGroupToolbar();
    });
  }

  function setMobilePanel(panelName, { focusTab = false } = {}) {
    const isMobile = window.matchMedia("(max-width: 980px)").matches;
    qa("[data-mobile-panel-tab]").forEach((tab) => {
      const active = tab.dataset.mobilePanelTab === panelName;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active && focusTab) tab.focus();
    });
    qa("[data-editor-panel]").forEach((panel) => {
      const active = panel.dataset.editorPanel === panelName;
      panel.classList.toggle("is-mobile-active", active);
      panel.hidden = isMobile && !active;
      if (isMobile) {
        panel.setAttribute("role", "tabpanel");
        panel.setAttribute("aria-labelledby", `gang-editor-tab-${panel.dataset.editorPanel}`);
      } else {
        panel.removeAttribute("role");
        panel.removeAttribute("aria-labelledby");
      }
    });
    if (panelName === "canvas") window.requestAnimationFrame(renderZoom);
  }

  function handleMobileTabKeydown(event) {
    if (!window.matchMedia("(max-width: 980px)").matches) return;
    const tabs = qa("[data-mobile-panel-tab]");
    const currentIndex = tabs.indexOf(event.currentTarget);
    let nextIndex = currentIndex;
    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length;
    else if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = tabs.length - 1;
    else return;
    event.preventDefault();
    setMobilePanel(tabs[nextIndex].dataset.mobilePanelTab, { focusTab: true });
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

  function createItemAction({ label, icon, attribute, danger = false, iconOnly = false }) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `gang-sheet-item-action${danger ? " is-danger" : ""}${iconOnly ? " is-icon" : ""}`;
    button.setAttribute(attribute, "");
    const iconNode = document.createElement("span");
    iconNode.setAttribute("aria-hidden", "true");
    if (typeof icon === "string") {
      iconNode.textContent = icon;
    } else if (icon instanceof Node) {
      iconNode.append(icon);
    }
    button.append(iconNode);
    if (!iconOnly) {
      const labelNode = document.createElement("span");
      labelNode.textContent = label;
      button.append(labelNode);
    } else {
      button.setAttribute("title", label);
    }
    return button;
  }

  function createLockIcon({ open = false } = {}) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "16");
    svg.setAttribute("height", "16");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.75");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const paths = open
      ? [
          "M13.5 10.5V6.75a4.5 4.5 0 1 1 9 0v.75",
          "M4.5 21.75h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H4.5a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z",
        ]
      : [
          "M16.5 10.5V7.875a4.5 4.5 0 1 0-9 0V10.5m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z",
        ];
    paths.forEach((d) => {
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      svg.append(path);
    });
    return svg;
  }

  function positionToolbarNearRect(toolbar, targetRect, { preferBelow = false, topClearance = 0 } = {}) {
    if (!toolbar || !targetRect) return;
    const gap = 6;
    const canvasRect = canvas.getBoundingClientRect();
    const toolbarRect = toolbar.getBoundingClientRect();
    const contentLeft = canvasRect.left + canvas.clientLeft;
    const contentTop = canvasRect.top + canvas.clientTop;
    const idealLeft = targetRect.left - contentLeft + (targetRect.width - toolbarRect.width) / 2;
    const maxLeft = Math.max(gap, canvas.clientWidth - toolbarRect.width - gap);
    const left = Math.max(gap, Math.min(idealLeft, maxLeft));
    const aboveTop = targetRect.top - contentTop - toolbarRect.height - gap - topClearance;
    const belowTop = targetRect.bottom - contentTop + gap;
    let top = preferBelow ? belowTop : aboveTop;
    if (preferBelow) {
      if (top + toolbarRect.height > canvas.clientHeight - gap) top = aboveTop;
    } else if (top < gap) {
      top = belowTop;
    }
    const maxTop = Math.max(gap, canvas.clientHeight - toolbarRect.height - gap);
    toolbar.style.left = `${round(left)}px`;
    toolbar.style.top = `${round(Math.max(gap, Math.min(top, maxTop)))}px`;
    toolbar.style.visibility = "visible";
  }

  function positionSelectedItemToolbar() {
    const toolbar = canvas.querySelector("[data-item-toolbar]");
    const itemNode = selectedIds.size === 1 && selectedId ? canvas.querySelector(`[data-item-id="${selectedId}"]`) : null;
    if (!toolbar || !itemNode) return;
    positionToolbarNearRect(toolbar, itemNode.getBoundingClientRect());
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

  function positionSelectionGroupToolbar() {
    const toolbar = canvas.querySelector("[data-group-toolbar]");
    const frame = canvas.querySelector("[data-selection-frame]");
    if (!toolbar || !frame) return;
    // Menu sous le cadre : la taille d’ensemble reste lisible au-dessus.
    positionToolbarNearRect(toolbar, frame.getBoundingClientRect(), {
      preferBelow: true,
      topClearance: 40,
    });
  }

  function renderSelectionGroupToolbar() {
    if (!canEdit || selectedIds.size < 2 || ["rendering", "validated"].includes(state.status)) return;
    const items = selectedItems();
    const hasGroup = items.some((item) => item.layout_group_id);
    const allGroupedTogether = Boolean(
      items[0]?.layout_group_id
      && items.every((item) => item.layout_group_id === items[0].layout_group_id)
    );
    const toolbar = document.createElement("div");
    toolbar.className = "gang-sheet-item-toolbar gang-sheet-item-toolbar--group";
    toolbar.dataset.groupToolbar = "";
    toolbar.setAttribute("role", "toolbar");
    toolbar.setAttribute("aria-label", "Actions sur la sélection groupée");
    toolbar.style.visibility = "hidden";

    const rotateButton = createItemAction({
      label: "Pivoter",
      icon: "↻",
      attribute: "data-canvas-rotate-item",
    });
    rotateButton.setAttribute("aria-label", `Pivoter les ${items.length} visuels de 90 degrés`);
    rotateButton.disabled = busy;

    const groupButton = createItemAction({
      label: "Grouper",
      icon: createLockIcon(),
      attribute: "data-canvas-group-selection",
    });
    groupButton.setAttribute("aria-label", `Grouper ${items.length} visuels`);
    groupButton.disabled = busy || items.length < 2;

    const ungroupButton = createItemAction({
      label: "Dissocier",
      icon: createLockIcon({ open: true }),
      attribute: "data-canvas-ungroup-selection",
    });
    ungroupButton.setAttribute("aria-label", "Dissocier le groupe sélectionné");
    ungroupButton.disabled = busy || !hasGroup;
    if (allGroupedTogether) groupButton.hidden = true;
    else ungroupButton.hidden = !hasGroup;

    const deleteButton = createItemAction({
      label: "Supprimer",
      icon: "×",
      attribute: "data-canvas-delete-item",
      danger: true,
    });
    deleteButton.setAttribute("aria-label", `Supprimer les ${items.length} visuels sélectionnés`);
    deleteButton.disabled = busy;

    toolbar.append(rotateButton, groupButton, ungroupButton, deleteButton);
    canvas.append(toolbar);
    window.requestAnimationFrame(positionSelectionGroupToolbar);
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
      const isGrouped = Boolean(item.layout_group_id);
      node.className = `gang-sheet-item${isSelected ? " is-selected" : ""}${selectedId === item.public_id ? " is-primary" : ""}${isGrouped ? " is-grouped" : ""}${issueIds.has(item.public_id) ? " has-issue" : ""}`;
      node.dataset.itemId = item.public_id;
      if (item.layout_group_id) node.dataset.layoutGroupId = item.layout_group_id;
      node.style.left = `${(item.x_mm / state.width_mm) * 100}%`;
      node.style.top = `${(item.y_mm / state.height_mm) * 100}%`;
      node.style.width = `${(size.width / state.width_mm) * 100}%`;
      node.style.height = `${(size.height / state.height_mm) * 100}%`;
      node.setAttribute("aria-label", `${item.asset_name}, ${round(item.width_mm / 10, 1)} par ${round(item.height_mm / 10, 1)} centimètres`);
      node.setAttribute("aria-pressed", String(isSelected));
      node.setAttribute("aria-keyshortcuts", "R Delete Backspace Control+D Meta+D");
      node.tabIndex = selectedId === item.public_id || (selectedId === null && state.items[0] === item) ? 0 : -1;
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
        selectItem(item.public_id, {
          additive: touchMultiSelect || event.shiftKey || event.ctrlKey || event.metaKey,
          isolate: event.altKey,
        });
      });
      if (canEdit) {
        node.addEventListener("pointerdown", (event) => startPointerAction(event, item));
      }
      canvas.append(node);
    });
    renderSnapGuides();
    renderSelectionFrame();
    if (selectedIds.size === 1 && selected()) renderSelectedItemToolbar(selected());
    if (selectedIds.size > 1) renderSelectionGroupToolbar();
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
    const metricItems = q("[data-metric-items]");
    const metricUsage = q("[data-metric-usage]");
    const metricSurface = q("[data-metric-surface]");
    if (metricItems) metricItems.textContent = String(state.items.length);
    if (metricUsage) metricUsage.textContent = `${round(usage, 1)} %`;
    if (metricSurface) metricSurface.textContent = `${Number(state.surface_sqm).toFixed(4)} m²`;
    updateOrderQuoteUi();
    const canvasFormat = q("[data-canvas-format]");
    if (canvasFormat) {
      canvasFormat.textContent = `${round(state.width_mm / 10, 1)} × ${round(state.height_mm / 10, 1)} cm`;
    }
    const mobileIssueCount = q("[data-mobile-issue-count]");
    if (mobileIssueCount) mobileIssueCount.textContent = String(state.issues.length);
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

  function syncGroupControls({ locked = ["rendering", "validated"].includes(state.status) } = {}) {
    const selectionCount = selectedIds.size;
    const groupIds = new Set(
      selectedItems().map((item) => item.layout_group_id).filter(Boolean)
    );
    const canMutate = canEdit && !locked && !busy;
    qa("[data-group-selection], [data-canvas-group-selection]").forEach((control) => {
      control.disabled = !canMutate || selectionCount < 2;
    });
    qa("[data-ungroup-selection], [data-canvas-ungroup-selection]").forEach((control) => {
      control.disabled = !canMutate || groupIds.size === 0;
    });
    const groupHelp = q("[data-group-help]");
    if (groupHelp) {
      groupHelp.textContent = groupIds.size
        ? "Cliquez un membre pour sélectionner tout le groupe. Option + clic isole un visuel."
        : "Sélectionnez au moins 2 visuels pour créer un groupe mémorisé.";
    }
  }

  function renderInspector() {
    const item = selected();
    const selectionCount = selectedIds.size;
    const multiInspector = q("[data-multi-inspector]");
    q("[data-empty-inspector]").hidden = selectionCount > 0;
    q("[data-item-inspector]").hidden = selectionCount !== 1 || !item;
    if (multiInspector) multiInspector.hidden = selectionCount < 2;
    q("[data-alignment-panel]").hidden = selectionCount === 0;
    const advancedSelectionTools = q("[data-advanced-selection-tools]");
    if (advancedSelectionTools && selectionCount > 1) advancedSelectionTools.open = true;
    const selectionDelete = q("[data-delete-selected]");
    const selectionDeleteLabel = q("[data-delete-selected-label]");
    if (selectionDelete) {
      selectionDelete.hidden = selectionCount < 2;
      const label = selectionCount > 1
        ? `Supprimer la sélection (${selectionCount})`
        : "Supprimer la sélection";
      if (selectionDeleteLabel) selectionDeleteLabel.textContent = label;
      else selectionDelete.textContent = label;
    }
    if (selectionCount > 1) {
      const multiSummary = q("[data-multi-summary]");
      const multiBounds = q("[data-multi-bounds]");
      if (multiSummary) {
        multiSummary.textContent = `${selectionCount} visuel${selectionCount > 1 ? "s" : ""}`;
      }
      if (multiBounds) {
        const bounds = selectionBounds(selectedItems());
        multiBounds.textContent = `${round((bounds.right - bounds.left) / 10, 1)} × ${round((bounds.bottom - bounds.top) / 10, 1)} cm`;
      }
    }
    if (selectionCount > 0) {
      q("[data-selection-summary]").textContent = `${selectionCount} visuel${selectionCount > 1 ? "s" : ""} sélectionné${selectionCount > 1 ? "s" : ""}`;
      const reference = effectiveAlignmentReference();
      qa("[data-align-reference]").forEach((control) => {
        control.checked = control.value === reference;
      });
      const help = q("[data-alignment-help]");
      if (reference === "selection") {
        help.textContent = "Les visuels s’alignent individuellement sur le cadre de la sélection.";
      } else if (reference === "others") {
        help.textContent = "Le groupe se déplace d’un bloc pour s’aligner sur le cadre des autres visuels.";
      } else {
        help.textContent = "Le groupe se déplace d’un bloc dans la zone utile de la planche.";
      }
      syncGroupControls();
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
    const status = state.status;
    const assetCount = qa("[data-asset-card]").length;
    const itemCount = state.items.length;
    const issueCount = state.issues.length;
    const compositionComplete = itemCount > 0;
    const controlComplete = compositionComplete && issueCount === 0;
    const steps = {
      import: assetCount > 0 ? "complete" : "active",
      compose: compositionComplete ? "complete" : assetCount > 0 ? "active" : "pending",
      control: controlComplete ? "complete" : compositionComplete ? "active" : "pending",
      validate: status === "validated" ? "complete" : controlComplete ? "active" : "pending",
    };
    const currentStep = assetCount === 0
      ? "import"
      : !compositionComplete
        ? "compose"
        : issueCount > 0
          ? "control"
          : "validate";
    const stepNumbers = { import: "1", compose: "2", control: "3", validate: "4" };
    const details = {
      import: assetCount > 0 ? `${assetCount} source${assetCount > 1 ? "s" : ""} disponible${assetCount > 1 ? "s" : ""}` : "Ajouter vos fichiers",
      compose: itemCount > 0 ? `${itemCount} visuel${itemCount > 1 ? "s" : ""} placé${itemCount > 1 ? "s" : ""}` : "Placer les visuels",
      control: !compositionComplete
        ? "Après composition"
        : issueCount > 0
          ? `${issueCount} anomalie${issueCount > 1 ? "s" : ""} à corriger`
          : "Composition contrôlée",
      validate:
        status === "validated"
          ? "Planche validée"
          : status === "rendering"
            ? "Rendu HD en cours"
            : status === "ready"
              ? "Prête à confirmer"
              : status === "render_failed"
                ? "Relancer la confirmation"
                : "Confirmer la composition",
    };
    qa("[data-workflow-step]").forEach((node) => {
      const step = node.dataset.workflowStep;
      const stepState = steps[step];
      node.classList.toggle("is-active", stepState === "active");
      node.classList.toggle("is-complete", stepState === "complete");
      if (step === currentStep) node.setAttribute("aria-current", "step");
      else node.removeAttribute("aria-current");
      node.querySelector("[data-workflow-marker]").textContent =
        stepState === "complete" ? "✓" : stepNumbers[step];
      node.querySelector("[data-workflow-detail]").textContent = details[step];
    });
  }

  function renderStatus() {
    const labels = {
      draft: "Enregistré",
      rendering: "Rendu haute définition en cours…",
      ready: "Rendu prêt — validation possible",
      validated: "Validée pour la production",
      render_failed: state.render_error || "Le rendu a échoué",
    };
    const issueCount = state.issues.length;
    // Un seul message visible : enregistrement / cycle de vie. Les anomalies
    // n’apparaissent que s’il y en a (sinon le workflow « Contrôler » suffit).
    let statusText = busy
      ? "Enregistrement en cours…"
      : dirty
        ? "Modifications non enregistrées"
        : labels[state.status] || state.status;
    if (!busy && !dirty && issueCount > 0 && state.status === "draft") {
      statusText = `${issueCount} anomalie${issueCount > 1 ? "s" : ""} à corriger`;
    }
    q("[data-status-text]").textContent = statusText;
    const detail = q("[data-status-detail]");
    if (detail) {
      detail.textContent = busy
        ? "Enregistrement de la composition en cours."
        : dirty
          ? "Enregistrez pour sécuriser cette version."
          : issueCount > 0
            ? "Corrigez les anomalies avant de finaliser."
            : state.status === "validated"
              ? "La composition est verrouillée et prête pour la commande."
              : "Composition synchronisée.";
    }
    const issueNode = q("[data-issue-count]");
    if (issueNode) {
      const showIssues = issueCount > 0 && (busy || dirty || state.status !== "draft");
      issueNode.hidden = !showIssues;
      issueNode.textContent = showIssues
        ? `${issueCount} anomalie${issueCount > 1 ? "s" : ""}`
        : "";
    }
    root.dataset.dirty = String(dirty);
    root.dataset.sheetStatus = state.status;
    root.dataset.hasIssues = String(issueCount > 0);
    const locked = ["rendering", "validated"].includes(state.status);
    qa(
      "[data-add-asset], [data-asset-quantity], [data-save-layout], [data-auto-place], [data-input-width], [data-input-height], [data-input-x], [data-input-y], [data-lock-ratio], [data-rotate-item], [data-rotate-selection], [data-duplicate-item], [data-delete-item], [data-delete-selected], [data-align], [data-align-reference], [data-distribute], [data-selection-gap], [data-apply-selection-gap], [data-spacing-x], [data-spacing-y], [data-apply-spacing], [data-canvas-rotate-item], [data-canvas-delete-item], [data-snap-toggle], [data-select-all], [data-touch-multiselect], [data-issue-fix], [data-group-selection], [data-ungroup-selection]"
    ).forEach((control) => {
      const assetPending = control.matches("[data-add-asset]") && control.dataset.assetReady !== "true";
      control.disabled = !canEdit || locked || assetPending;
    });
    syncGroupControls({ locked });
    qa("[data-issue-focus]").forEach((control) => {
      control.disabled = busy;
    });
    q("[data-save-layout]").disabled = !canEdit || locked || !dirty || busy;
    const saveLabel = q("[data-save-label]");
    const saveText = busy ? "Enregistrement…" : dirty ? "Enregistrer" : "Enregistré";
    if (saveLabel) saveLabel.textContent = saveText;
    else q("[data-save-layout]").textContent = saveText;
    q("[data-save-layout]")?.classList.toggle("is-saved", !dirty && !busy);
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
    const selectionDeleteControl = q("[data-delete-selected]");
    if (selectionDeleteControl) {
      selectionDeleteControl.disabled = !canEdit || locked || busy || selectedIds.size < 2;
    }
    q("[data-select-all]").disabled = !canEdit || locked || busy || state.items.length === 0;
    q("[data-snap-toggle]").setAttribute("aria-pressed", String(snapEnabled));
    q("[data-touch-multiselect]").setAttribute("aria-pressed", String(touchMultiSelect));
    renderHistoryControls();
    q("[data-download-preview]").hidden = !["ready", "validated"].includes(state.status);
    const validateBtn = q("[data-validate-sheet]");
    const validateLabel = q("[data-validate-label]");
    const validationLead = q("[data-validation-lead]");
    const canStartRender =
      canEdit &&
      !busy &&
      state.items.length > 0 &&
      state.issues.length === 0 &&
      !locked &&
      ["draft", "render_failed"].includes(state.status);
    const canConfirmReady = canEdit && !busy && state.status === "ready" && state.issues.length === 0;
    if (validateBtn) {
      if (state.status === "rendering" || pendingValidateAfterRender) {
        validateBtn.disabled = true;
        if (validateLabel) validateLabel.textContent = "Rendu HD en cours…";
        if (validationLead) {
          validationLead.textContent = "Préparation du fichier atelier… la confirmation suivra automatiquement.";
        }
      } else if (state.status === "validated") {
        validateBtn.disabled = true;
        if (validateLabel) validateLabel.textContent = "Composition confirmée";
        if (validationLead) {
          validationLead.textContent = "Planche verrouillée. Téléchargez l’aperçu ou créez la commande.";
        }
      } else if (state.status === "ready") {
        validateBtn.disabled = !canConfirmReady;
        if (validateLabel) validateLabel.textContent = "Confirmer la composition";
        if (validationLead) {
          validationLead.textContent = "Rendu HD prêt. Confirmez pour verrouiller la composition.";
        }
      } else if (state.status === "render_failed") {
        validateBtn.disabled = !canStartRender;
        if (validateLabel) validateLabel.textContent = "Relancer la confirmation";
        if (validationLead) {
          validationLead.textContent = state.render_error || "Le rendu a échoué. Relancez la confirmation.";
        }
      } else {
        validateBtn.disabled = !canStartRender;
        if (validateLabel) validateLabel.textContent = "Confirmer la composition";
        if (validationLead) {
          validationLead.textContent =
            "Un seul clic prépare le rendu HD atelier, puis confirme la composition.";
        }
      }
    }
    syncCreateOrderProjectControl();
    const quantityField = q("[data-sheet-quantity-field]");
    const quantityInput = q("[data-sheet-quantity]");
    if (quantityField) {
      const showQuantity = state.status === "validated";
      quantityField.hidden = !showQuantity;
      if (quantityInput) {
        quantityInput.disabled = !canEdit || !showQuantity;
      }
    }
    updateOrderQuoteUi();
  }

  function sheetOrderQuote() {
    const qtyRaw = Number(q("[data-sheet-quantity]")?.value || 1);
    const qty = Number.isFinite(qtyRaw) && qtyRaw >= 1 ? Math.floor(qtyRaw) : 1;
    const surface = Number(state.surface_sqm || 0);
    const unit = Number(state.unit_price_eur || 0);
    const prep = Number(root.dataset.prepFeeEur || 0);
    const billable = round(surface * qty, 4);
    const dtf = round(billable * unit, 2);
    const total = round(dtf + prep, 2);
    return { qty, surface, billable, unit, prep, dtf, total };
  }

  function updateOrderQuoteUi() {
    const quote = sheetOrderQuote();
    const quoteBox = q("[data-sheet-order-quote]");
    const detail = q("[data-sheet-order-quote-detail]");
    const totalEl = q("[data-sheet-order-quote-total]");
    const showQuote = state.status === "validated";
    if (quoteBox) quoteBox.hidden = !showQuote;
    if (totalEl) totalEl.textContent = `${quote.total.toFixed(2)} €`;
    if (detail) {
      detail.textContent = `${quote.surface.toFixed(4)} m² × ${quote.qty} ex. = ${quote.billable.toFixed(4)} m² · DTF ${quote.dtf.toFixed(2)} € + préparation ${quote.prep.toFixed(2)} €`;
    }
    if (showQuote) {
      q("[data-metric-price]").textContent = `${quote.total.toFixed(2)} €`;
    } else {
      q("[data-metric-price]").textContent = `${Number(state.estimated_price_eur).toFixed(2)} €`;
    }
  }

  function syncCreateOrderProjectControl() {
    const link = q("[data-create-order-project]");
    if (!(link instanceof HTMLAnchorElement)) return;
    // Après validation AJAX, retirer aria-disabled / href="#" / is-disabled :
    // sinon pointer-events:none laisse le CTA « Créer le projet » inactif.
    const canCreate = canEdit && state.status === "validated";
    link.classList.toggle("is-disabled", !canCreate);
    if (canCreate) {
      link.removeAttribute("aria-disabled");
      link.removeAttribute("tabindex");
      const formUrl = root.dataset.createOrderFormUrl;
      if (formUrl) {
        link.setAttribute("href", formUrl);
      }
    } else {
      link.setAttribute("aria-disabled", "true");
      link.setAttribute("tabindex", "-1");
      link.setAttribute("href", "#");
    }
  }

  function clearSelection() {
    selectedId = null;
    selectedIds.clear();
  }

  function selectItem(publicId, { additive = false, isolate = false } = {}) {
    const item = state.items.find((candidate) => candidate.public_id === publicId);
    if (!item) return;
    const groupId = item.layout_group_id || null;
    if (!additive && groupId && !isolate) {
      selectedIds = new Set(
        state.items
          .filter((candidate) => candidate.layout_group_id === groupId)
          .map((candidate) => candidate.public_id)
      );
      selectedId = publicId;
      render();
      return;
    }
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

  function renderSelectionFrame() {
    const items = selectedItems();
    if (!items.length) return;
    const bounds = selectionBounds(items);
    const frame = document.createElement("div");
    const sharedGroupId = items[0]?.layout_group_id || null;
    const isPersistentGroup = Boolean(
      sharedGroupId && items.every((item) => item.layout_group_id === sharedGroupId)
    );
    const widthCm = round((bounds.right - bounds.left) / 10, 1);
    const heightCm = round((bounds.bottom - bounds.top) / 10, 1);
    frame.className = `gang-selection-frame${items.length > 1 ? " is-multiple" : ""}${isPersistentGroup ? " is-group" : ""}`;
    frame.dataset.selectionFrame = "";
    frame.setAttribute("aria-hidden", "true");
    frame.style.left = `${(bounds.left / state.width_mm) * 100}%`;
    frame.style.top = `${(bounds.top / state.height_mm) * 100}%`;
    frame.style.width = `${((bounds.right - bounds.left) / state.width_mm) * 100}%`;
    frame.style.height = `${((bounds.bottom - bounds.top) / state.height_mm) * 100}%`;
    if (items.length > 1) {
      const chrome = document.createElement("div");
      chrome.className = "gang-selection-frame__chrome";
      const badge = document.createElement("span");
      badge.className = "gang-selection-frame__badge";
      const countLabel = isPersistentGroup
        ? `Groupe · ${items.length}`
        : `${items.length} sélectionnés`;
      badge.textContent = `${countLabel} · ${widthCm} × ${heightCm} cm`;
      chrome.append(badge);
      frame.append(chrome);
    }
    canvas.append(frame);
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

  function canStartRectangleSelection(event) {
    if (!canEdit || busy || ["rendering", "validated"].includes(state.status)) return false;
    if (event.pointerType === "touch" || event.button !== 0) return false;
    const target = event.target;
    if (!(target instanceof Element)) return false;
    if (target.closest("[data-item-id], [data-item-toolbar], [data-group-toolbar], [data-resize-handle], [data-crop-box]")) {
      return false;
    }
    return target === canvas
      || target === canvasClearZone
      || canvas.contains(target)
      || Boolean(canvasClearZone?.contains(target));
  }

  function pointerToCanvasPx(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, canvas.clientWidth);
    const height = Math.max(1, canvas.clientHeight);
    const x = clientX - rect.left - canvas.clientLeft;
    const y = clientY - rect.top - canvas.clientTop;
    return {
      x: Math.max(0, Math.min(width, x)),
      y: Math.max(0, Math.min(height, y)),
      width,
      height,
    };
  }

  function startRectangleSelection(event) {
    if (!canStartRectangleSelection(event)) return;
    event.preventDefault();
    const pointerId = event.pointerId;
    const start = pointerToCanvasPx(event.clientX, event.clientY);
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
    canvas.classList.add("is-marquee-selecting");
    canvas.setPointerCapture?.(event.pointerId);
    const applyMarqueeSelection = (left, top, right, bottom, width, height) => {
      const area = {
        left: (left / width) * state.width_mm,
        top: (top / height) * state.height_mm,
        right: (right / width) * state.width_mm,
        bottom: (bottom / height) * state.height_mm,
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
        node.classList.toggle("is-primary", selectedIds.size === 1 && node.dataset.itemId === Array.from(selectedIds)[0]);
        node.setAttribute("aria-pressed", String(isSelected));
      });
    };
    const move = (moveEvent) => {
      if (moveEvent.pointerId !== pointerId) return;
      const current = pointerToCanvasPx(moveEvent.clientX, moveEvent.clientY);
      moved = moved || Math.abs(current.x - start.x) > 2 || Math.abs(current.y - start.y) > 2;
      if (!moved) return;
      const left = Math.min(start.x, current.x);
      const top = Math.min(start.y, current.y);
      const right = Math.max(start.x, current.x);
      const bottom = Math.max(start.y, current.y);
      marquee.style.left = `${left}px`;
      marquee.style.top = `${top}px`;
      marquee.style.width = `${right - left}px`;
      marquee.style.height = `${bottom - top}px`;
      applyMarqueeSelection(left, top, right, bottom, current.width, current.height);
    };
    const cleanup = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", cancel);
      if (canvas.hasPointerCapture?.(pointerId)) canvas.releasePointerCapture(pointerId);
      canvas.classList.remove("is-marquee-selecting");
      marquee.remove();
    };
    const end = (endEvent) => {
      if (endEvent.pointerId !== pointerId) return;
      cleanup();
      suppressNextCanvasClick = moved;
      if (!moved && !additive) {
        selectedIds = new Set();
        selectedId = null;
      } else {
        selectedId = Array.from(selectedIds).at(-1) || null;
      }
      render();
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
      if (!resizing && item.layout_group_id) {
        selectedIds = new Set(
          state.items
            .filter((candidate) => candidate.layout_group_id === item.layout_group_id)
            .map((candidate) => candidate.public_id)
        );
      } else {
        selectedIds = new Set([item.public_id]);
      }
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
        items: state.items.map(({ public_id, x_mm, y_mm, width_mm, height_mm, rotation, layout_group_id }) => ({
          public_id,
          x_mm,
          y_mm,
          width_mm,
          height_mm,
          rotation,
          layout_group_id: layout_group_id || null,
        })),
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
        if (state.status === "rendering") {
          pollTimer = window.setTimeout(poll, 2000);
          return;
        }
        if (state.status === "ready") {
          if (pendingValidateAfterRender) {
            pendingValidateAfterRender = false;
            window.preniumToast?.("Rendu HD terminé. Confirmation en cours…", "success");
            await runAction("validate");
            return;
          }
          window.preniumToast?.("Rendu HD terminé. L’aperçu est disponible.", "success");
          return;
        }
        if (state.status === "render_failed") {
          pendingValidateAfterRender = false;
          window.preniumToast?.("Le rendu HD a échoué.", "error");
        }
      } catch (error) {
        pollTimer = window.setTimeout(poll, 4000);
      }
    };
    pollTimer = window.setTimeout(poll, 1500);
  }

  async function confirmComposition() {
    if (!canEdit || busy) return;
    if (state.status === "ready") {
      await runAction("validate");
      return;
    }
    if (!["draft", "render_failed"].includes(state.status)) return;
    if (!state.items.length || state.issues.length > 0) {
      window.preniumToast?.("Corrigez les anomalies avant de confirmer.", "error");
      return;
    }
    pendingValidateAfterRender = true;
    await runAction("render", { saveFirst: true });
    if (!["rendering", "ready"].includes(state.status)) {
      pendingValidateAfterRender = false;
      renderStatus();
    }
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
    tab.addEventListener("keydown", handleMobileTabKeydown);
  });

  qa("[data-workflow-panel-target]").forEach((control) => {
    control.addEventListener("click", () => {
      const panelName = control.dataset.workflowPanelTarget;
      if (window.matchMedia("(max-width: 980px)").matches) {
        setMobilePanel(panelName, { focusTab: true });
        if (control.closest("[data-workflow-step='validate']")) {
          window.requestAnimationFrame(() => {
            q(".gang-inspector-panel--validation")?.scrollIntoView({ block: "start", behavior: "smooth" });
          });
        }
      } else {
        q(`[data-editor-panel='${panelName}']`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    });
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
  canvasClearZone.addEventListener("pointerdown", startRectangleSelection);
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

  function sheetUsefulBounds() {
    const margin = Math.max(0, Number(state.margin_mm) || 0);
    return {
      left: margin,
      top: margin,
      right: Math.max(margin, state.width_mm - margin),
      bottom: Math.max(margin, state.height_mm - margin),
    };
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
    const reference = effectiveAlignmentReference();
    if (reference === "selection") return selectionBounds(items);
    if (reference === "others") {
      const selectedSet = new Set(items.map((item) => item.public_id));
      const others = state.items.filter((item) => !selectedSet.has(item.public_id));
      if (!others.length) return sheetUsefulBounds();
      return selectionBounds(others);
    }
    return sheetUsefulBounds();
  }

  function translateSelectionAsGroup(direction) {
    const items = selectedItems();
    if (!items.length || !canEdit || ["rendering", "validated"].includes(state.status)) return;
    const before = layoutSnapshot();
    const group = selectionBounds(items);
    const target = alignmentBounds(items);
    let deltaX = 0;
    let deltaY = 0;
    if (direction === "left") deltaX = target.left - group.left;
    else if (direction === "center-x") {
      deltaX = (target.left + target.right) / 2 - (group.left + group.right) / 2;
    } else if (direction === "right") deltaX = target.right - group.right;
    else if (direction === "top") deltaY = target.top - group.top;
    else if (direction === "center-y") {
      deltaY = (target.top + target.bottom) / 2 - (group.top + group.bottom) / 2;
    } else if (direction === "bottom") deltaY = target.bottom - group.bottom;
    items.forEach((item) => {
      item.x_mm = round(item.x_mm + deltaX);
      item.y_mm = round(item.y_mm + deltaY);
    });
    const labels = {
      left: "à gauche",
      "center-x": "au centre horizontal",
      right: "à droite",
      top: "en haut",
      "center-y": "au centre vertical",
      bottom: "en bas",
    };
    const referenceLabel = effectiveAlignmentReference() === "others"
      ? "les autres visuels"
      : "la planche";
    commitLayoutMutation(before);
    render();
    window.preniumToast?.(
      `Groupe déplacé ${labels[direction]} par rapport à ${referenceLabel}.`,
      "success"
    );
  }

  function alignSelectedItems(direction) {
    const items = selectedItems();
    if (!items.length || !canEdit || ["rendering", "validated"].includes(state.status)) return;
    if (effectiveAlignmentReference() !== "selection") {
      translateSelectionAsGroup(direction);
      return;
    }
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
    commitLayoutMutation(before);
    render();
    window.preniumToast?.(
      `${items.length} visuel${items.length > 1 ? "s" : ""} aligné${items.length > 1 ? "s" : ""} ${labels[direction]} sur la sélection.`,
      "success"
    );
  }

  function groupSelectedItems() {
    const items = selectedItems();
    if (items.length < 2 || !canEdit || busy || ["rendering", "validated"].includes(state.status)) {
      return;
    }
    const before = layoutSnapshot();
    const groupId = window.crypto?.randomUUID?.() || `group-${Date.now()}`;
    items.forEach((item) => {
      item.layout_group_id = groupId;
    });
    commitLayoutMutation(before);
    render();
    window.preniumToast?.(`Groupe de ${items.length} visuels mémorisé.`, "success");
  }

  function ungroupSelectedItems() {
    const items = selectedItems().filter((item) => item.layout_group_id);
    if (!items.length || !canEdit || busy || ["rendering", "validated"].includes(state.status)) {
      return;
    }
    const before = layoutSnapshot();
    const groupIds = new Set(items.map((item) => item.layout_group_id));
    state.items.forEach((item) => {
      if (item.layout_group_id && groupIds.has(item.layout_group_id)) {
        item.layout_group_id = null;
      }
    });
    commitLayoutMutation(before);
    render();
    window.preniumToast?.("Groupe dissocié.", "success");
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
  q("[data-group-selection]")?.addEventListener("click", groupSelectedItems);
  q("[data-ungroup-selection]")?.addEventListener("click", ungroupSelectedItems);
  qa("[data-distribute]").forEach((control) => {
    control.addEventListener("click", () => distributeSelectedItems(control.dataset.distribute));
  });
  qa("[data-apply-selection-gap]").forEach((control) => {
    control.addEventListener("click", () => applyPreciseGap(control.dataset.applySelectionGap));
  });
  q("[data-validate-sheet]")?.addEventListener("click", () => {
    confirmComposition();
  });
  q("[data-create-order-project]")?.addEventListener("click", (event) => {
    const link = event.currentTarget;
    if (!(link instanceof HTMLAnchorElement)) {
      return;
    }
    const canCreate = canEdit && state.status === "validated";
    if (!canCreate || link.getAttribute("aria-disabled") === "true") {
      event.preventDefault();
      return;
    }
    const quantity = Number(q("[data-sheet-quantity]")?.value || 1);
    const safeQuantity = Number.isFinite(quantity) && quantity >= 1 ? Math.floor(quantity) : 1;
    const baseUrl = root.dataset.createOrderFormUrl || link.getAttribute("href") || "";
    if (!baseUrl || baseUrl === "#") {
      event.preventDefault();
      return;
    }
    try {
      const url = new URL(baseUrl, window.location.origin);
      url.searchParams.set("quantity", String(safeQuantity));
      event.preventDefault();
      window.location.assign(url.toString());
    } catch (_error) {
      // Fallback: navigate to the bare form URL.
    }
  });
  q("[data-sheet-quantity]")?.addEventListener("input", () => updateOrderQuoteUi());
  q("[data-sheet-quantity]")?.addEventListener("change", () => updateOrderQuoteUi());
  function rotateSelected() {
    const items = selectedItems();
    if (!items.length || !canEdit || busy || ["rendering", "validated"].includes(state.status)) return;
    const before = layoutSnapshot();
    if (items.length === 1) {
      items[0].rotation = (Number(items[0].rotation) + 90) % 360;
    } else {
      const bounds = selectionBounds(items);
      const centerX = (bounds.left + bounds.right) / 2;
      const centerY = (bounds.top + bounds.bottom) / 2;
      items.forEach((item) => {
        const size = effectiveSize(item);
        const itemCenterX = item.x_mm + size.width / 2;
        const itemCenterY = item.y_mm + size.height / 2;
        const dx = itemCenterX - centerX;
        const dy = itemCenterY - centerY;
        // Pivot horaire 90° du groupe autour de son centre.
        const nextCenterX = centerX + dy;
        const nextCenterY = centerY - dx;
        item.rotation = (Number(item.rotation) + 90) % 360;
        const nextSize = effectiveSize(item);
        item.x_mm = round(nextCenterX - nextSize.width / 2);
        item.y_mm = round(nextCenterY - nextSize.height / 2);
      });
    }
    commitLayoutMutation(before);
    render();
    if (items.length > 1) {
      window.preniumToast?.(
        `Groupe de ${items.length} visuels pivoté de 90°.`,
        "success"
      );
    }
  }
  q("[data-rotate-item]")?.addEventListener("click", rotateSelected);
  q("[data-rotate-selection]")?.addEventListener("click", rotateSelected);
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
  q("[data-delete-item]")?.addEventListener("click", deleteSelected);
  q("[data-delete-selected]")?.addEventListener("click", deleteSelected);

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
    if (deleteButton && !deleteButton.disabled) {
      deleteSelected();
      return;
    }
    const groupButton = event.target.closest("[data-canvas-group-selection]");
    if (groupButton && !groupButton.disabled) {
      groupSelectedItems();
      return;
    }
    const ungroupButton = event.target.closest("[data-canvas-ungroup-selection]");
    if (ungroupButton && !ungroupButton.disabled) ungroupSelectedItems();
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

  function shouldIgnoreStudioShortcut(event) {
    const target = event.target;
    if (!(target instanceof Element) || !root.contains(target)) return true;
    if (canvas.contains(target)) return Boolean(target.closest("input, textarea, select, [contenteditable]"));
    return true;
  }

  window.addEventListener("keydown", (event) => {
    if (shouldIgnoreStudioShortcut(event)) return;
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
    } else if (event.key.toLowerCase() === "r" && canEdit && selectedIds.size > 0) {
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
  window.addEventListener("resize", () => {
    if (resizeFrame !== null) return;
    resizeFrame = window.requestAnimationFrame(() => {
      resizeFrame = null;
      const activePanel = q("[data-mobile-panel-tab][aria-selected='true']")?.dataset.mobilePanelTab || "canvas";
      setMobilePanel(activePanel);
    });
  });
  syncSpacingControls();
  setMobilePanel("canvas");
  render();
  if (state.status === "rendering") startPolling();
}
