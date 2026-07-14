function insertTemplateToken(button) {
  const scope = button.closest("[data-email-template-editor-scope]");
  const form = scope?.querySelector("[data-email-template-editor]");
  if (!form) {
    return;
  }
  const activeElement = document.activeElement;
  const subject = form.querySelector("#id_subject_template");
  const body = form.querySelector("#id_body_template");
  const field = activeElement === subject || activeElement === body ? activeElement : body;
  if (!(field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement)) {
    return;
  }
  const token = button.dataset.emailTemplateToken || "";
  const start = field.selectionStart ?? field.value.length;
  const end = field.selectionEnd ?? start;
  field.setRangeText(token, start, end, "end");
  field.focus();
  field.dispatchEvent(new Event("input", { bubbles: true }));
  if (typeof window.preniumToast === "function") {
    window.preniumToast(`Tag ${token} inséré`, "success");
  }
}

function initEmailTemplateEditor() {
  document.querySelectorAll("[data-email-template-token]").forEach((button) => {
    if (!(button instanceof HTMLButtonElement) || button.dataset.tokenInsertReady === "true") {
      return;
    }
    button.dataset.tokenInsertReady = "true";
    button.addEventListener("click", () => {
      if (!button.disabled) {
        insertTemplateToken(button);
      }
    });
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initEmailTemplateEditor);
} else {
  initEmailTemplateEditor();
}

document.body.addEventListener("htmx:afterSwap", initEmailTemplateEditor);
