function productMenuForButton(button) {
  const targetId = button.getAttribute("aria-controls");
  return targetId ? document.getElementById(targetId) : null;
}

function productMenuButtonForMenu(menu) {
  if (!menu.id) {
    return null;
  }

  return document.querySelector(
    `[data-product-menu-toggle][aria-controls="${menu.id}"]`
  );
}

function setProductMenuOpen(button, menu, open) {
  menu.classList.toggle("is-open", open);
  button.setAttribute("aria-expanded", open ? "true" : "false");

  if (!open) {
    menu.querySelectorAll("[data-product-nav-details][open]").forEach((details) => {
      details.removeAttribute("open");
    });
  }

  const label = open ? button.dataset.menuCloseLabel : button.dataset.menuOpenLabel;
  if (label) {
    button.setAttribute("aria-label", label);
  }
}

function closeProductMenus(exceptMenu = null) {
  document.querySelectorAll("[data-product-menu].is-open").forEach((menu) => {
    if (menu === exceptMenu) {
      return;
    }

    const button = productMenuButtonForMenu(menu);
    if (button) {
      setProductMenuOpen(button, menu, false);
      return;
    }

    menu.classList.remove("is-open");
  });
}

function closeProductNavDetails(exceptDetails = null, restoreFocus = false) {
  document.querySelectorAll("[data-product-nav-details][open]").forEach((details) => {
    if (details === exceptDetails) {
      return;
    }

    const summary = details.querySelector("summary");
    const containedFocus = details.contains(document.activeElement);
    details.removeAttribute("open");
    if (restoreFocus && containedFocus && summary instanceof HTMLElement) {
      summary.focus();
    }
  });
}

function initProductMenuFallback() {
  document.querySelectorAll("[data-product-menu-toggle]").forEach((button) => {
    const menu = productMenuForButton(button);
    if (!menu) {
      return;
    }

    button.dataset.productMenuReady = "true";
    setProductMenuOpen(button, menu, menu.classList.contains("is-open"));
  });

  if (document.documentElement.dataset.productMenuGlobalReady === "true") {
    return;
  }

  document.documentElement.dataset.productMenuGlobalReady = "true";

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }

    const button = target.closest("[data-product-menu-toggle]");
    if (button) {
      const menu = productMenuForButton(button);
      if (!menu) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();
      const shouldOpen = button.getAttribute("aria-expanded") !== "true";
      closeProductMenus(menu);
      setProductMenuOpen(button, menu, shouldOpen);
      return;
    }

    const detailsSummary = target.closest("[data-product-nav-details] > summary");
    if (detailsSummary) {
      const details = detailsSummary.parentElement;
      if (details instanceof HTMLDetailsElement) {
        closeProductNavDetails(details);
      }
      return;
    }

    if (target.closest("[data-product-menu] a, [data-product-menu] button[type='submit']")) {
      closeProductNavDetails();
      closeProductMenus();
      return;
    }

    if (!target.closest("[data-product-nav-details]")) {
      closeProductNavDetails();
    }

    if (!target.closest("[data-product-menu].is-open")) {
      closeProductMenus();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeProductNavDetails(null, true);
      closeProductMenus();
    }
  });
}

const INLINE_REQUIRED_MISSING = "Renseignez ce champ.";
const INLINE_REQUIRED_INVALID = "Indiquez une valeur valide.";

function isInlineRequiredField(field) {
  if (
    !(
      field instanceof HTMLInputElement ||
      field instanceof HTMLSelectElement ||
      field instanceof HTMLTextAreaElement
    )
  ) {
    return false;
  }
  if (!field.required || field.disabled || field.type === "hidden") {
    return false;
  }
  return true;
}

function inlineRequiredMessage(field) {
  if (field.validity.valueMissing) {
    return field.dataset.missingMessage || INLINE_REQUIRED_MISSING;
  }
  if (field.validity.typeMismatch) {
    return field.dataset.invalidMessage || INLINE_REQUIRED_INVALID;
  }
  return "";
}

function inlineRequiredErrorElement(field) {
  const describedBy = field.getAttribute("aria-describedby") || "";
  for (const id of describedBy.split(/\s+/)) {
    if (!id) {
      continue;
    }
    const candidate = document.getElementById(id);
    if (candidate?.classList.contains("ui-error-text")) {
      return candidate;
    }
  }
  return field.closest(".ui-field-group")?.querySelector(".ui-error-text") || null;
}

function setInlineRequiredError(field, message) {
  const errorNode = inlineRequiredErrorElement(field);
  const invalid = Boolean(message);

  field.classList.toggle("ui-input--error", invalid);
  if (invalid) {
    field.setAttribute("aria-invalid", "true");
  } else {
    field.removeAttribute("aria-invalid");
  }

  if (!errorNode) {
    return;
  }

  if (invalid) {
    errorNode.textContent = message;
    errorNode.removeAttribute("hidden");
  } else {
    errorNode.textContent = "";
    errorNode.setAttribute("hidden", "");
  }
}

function syncInlineRequiredField(field) {
  if (!isInlineRequiredField(field)) {
    return "";
  }
  const message = inlineRequiredMessage(field);
  setInlineRequiredError(field, message);
  return message;
}

function validateInlineRequiredForm(form) {
  const fields = [...form.elements].filter(isInlineRequiredField);
  let firstInvalid = null;

  for (const field of fields) {
    if (syncInlineRequiredField(field) && !firstInvalid) {
      firstInvalid = field;
    }
  }

  if (firstInvalid) {
    const alert = form
      .closest(".product-auth-card, .product-login-card")
      ?.querySelector(".alert--danger");
    if (alert instanceof HTMLElement) {
      alert.hidden = true;
    }
    firstInvalid.focus();
    return false;
  }

  return true;
}

function bindInlineRequiredForm(form) {
  if (form.dataset.inlineRequiredReady === "true") {
    return;
  }

  form.dataset.inlineRequiredReady = "true";
  form.addEventListener("input", (event) => {
    const field = event.target;
    if (isInlineRequiredField(field) && field.getAttribute("aria-invalid") === "true") {
      syncInlineRequiredField(field);
    }
  });
  form.addEventListener("change", (event) => {
    const field = event.target;
    if (isInlineRequiredField(field) && field.getAttribute("aria-invalid") === "true") {
      syncInlineRequiredField(field);
    }
  });
  form.addEventListener("submit", (event) => {
    if (event.submitter?.hasAttribute("formnovalidate")) {
      return;
    }
    if (!validateInlineRequiredForm(form)) {
      event.preventDefault();
    }
  });
}

function initInlineRequiredValidation() {
  document.querySelectorAll("form[data-inline-required]").forEach(bindInlineRequiredForm);
}

function initSubmitLoadingState() {
  document.querySelectorAll("form[data-submit-loading]").forEach((form) => {
    if (form.dataset.submitLoadingReady === "true") {
      return;
    }

    form.dataset.submitLoadingReady = "true";
    form.addEventListener("submit", (event) => {
      if (event.defaultPrevented || event.submitter?.hasAttribute("formnovalidate")) {
        return;
      }
      if (form.hasAttribute("data-inline-required") && !validateInlineRequiredForm(form)) {
        event.preventDefault();
        return;
      }
      const submitter = event.submitter || form.querySelector("[type='submit']");
      if (submitter instanceof HTMLButtonElement) {
        submitter.classList.add("is-loading");
        submitter.setAttribute("aria-busy", "true");
      }
    });
  });
}

function initProductShell() {
  initProductMenuFallback();
  initInlineRequiredValidation();
  initSubmitLoadingState();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initProductShell);
} else {
  initProductShell();
}

document.body.addEventListener("htmx:afterSwap", initProductShell);
