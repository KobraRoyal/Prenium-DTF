import { createMotionScene } from "./dtf-motion-scene.js?v=20261025e";

const inks = ["orange", "green", "red", "blue"];
const extendedCopy = "8 couleurs : l’orange, le vert, le rouge et le bleu complètent la base CMJN.";
const baseCopy = "Base CMJN : cyan, magenta, jaune et noir. Les encres complémentaires sont masquées dans ce schéma.";

function loadEngine() {
  if (window.gsap) return Promise.resolve(window.gsap);
  return new Promise((resolve, reject) => {
    // The distributed GSAP core is UMD, so load it as a classic local script.
    const script = document.createElement("script");
    script.src = new URL("../vendor/gsap/gsap-3.15.0.min.js", import.meta.url).href;
    script.async = true;
    script.onload = () => resolve(window.gsap);
    script.onerror = () => reject(new Error("Motion library unavailable"));
    document.head.append(script);
  });
}

// The two outlines have matching authored points: a deterministic SVG morph,
// not a measured color-space comparison. No random values or looping tweens.
export function buildGamutTimeline(gsap, root) {
  const base = root.querySelector("#gamut-base-path").getAttribute("d");
  const outer = root.querySelector("#gamut-extended-path").getAttribute("d");
  const envelope = root.querySelector("#gamut-envelope-path");
  const boundary = root.querySelector("#gamut-extended-path");
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(envelope, { attr: { d: base } }, {
    attr: { d: outer }, duration: 1.25, ease: "sine.inOut",
  }, 1.3);
  tl.fromTo(boundary, { attr: { d: base }, strokeDasharray: 1, strokeDashoffset: 1 }, {
    attr: { d: base }, strokeDashoffset: 0, duration: 0.85, ease: "expo.out",
  }, 0.2);
  tl.to(boundary, { attr: { d: outer }, duration: 1.25, ease: "sine.inOut" }, 1.3);
  inks.forEach((ink, i) => {
    const label = root.querySelector(`[data-gamut-label="${ink}"]`);
    const at = 1.9 + i * 0.6;
    tl.fromTo(label, { opacity: 0, y: 5 }, {
      opacity: 1, y: 0, duration: 0.45, ease: "power3.out",
    }, at);
  });
  tl.to({}, { duration: 1.75 }, 4.65);
  tl.seek(0);
  return tl;
}

export function buildAnalysisTimeline(gsap, root) {
  const line = root.querySelector(".dtf-scan-line");
  const tl = gsap.timeline({ paused: true });
  tl.fromTo(line, { yPercent: 0 }, {
    yPercent: 100, duration: 2.1, ease: "none",
  }, 0.25);
  tl.fromTo(line, { opacity: 0 }, {
    opacity: 0.75, duration: 0.18, ease: "power1.out",
  }, 0.25);
  tl.to(line, { opacity: 0, duration: 0.2, ease: "power1.in" }, 2.15);
  ["edge", "detail", "alpha"].forEach((name, i) => {
    const mark = root.querySelector(`#analysis-detect-${name}`);
    const at = 1 + i * 0.45;
    tl.fromTo(mark, { opacity: 0, strokeDasharray: 1, strokeDashoffset: 1 }, {
      opacity: 1, strokeDashoffset: 0, duration: 0.5, ease: "circ.out",
    }, at);
    tl.to(mark, { opacity: 0, duration: 0.2, ease: "power2.in" }, 2.65);
  });
  tl.seek(0);
  return tl;
}

export function initDtfChoreography(gamut, analysis, media) {
  const buttons = [...gamut.querySelectorAll("[data-gamut-mode]")];
  const svg = gamut.querySelector("[data-gamut-view]");
  const legend = gamut.querySelector("[data-gamut-explanation]");
  const control = gamut.querySelector("[data-gamut-play]");
  const fullEnvelope = gamut.querySelector("#gamut-envelope-path").getAttribute("d");
  let gamutScene, analysisScene;
  let manualMode = null;
  let analysisTouched = false;
  let loading = false;
  const mode = (value) => {
    svg.dataset.gamutView = value;
    for (const button of buttons)
      button.setAttribute("aria-pressed", String(button.dataset.gamutMode === value));
    legend.textContent = value === "base" ? baseCopy : extendedCopy;
  };
  buttons.forEach((button) => button.addEventListener("click", () => {
    manualMode = button.dataset.gamutMode;
    gamutScene?.settle();
    mode(manualMode);
  }));
  control.addEventListener("click", () => gamutScene?.toggle());
  // Selecting a technical area takes precedence over the automatic scan.
  function inspect() {
    analysisTouched = true;
    analysisScene?.settle();
  }
  analysis.addEventListener("pointerdown", inspect);
  analysis.addEventListener("focusin", inspect);
  function controlState(state) {
    control.hidden = media.matches;
    control.textContent = state === "playing" ? "Mettre en pause"
      : state === "paused" ? "Reprendre l’animation" : "Rejouer la démonstration";
    if (state === "complete") mode(manualMode || "extended");
  }
  media.addEventListener("change", () => {
    if (gamutScene) controlState(gamutScene.state);
  });

  async function prepare() {
    if (loading || media.matches) return;
    loading = true;
    try {
      // Local and deferred: the hero needs neither this library nor a network CDN.
      const gsap = await loadEngine();
      const registry = window.__timelines ??= {};
      const gamutTimeline = buildGamutTimeline(gsap, gamut);
      registry["dtf-gamut"] = gamutTimeline;
      gamutTimeline.eventCallback("onUpdate", () => {
        if (manualMode !== null) return;
        const value = gamutTimeline.time() < 1.3 ? "base" : "extended";
        for (const button of buttons)
          button.setAttribute("aria-pressed", String(button.dataset.gamutMode === value));
      });
      gamutTimeline.time(gamutTimeline.duration(), false);
      gamutScene = createMotionScene(gamutTimeline, {
        element: gamut.querySelector("[data-gamut-scene]"), media,
        onStart() {
          manualMode = null;
          mode("extended");
          legend.textContent = "De la base CMJN à une palette enrichie par quatre encres complémentaires.";
        },
        onState: controlState,
      });
      if (manualMode) {
        gamutScene.settle();
        mode(manualMode);
      }
      controlState(gamutScene.state);
      const analysisTimeline = buildAnalysisTimeline(gsap, analysis);
      registry["dtf-analysis"] = analysisTimeline;
      analysisTimeline.time(analysisTimeline.duration(), false);
      analysisScene = createMotionScene(analysisTimeline, {
        element: analysis.querySelector("[data-analysis-scene]"), media,
      });
      if (analysisTouched) analysisScene.settle();
    } catch {
      // The page and mode controls keep their complete, static HTML fallback.
      gamutScene?.destroy();
      analysisScene?.destroy();
      for (const id of ["gamut-envelope-path", "gamut-extended-path"]) {
        const path = gamut.querySelector(`#${id}`);
        path.setAttribute("d", fullEnvelope);
        path.removeAttribute("style");
      }
      gamut.querySelectorAll("[data-gamut-label]").forEach((label) => {
        label.removeAttribute("style");
        label.removeAttribute("transform");
      });
      mode(manualMode || "extended");
      gamut.dataset.motionUnavailable = "true";
      control.hidden = true;
    }
  }
  if ("IntersectionObserver" in window) {
    const warmup = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting) && !media.matches) {
        warmup.disconnect();
        prepare();
      }
    }, { rootMargin: "200px" });
    warmup.observe(gamut);
    media.addEventListener("change", () => { if (!media.matches) prepare(); });
  } else prepare();
}
