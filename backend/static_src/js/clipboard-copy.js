async function copyText(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.append(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) {
    throw new Error("Clipboard copy failed");
  }
}

document.addEventListener("click", async (event) => {
  if (!(event.target instanceof Element)) {
    return;
  }
  const button = event.target.closest("[data-clipboard-copy]");
  if (!(button instanceof HTMLButtonElement) || button.disabled) {
    return;
  }

  const value = button.dataset.copyValue?.trim();
  if (!value) {
    return;
  }

  const idleLabel = button.getAttribute("aria-label") || "Copier";
  const successMessage = button.dataset.copySuccess || "Copié dans le presse-papiers.";
  try {
    await copyText(value);
    button.classList.add("is-copied");
    button.setAttribute("aria-label", successMessage);
    if (typeof window.preniumToast === "function") {
      window.preniumToast(successMessage, "success");
    }
    window.setTimeout(() => {
      button.classList.remove("is-copied");
      button.setAttribute("aria-label", idleLabel);
    }, 1600);
  } catch {
    if (typeof window.preniumToast === "function") {
      window.preniumToast("Copie impossible — réessayez.", "error");
    }
  }
});
