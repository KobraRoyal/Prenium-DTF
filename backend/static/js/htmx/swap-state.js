const ORDER_TAB_SELECTOR =
  '.portal-order-tabs [role="tab"][data-panel-slug]';
const TAB_CONTROL_SELECTOR = `${ORDER_TAB_SELECTOR}, .tabs-row .chip`;

function syncTabGroupActiveState(group, activeEl) {
  const controls = group.matches(".portal-order-tabs")
    ? group.querySelectorAll('[role="tab"][data-panel-slug]')
    : group.querySelectorAll(".chip");

  controls.forEach((el) => {
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

function syncOrderTabsFromPath(path) {
  let panelSlug;
  try {
    const restoredUrl = new URL(
      path || window.location.href,
      window.location.origin
    );
    panelSlug = restoredUrl.searchParams.get("panel");
  } catch {
    return;
  }
  if (!panelSlug) {
    return;
  }

  document.querySelectorAll(".portal-order-tabs").forEach((group) => {
    const activeTab = Array.from(
      group.querySelectorAll('[role="tab"][data-panel-slug]')
    ).find((tab) => tab.dataset.panelSlug === panelSlug);
    if (activeTab) {
      syncTabGroupActiveState(group, activeTab);
      syncPanelLabel(activeTab);
    }
  });
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
  const control = event.target.closest(TAB_CONTROL_SELECTOR);
  if (!control) {
    return;
  }
  const group = control.closest(".portal-order-tabs, .tabs-row");
  if (!group) {
    return;
  }
  syncTabGroupActiveState(group, control);
  syncPanelLabel(control);
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
  const requestControl = event.detail?.requestConfig?.elt;
  if (!requestControl?.matches?.(ORDER_TAB_SELECTOR)) {
    return;
  }
  const group = requestControl.closest(".portal-order-tabs");
  if (group) {
    syncTabGroupActiveState(group, requestControl);
    syncPanelLabel(requestControl);
  }
});

document.body.addEventListener("htmx:responseError", (event) => {
  togglePanelLoading(event.detail?.target, false);
});

document.body.addEventListener("htmx:historyRestore", (event) => {
  syncOrderTabsFromPath(event.detail?.path);
});
