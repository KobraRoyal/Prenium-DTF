/**
 * Motion landing marketing — Kinetic Brutalism.
 * Contenu toujours lisible ; motion = enhancement (transform / clip-path).
 * Respecte prefers-reduced-motion.
 */

function initLandingReveal() {
  const root = document.querySelector(".landing-main");
  if (!root) {
    return;
  }

  const nodes = root.querySelectorAll(".landing-reveal, .landing-hero--animate");
  if (!nodes.length) {
    return;
  }

  // Le contenu reste visible dès le premier rendu. Les animations du hero et
  // l'état du header restent des améliorations progressives indépendantes.
  nodes.forEach((el) => el.classList.add("is-visible"));
}

function initLandingHeaderState() {
  const header = document.querySelector(".marketing-header, .product-header");
  const hero = document.querySelector("#landing-hero");
  if (!header || !hero || !("IntersectionObserver" in window)) {
    return;
  }

  const observer = new IntersectionObserver(
    ([entry]) => {
      header.classList.toggle("is-scrolled", entry.intersectionRatio < 0.18);
    },
    { threshold: [0, 0.18, 1] }
  );

  observer.observe(hero);
}

function initLandingSmoothAnchors() {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) {
    return;
  }

  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    const id = link.getAttribute("href");
    if (!id || id === "#") {
      return;
    }
    const target = document.querySelector(id);
    if (!target) {
      return;
    }
    link.addEventListener("click", (event) => {
      event.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      history.pushState(null, "", id);
    });
  });
}

function initLandingMenuFallback() {
  document
    .querySelectorAll("[data-landing-menu-toggle]:not([data-product-menu-toggle])")
    .forEach((button) => {
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
  initLandingHeaderState();
  initLandingSmoothAnchors();
  initLandingMenuFallback();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initLandingUI);
} else {
  initLandingUI();
}
