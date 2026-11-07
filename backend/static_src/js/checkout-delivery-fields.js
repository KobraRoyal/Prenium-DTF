/** Champs livraison checkout — validation visuelle partagée (studio + fichier). */

export const CHECKOUT_DELIVERY_BASE_FIELDS = [
  "shipping_contact_name",
  "shipping_email",
  "shipping_phone",
  "shipping_house_number",
];

export const CHECKOUT_DELIVERY_OTHER_FIELDS = [
  "shipping_address_line1",
  "shipping_postal_code",
  "shipping_city",
];

const FIELD_MISSING_MESSAGES = {
  shipping_contact_name: "Indiquez le destinataire.",
  shipping_email: "Indiquez l’email de suivi.",
  shipping_phone: "Indiquez le numéro de téléphone.",
  shipping_house_number: "Indiquez le n° de voie.",
  shipping_address_line1: "Indiquez la voie.",
  shipping_postal_code: "Indiquez le code postal.",
  shipping_city: "Indiquez la ville.",
};

const EMAIL_INVALID_MESSAGE = "Indiquez un email valide.";

export function checkoutDeliveryRequiredNames({ other = false } = {}) {
  const names = [...CHECKOUT_DELIVERY_BASE_FIELDS];
  if (other) names.push(...CHECKOUT_DELIVERY_OTHER_FIELDS);
  return names;
}

export function checkoutDeliveryToastMessage({ other = false } = {}) {
  return other
    ? "Complétez les champs obligatoires pour l’expédition."
    : "Indiquez le destinataire, l’email, le téléphone et le n° de voie.";
}

function deliveryField(form, name) {
  const node = form.querySelector(`[name='${name}']`);
  return node instanceof HTMLInputElement || node instanceof HTMLSelectElement ? node : null;
}

function ensureErrorNode(field) {
  const group = field.closest(".ui-field-group");
  if (!(group instanceof HTMLElement)) return null;
  let errorNode =
    group.querySelector("[data-checkout-field-error]") ||
    group.querySelector(".ui-error-text");
  if (!(errorNode instanceof HTMLElement)) {
    errorNode = document.createElement("p");
    errorNode.className = "ui-error-text";
    errorNode.dataset.checkoutFieldError = "";
    errorNode.hidden = true;
    group.appendChild(errorNode);
  }
  if (!errorNode.id) {
    errorNode.id = `${field.id || field.name || "checkout-field"}-error`;
  }
  const describedBy = (field.getAttribute("aria-describedby") || "")
    .split(/\s+/)
    .filter(Boolean);
  if (!describedBy.includes(errorNode.id)) {
    field.setAttribute("aria-describedby", [...describedBy, errorNode.id].join(" "));
  }
  return errorNode;
}

export function setCheckoutDeliveryFieldInvalid(field, message) {
  if (!(field instanceof HTMLInputElement || field instanceof HTMLSelectElement)) return;
  const invalid = Boolean(message);
  field.classList.toggle("ui-input--error", invalid);
  if (invalid) {
    field.setAttribute("aria-invalid", "true");
  } else {
    field.removeAttribute("aria-invalid");
  }
  const group = field.closest(".ui-field-group");
  if (group instanceof HTMLElement) {
    group.classList.toggle("is-invalid", invalid);
  }
  const errorNode = ensureErrorNode(field);
  if (!(errorNode instanceof HTMLElement)) return;
  if (invalid) {
    errorNode.textContent = message;
    errorNode.hidden = false;
  } else {
    errorNode.textContent = "";
    errorNode.hidden = true;
  }
}

export function clearCheckoutDeliveryFieldInvalid(field) {
  setCheckoutDeliveryFieldInvalid(field, "");
}

export function clearCheckoutDeliveryErrors(form) {
  if (!(form instanceof HTMLFormElement)) return;
  form
    .querySelectorAll(
      "[data-studio-delivery] input, [data-studio-delivery] select, [data-file-checkout-delivery] input, [data-file-checkout-delivery] select",
    )
    .forEach((node) => {
      if (node instanceof HTMLInputElement || node instanceof HTMLSelectElement) {
        clearCheckoutDeliveryFieldInvalid(node);
      }
    });
}

export function syncCheckoutDeliveryRequiredMarks(form, { pickup = false, other = false } = {}) {
  if (!(form instanceof HTMLFormElement)) return;
  const required = new Set(pickup ? [] : checkoutDeliveryRequiredNames({ other }));
  form.querySelectorAll("[data-checkout-req-for]").forEach((mark) => {
    if (!(mark instanceof HTMLElement)) return;
    const name = mark.dataset.checkoutReqFor || "";
    const show = required.has(name);
    mark.hidden = !show;
    const group = mark.closest(".ui-field-group");
    if (group instanceof HTMLElement) {
      group.toggleAttribute("data-checkout-required", show);
    }
  });
}

export function highlightCheckoutDeliveryErrors(
  form,
  { requiredNames, emailInvalid = false } = {},
) {
  if (!(form instanceof HTMLFormElement)) return null;
  clearCheckoutDeliveryErrors(form);
  let firstInvalid = null;
  for (const name of requiredNames || []) {
    const field = deliveryField(form, name);
    if (!field || field.disabled) continue;
    if (field.value.trim()) continue;
    setCheckoutDeliveryFieldInvalid(
      field,
      FIELD_MISSING_MESSAGES[name] || "Champ obligatoire.",
    );
    if (!firstInvalid) firstInvalid = field;
  }
  const email = deliveryField(form, "shipping_email");
  if (emailInvalid && email) {
    setCheckoutDeliveryFieldInvalid(email, EMAIL_INVALID_MESSAGE);
    if (!firstInvalid) firstInvalid = email;
  }
  if (firstInvalid instanceof HTMLElement) {
    firstInvalid.focus({ preventScroll: true });
    firstInvalid.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  return firstInvalid;
}

export function validateCheckoutDeliveryFields(form, { other = false } = {}) {
  const requiredNames = checkoutDeliveryRequiredNames({ other });
  const email = deliveryField(form, "shipping_email");
  const emailInvalid = Boolean(
    email && email.value.trim() && !email.value.includes("@"),
  );
  const missing = requiredNames.some((name) => {
    const field = deliveryField(form, name);
    return !field || !field.value.trim();
  });
  if (!missing && !emailInvalid) {
    clearCheckoutDeliveryErrors(form);
    return { ok: true, requiredNames, emailInvalid: false };
  }
  highlightCheckoutDeliveryErrors(form, { requiredNames, emailInvalid });
  return { ok: false, requiredNames, emailInvalid };
}

export function bindCheckoutDeliveryFieldFeedback(form) {
  if (!(form instanceof HTMLFormElement) || form.dataset.checkoutDeliveryFeedback === "true") {
    return;
  }
  form.dataset.checkoutDeliveryFeedback = "true";
  const refresh = (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) return;
    if (!target.name || !target.name.startsWith("shipping_")) return;
    if (target.getAttribute("aria-invalid") !== "true") return;
    if (target.name === "shipping_email" && target.value.trim() && !target.value.includes("@")) {
      setCheckoutDeliveryFieldInvalid(target, EMAIL_INVALID_MESSAGE);
      return;
    }
    if (target.required && !target.value.trim()) {
      setCheckoutDeliveryFieldInvalid(
        target,
        FIELD_MISSING_MESSAGES[target.name] || "Champ obligatoire.",
      );
      return;
    }
    clearCheckoutDeliveryFieldInvalid(target);
  };
  form.addEventListener("input", refresh);
  form.addEventListener("change", refresh);
}
