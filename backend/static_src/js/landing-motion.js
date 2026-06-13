/**
 * Révélations au scroll sur la landing (IntersectionObserver).
 * Double requestAnimationFrame avant .is-visible pour forcer les transitions CSS.
 * Chargé depuis app.js pour garder un point d'entrée JS unique.
 */
function revealElement(el) {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      el.classList.add("is-visible");
    });
  });
}

function initLandingReveal() {
  const root = document.querySelector(".landing-main, .landing-saas-main");
  if (!root) {
    return;
  }

  const nodes = root.querySelectorAll(".landing-reveal, .landing-hero--animate");
  if (!nodes.length) {
    return;
  }

  document.documentElement.classList.add("js-landing-motion");

  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) {
    nodes.forEach((el) => el.classList.add("is-visible"));
    return;
  }

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

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initLandingReveal);
} else {
  initLandingReveal();
}
