function findLocalFeedbackRoot(target) {
  if (!target || !(target instanceof HTMLElement)) {
    return null;
  }
  return target.closest(".workflow-panel, .workflow-panel-shell, .dui-card, .prospect-form, .prospect-tunnel__form-wrap") || target;
}

function clearLocalFeedback(root) {
  if (!root) {
    return;
  }
  root.querySelectorAll(".ui-local-feedback").forEach((node) => node.remove());
}

function pushLocalFeedback(target, message, variant = "info") {
  const root = findLocalFeedbackRoot(target);
  if (!root || !message) {
    return;
  }
  clearLocalFeedback(root);
  const box = document.createElement("div");
  box.className = `ui-local-feedback ui-local-feedback--${variant}`;
  box.setAttribute("role", variant === "error" ? "alert" : "status");
  const text = document.createElement("p");
  text.textContent = message;
  box.append(text);
  root.prepend(box);
  if (variant !== "error") {
    window.setTimeout(() => {
      box.classList.add("is-fading");
      window.setTimeout(() => box.remove(), 220);
    }, 2400);
  }
}

document.body.addEventListener("htmx:afterRequest", (event) => {
  const xhr = event.detail.xhr;
  if (!xhr || typeof window.preniumToast !== "function") {
    return;
  }
  const raw = xhr.getResponseHeader("X-Prenium-Toast");
  if (!raw) {
    return;
  }
  const ok = xhr.status >= 200 && xhr.status < 300;
  try {
    const data = JSON.parse(raw);
    const variant = data.variant || (ok ? "success" : "error");
    const message = data.message || raw;
    window.preniumToast(message, variant);
    pushLocalFeedback(event.detail.target, message, variant);
  } catch {
    const variant = ok ? "info" : "error";
    window.preniumToast(raw, variant);
    pushLocalFeedback(event.detail.target, raw, variant);
  }
});

document.body.addEventListener("htmx:responseError", (event) => {
  pushLocalFeedback(event.detail.target, "Une erreur est survenue pendant l'action demandée.", "error");
});
