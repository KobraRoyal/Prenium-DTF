/* Progressive enhancement, scoped to POD. Server permissions remain authoritative. */
const workspaceSelector = ".pod-page";
let refreshPending = false;

function enhancePodWorkspace() {
  const workspace = document.querySelector(workspaceSelector);
  if (!workspace || !window.htmx) return;
  workspace.querySelectorAll("a[href], form").forEach((control) => {
    if (control.closest("#pod-variant-drawer") || control.hasAttribute("hx-boost") ||
        control.matches("[hx-get], [hx-post]")) return;
    const form = control instanceof HTMLFormElement;
    const url = new URL(form ? control.action : control.href, location.href);
    // Downloads, OAuth and non-POD destinations retain native browser behavior.
    if (url.origin !== location.origin || !url.pathname.startsWith("/staff/atelier/pod/") ||
        url.pathname.endsWith(".pdf") || control.hasAttribute("download") ||
        (!form && (url.hash || control.target)) ||
        (form && control.querySelector('[name="intent"][value="oauth"]'))) return;
    control.setAttribute("hx-boost", "true");
    control.setAttribute("hx-target", workspaceSelector);
    control.setAttribute("hx-select", workspaceSelector);
    control.setAttribute("hx-swap", "outerHTML show:none");
    control.setAttribute("hx-indicator", "#portal-htmx-indicator");
    control.setAttribute("hx-sync", "closest .pod-page:queue last");
    control.dataset.podDynamic = "true";
    if (form) {
      control.setAttribute("hx-sync", "this:drop");
      if (control.enctype === "multipart/form-data") {
        control.setAttribute("hx-encoding", "multipart/form-data");
      }
    }
    window.htmx.process(control);
  });
}

function notifyError(message) {
  window.preniumToast?.(message, "error");
}

document.body.addEventListener("htmx:beforeSwap", (event) => {
  const { target, xhr } = event.detail;
  if (!target?.matches?.(".pod-page, #pod-variant-drawer")) return;
  const selector = target.matches(".pod-page") ? ".pod-page" : "#pod-variant-config-panel";
  const response = new DOMParser().parseFromString(xhr.responseText || "", "text/html");
  if (xhr.status === 400 && response.querySelector(selector)) {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
  if (xhr.status >= 200 && xhr.status < 300 && !response.querySelector(selector)) {
    event.detail.shouldSwap = false;
    const destination = new URL(xhr.responseURL || location.href, location.href);
    if (destination.origin === location.origin && destination.pathname.includes("login")) {
      location.assign(destination.href);
    } else {
      notifyError("La vue n’a pas pu être actualisée. Vos données saisies restent disponibles.");
    }
  }
  const panel = document.querySelector("#pod-variant-config-panel");
  if (target.matches(".pod-page") && panel?.open) panel.dataset.podReopen = "true";
});

document.body.addEventListener("htmx:afterSwap", () => {
  enhancePodWorkspace();
  const panel = document.querySelector('#pod-variant-config-panel[data-pod-reopen="true"]');
  if (panel) {
    delete panel.dataset.podReopen;
    if (!panel.open) panel.showModal();
  }
  document.querySelector('.pod-page [role="alert"]')?.focus?.({ preventScroll: true });
});

document.body.addEventListener("pod-config-saved", () => { refreshPending = true; });
document.body.addEventListener("htmx:afterSettle", (event) => {
  if (!refreshPending || !event.detail.target?.matches?.("#pod-variant-drawer")) return;
  refreshPending = false;
  const workspace = document.querySelector(workspaceSelector);
  if (workspace) window.htmx.ajax("GET", location.href, {
    target: workspace, select: workspaceSelector, swap: "outerHTML show:none",
  });
});
document.body.addEventListener("htmx:sendError", (event) => {
  if (event.detail.elt?.closest(workspaceSelector)) {
    notifyError("Connexion interrompue. Vérifiez le résultat avant de réessayer une action de production.");
  }
});
document.body.addEventListener("htmx:afterRequest", (event) => {
  const form = event.detail.elt?.closest?.(".pod-page form");
  form?.querySelectorAll('[aria-busy="true"]').forEach((button) => {
    button.removeAttribute("aria-busy");
    button.classList.remove("is-loading");
  });
  const scope = event.detail.target;
  if (scope?.closest?.(".pod-page")) {
    scope.classList.remove("is-loading");
    scope.removeAttribute("aria-busy");
  }
});
document.body.addEventListener("htmx:historyRestore", enhancePodWorkspace);
enhancePodWorkspace();
