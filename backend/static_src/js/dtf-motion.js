/* Taste motion layer. HTML is always visible; animations only add arrival. */
export function createMotion(
  media = matchMedia("(prefers-reduced-motion: reduce)"),
) {
  const active = new Map();
  const curve = "cubic-bezier(.16,1,.3,1)";
  function enter(element, { kind = "text", delay = 0, duration = 560 } = {}) {
    if (!element || element.hidden || !element.animate) return;
    active.get(element)?.cancel();
    if (media.matches || document.hidden) return;
    const from =
      kind === "media"
        ? { opacity: 0.55, transform: "translateY(14px) scale(.99)" }
        : kind === "panel"
          ? { opacity: 0.4, transform: "translateY(6px)" }
          : kind === "tooltip"
            ? { opacity: 0.35, transform: "translateY(3px)" }
            : { opacity: 0.45, transform: "translateY(18px)" };
    const animation = element.animate(
      [from, { opacity: 1, transform: "none" }],
      {
        duration,
        delay,
        easing: curve,
        fill: "backwards",
      },
    );
    active.set(element, animation);
    element.dataset.motionPlayed = "true";
    const clear = () => {
      if (active.get(element) === animation) active.delete(element);
    };
    animation.onfinish = clear;
    animation.oncancel = clear;
  }
  function settle() {
    for (const animation of active.values()) animation.cancel();
    active.clear();
  }
  media.addEventListener("change", () => {
    if (media.matches) settle();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) settle();
  });
  function revealPage() {
    const hero = document.querySelector(".dtf-hero");
    hero
      .querySelectorAll("[data-hero-line]")
      .forEach((line, i) => enter(line, { delay: i * 75, duration: 650 }));
    [
      ".dtf-lead",
      ".dtf-hero__description",
      ".dtf-actions",
      ".dtf-hero__access",
    ].forEach((selector, i) =>
      enter(hero.querySelector(selector), {
        delay: 90 + i * 60,
        duration: 560,
      }),
    );
    enter(hero.querySelector(".dtf-transfer-visual"), {
      kind: "media",
      delay: 80,
      duration: 700,
    });
    if (!("IntersectionObserver" in window) || media.matches) return;
    const targets = new Map();
    function add(section, selector, kind, delay) {
      const element = section.querySelector(selector);
      if (element) targets.set(element, { kind, delay });
    }
    for (const section of document.querySelectorAll(
      "main > section:not(.dtf-hero)",
    )) {
      add(section, "h2", "text", 0);
      add(
        section,
        ".dtf-section-head > p, .dtf-gamut__copy > p, .dtf-detail-copy > p, .dtf-workshop__copy > p",
        "text",
        70,
      );
      const mediaSelector =
        ".dtf-gamut-diagram, [data-preparation-carousel], .dtf-comparison, .dtf-textile__layout, .dtf-alpha-workspace, .dtf-gallery__grid, .dtf-ordering-demo, .dtf-pricing__layout, .dtf-workshop__photo, .dtf-faq__list, .dtf-final .dtf-button";
      add(section, mediaSelector, "media", 110);
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          observer.unobserve(entry.target);
          enter(entry.target, { ...targets.get(entry.target), duration: 680 });
        }
      },
      { threshold: 0.08, rootMargin: "0px 0px -3% 0px" },
    );
    for (const element of targets.keys()) observer.observe(element);
    media.addEventListener("change", () => {
      if (media.matches) observer.disconnect();
    });
    document.querySelectorAll("details").forEach((details) => {
      details.addEventListener("toggle", () => {
        if (details.open)
          enter(details.querySelector("summary + div"), {
            kind: "panel",
            duration: 260,
          });
      });
    });
  }
  return { enter, settle, revealPage };
}
