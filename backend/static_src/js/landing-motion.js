/**
 * Motion landing marketing — Kinetic Brutalism.
 * Contenu toujours lisible ; motion = enhancement (transform / clip-path).
 * Respecte prefers-reduced-motion.
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
    { root: null, rootMargin: "0px 0px -10% 0px", threshold: 0.14 }
  );

  nodes.forEach((el) => io.observe(el));
}

function initLandingHeaderState() {
  const header = document.querySelector(".agency-header");
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

function initLandingBoardTilt() {
  const board = document.querySelector(".conversion-board");
  if (!board) {
    return;
  }

  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const finePointer = window.matchMedia("(pointer: fine)").matches;
  if (reduce || !finePointer) {
    return;
  }

  let frame = 0;
  let ready = false;

  const arm = () => {
    ready = true;
  };

  board.addEventListener(
    "animationend",
    (event) => {
      if (event.animationName === "conversion-board-in") {
        arm();
      }
    },
    { once: true }
  );
  window.setTimeout(arm, 1100);

  const onMove = (event) => {
    if (!ready) {
      return;
    }
    const rect = board.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width - 0.5;
    const y = (event.clientY - rect.top) / rect.height - 0.5;
    if (frame) {
      cancelAnimationFrame(frame);
    }
    frame = requestAnimationFrame(() => {
      board.classList.add("is-tilting");
      board.style.transform = `rotate(${1.25 + x * 2}deg) translate3d(${x * 10}px, ${y * 8}px, 0)`;
    });
  };

  const onLeave = () => {
    if (frame) {
      cancelAnimationFrame(frame);
    }
    board.classList.remove("is-tilting");
    board.style.transform = "";
  };

  board.addEventListener("pointermove", onMove);
  board.addEventListener("pointerleave", onLeave);
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
  initLandingBoardTilt();
  initLandingSmoothAnchors();
  initLandingMenuFallback();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initLandingUI);
} else {
  initLandingUI();
}
