function syncTabsRowChipActive(group, activeEl) {
  group.querySelectorAll(".chip").forEach((el) => {
    const on = el === activeEl;
    el.classList.toggle("is-active", on);
    if (el.getAttribute("role") === "tab") {
      el.setAttribute("aria-selected", on ? "true" : "false");
      el.setAttribute("tabindex", on ? "0" : "-1");
    }
  });
  if (activeEl) {
    activeEl.classList.add("is-active");
  }
}

function togglePanelLoading(target, on) {
  if (!target || !(target instanceof HTMLElement)) {
    return;
  }
  target.classList.toggle("is-loading", on);
  if (target.getAttribute("role") === "tabpanel") {
    target.setAttribute("aria-busy", on ? "true" : "false");
  }
}

function syncPanelLabel(activeEl) {
  if (!activeEl || activeEl.getAttribute("role") !== "tab") {
    return;
  }
  const panelId = activeEl.getAttribute("aria-controls");
  const panel = panelId ? document.getElementById(panelId) : null;
  if (panel && activeEl.id) {
    panel.setAttribute("aria-labelledby", activeEl.id);
  }
}

function moveOrderTabFocus(tab, direction) {
  const group = tab.closest(".portal-order-tabs, .tabs-row");
  if (!group) {
    return;
  }
  const tabs = Array.from(group.querySelectorAll('[role="tab"]'));
  const current = tabs.indexOf(tab);
  if (current < 0 || tabs.length === 0) {
    return;
  }
  let next = current;
  if (direction === "next") next = (current + 1) % tabs.length;
  if (direction === "prev") next = (current - 1 + tabs.length) % tabs.length;
  if (direction === "first") next = 0;
  if (direction === "last") next = tabs.length - 1;
  tabs[next].focus();
  tabs[next].click();
}

document.addEventListener("click", (event) => {
  const chip = event.target.closest(
    ".portal-order-tabs .chip, .tabs-row .chip"
  );
  if (!chip) {
    return;
  }
  const group = chip.closest(".portal-order-tabs, .tabs-row");
  if (!group) {
    return;
  }
  syncTabsRowChipActive(group, chip);
  syncPanelLabel(chip);
});

document.addEventListener("keydown", (event) => {
  const tab = event.target.closest?.('.portal-order-tabs [role="tab"]');
  if (!tab) {
    return;
  }
  if (event.key === "ArrowRight" || event.key === "ArrowDown") {
    event.preventDefault();
    moveOrderTabFocus(tab, "next");
  } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
    event.preventDefault();
    moveOrderTabFocus(tab, "prev");
  } else if (event.key === "Home") {
    event.preventDefault();
    moveOrderTabFocus(tab, "first");
  } else if (event.key === "End") {
    event.preventDefault();
    moveOrderTabFocus(tab, "last");
  }
});

document.body.addEventListener("htmx:beforeRequest", (event) => {
  togglePanelLoading(event.detail?.target, true);
});

document.body.addEventListener("htmx:afterSwap", (event) => {
  const target = event.detail?.target;
  togglePanelLoading(target, false);
  if (!target?.id?.endsWith("order-panel")) {
    return;
  }
  const elt = event.detail?.elt;
  if (!elt?.classList?.contains("chip")) {
    return;
  }
  const group = elt.closest(".portal-order-tabs, .tabs-row");
  if (group) {
    syncTabsRowChipActive(group, elt);
    syncPanelLabel(elt);
  }
});

document.body.addEventListener("htmx:responseError", (event) => {
  togglePanelLoading(event.detail?.target, false);
});
