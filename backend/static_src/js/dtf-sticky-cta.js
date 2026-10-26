/** Mobile access bar: shown while scrolling back up, past the hero, when no other access action is on screen. */
const bar = document.querySelector("[data-sticky-cta]");
const SCROLL_INTENT_PX = 12;

if (bar && "IntersectionObserver" in window) {
  const anchors = [
    ...document.querySelectorAll("main .dtf-button, .dtf-header .dtf-button"),
  ];
  const hero = document.querySelector(".dtf-hero");
  const visible = new Set();
  let pastHero = false;
  let scrollingUp = false;
  let lastY = window.scrollY;

  const render = () => {
    const show = pastHero && scrollingUp && visible.size === 0;
    bar.classList.toggle("is-visible", show);
    bar.inert = !show;
  };

  const anchorObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) visible.add(entry.target);
      else visible.delete(entry.target);
    });
    render();
  });
  anchors.forEach((anchor) => anchorObserver.observe(anchor));

  if (hero) {
    new IntersectionObserver(([entry]) => {
      pastHero = !entry.isIntersecting && entry.boundingClientRect.top < 0;
      render();
    }).observe(hero);
  }

  window.addEventListener(
    "scroll",
    () => {
      const y = window.scrollY;
      if (Math.abs(y - lastY) < SCROLL_INTENT_PX) return;
      const up = y < lastY;
      lastY = y;
      if (up !== scrollingUp) {
        scrollingUp = up;
        render();
      }
    },
    { passive: true },
  );
  render();
  bar.hidden = false;
}
