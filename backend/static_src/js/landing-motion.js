/**
 * Révélations au scroll sur la landing marketing.
 * Le contenu reste visible si IntersectionObserver ou les animations ne sont pas disponibles.
 */
function revealElement(el) {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      el.classList.add("is-visible");
    });
  });
}

function initLandingReveal() {
  const root = document.querySelector(".landing-main");
  if (!root) {
    return;
  }

  const nodes = root.querySelectorAll(".landing-reveal, .landing-hero--animate");
  if (!nodes.length) {
    return;
  }

  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || !("IntersectionObserver" in window)) {
    nodes.forEach((el) => el.classList.add("is-visible"));
    return;
  }

  document.documentElement.classList.add("js-landing-motion");

  const io = new IntersectionObserver(
    (entries, obs) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) {
          return;
        }
        obs.unobserve(entry.target);
        revealElement(entry.target);
      });
    },
    { root: null, rootMargin: "0px 0px -2% 0px", threshold: 0.01 }
  );

  nodes.forEach((el) => io.observe(el));
}

function initLandingMenuFallback() {
  document.querySelectorAll("[data-landing-menu-toggle]").forEach((button) => {
    const targetId = button.getAttribute("data-landing-menu-toggle");
    const target = targetId ? document.getElementById(targetId) : null;
    if (!target) {
      return;
    }

    button.addEventListener("click", () => {
      const isOpen = target.classList.toggle("is-open");
      button.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });

    target.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        target.classList.remove("is-open");
        button.setAttribute("aria-expanded", "false");
      });
    });
  });
}

function initLandingUI() {
  initLandingReveal();
  initLandingMenuFallback();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initLandingUI);
} else {
  initLandingUI();
}
