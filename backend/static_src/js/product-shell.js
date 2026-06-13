function initProductMenuFallback() {
  document.querySelectorAll("[data-product-menu-toggle]").forEach((button) => {
    const targetId = button.getAttribute("aria-controls");
    const menu = targetId ? document.getElementById(targetId) : null;

    if (!menu || button.dataset.productMenuReady === "true") {
      return;
    }

    button.dataset.productMenuReady = "true";

    const setOpen = (open) => {
      menu.classList.toggle("is-open", open);
      button.setAttribute("aria-expanded", open ? "true" : "false");
    };

    button.addEventListener("click", () => {
      setOpen(button.getAttribute("aria-expanded") !== "true");
    });

    menu.addEventListener("click", (event) => {
      const target = event.target;
      if (target instanceof Element && target.closest("a, button[type='submit']")) {
        setOpen(false);
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    });
  });
}

function initSubmitLoadingState() {
  document.querySelectorAll("form[data-submit-loading]").forEach((form) => {
    if (form.dataset.submitLoadingReady === "true") {
      return;
    }

    form.dataset.submitLoadingReady = "true";
    form.addEventListener("submit", () => {
      const submitter = form.querySelector("[type='submit']");
      if (submitter instanceof HTMLButtonElement) {
        submitter.classList.add("is-loading");
        submitter.setAttribute("aria-busy", "true");
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initProductMenuFallback();
  initSubmitLoadingState();
});

document.body.addEventListener("htmx:afterSwap", () => {
  initProductMenuFallback();
  initSubmitLoadingState();
});
