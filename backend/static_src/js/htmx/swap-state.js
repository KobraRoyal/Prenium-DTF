function syncTabsRowChipActive(group, activeEl) {
  group.querySelectorAll(".chip").forEach((el) => el.classList.remove("is-active"));
  if (activeEl) {
    activeEl.classList.add("is-active");
  }
}

function togglePanelLoading(target, on) {
  if (!target || !(target instanceof HTMLElement)) {
    return;
  }
  target.classList.toggle("is-loading", on);
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
  }
});

document.body.addEventListener("htmx:responseError", (event) => {
  togglePanelLoading(event.detail?.target, false);
});
