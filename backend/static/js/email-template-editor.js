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

function normalizeSearchText(value) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function updateTokenFilter(scope) {
  const search = scope.querySelector("[data-email-token-search]");
  const tokens = [...scope.querySelectorAll("[data-email-template-token]")];
  const count = scope.querySelector("[data-email-token-count]");
  const empty = scope.querySelector("[data-email-token-empty]");
  if (!(search instanceof HTMLInputElement)) {
    return;
  }

  const query = normalizeSearchText(search.value);
  let visibleCount = 0;
  tokens.forEach((token) => {
    const haystack = normalizeSearchText(token.dataset.emailTokenSearchText || "");
    const isVisible = !query || haystack.includes(query);
    token.hidden = !isVisible;
    visibleCount += isVisible ? 1 : 0;
  });

  if (count) {
    count.textContent = `${visibleCount} tag${visibleCount > 1 ? "s" : ""}`;
  }
  if (empty) {
    empty.hidden = visibleCount !== 0;
  }
}

function initEmailTemplateEditor() {
  document.querySelectorAll("[data-email-template-editor-scope]").forEach((scope) => {
    if (!(scope instanceof HTMLElement) || scope.dataset.emailEditorReady === "true") {
      return;
    }
    scope.dataset.emailEditorReady = "true";

    const form = scope.querySelector("[data-email-template-editor]");
    const subject = scope.querySelector("#id_subject_template");
    const subjectCounter = scope.querySelector("[data-email-subject-counter]");
    const editorState = scope.querySelector("[data-email-editor-state]");
    const search = scope.querySelector("[data-email-token-search]");

    const updateSubjectCounter = () => {
      if (subject instanceof HTMLInputElement && subjectCounter) {
        subjectCounter.textContent = `${subject.value.length} / ${subject.maxLength}`;
      }
    };
    const markDirty = () => {
      if (editorState) {
        editorState.textContent = "À enregistrer";
        editorState.classList.add("is-dirty");
      }
    };

    if (form instanceof HTMLFormElement) {
      form.addEventListener("input", (event) => {
        updateSubjectCounter();
        if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
          markDirty();
        }
      });
      form.addEventListener("change", markDirty);
    }

    if (search instanceof HTMLInputElement) {
      search.addEventListener("input", () => updateTokenFilter(scope));
      search.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && search.value) {
          search.value = "";
          updateTokenFilter(scope);
        }
      });
    }

    scope.querySelectorAll("[data-email-template-token]").forEach((button) => {
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }
      button.addEventListener("click", () => {
        if (!button.disabled) {
          insertTemplateToken(button);
        }
      });
    });

    updateSubjectCounter();
    updateTokenFilter(scope);
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initEmailTemplateEditor);
} else {
  initEmailTemplateEditor();
}

document.body.addEventListener("htmx:afterSwap", initEmailTemplateEditor);
