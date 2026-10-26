import { initPhotoCarousel } from "./dtf-photo-carousel.js?v=20261025p";
import { initPreparationCarousel } from "./dtf-preparation-carousel.js?v=20261025l";
import { initDtfChoreography } from "./dtf-choreography.js?v=20261025e";
import { createMotion } from "./dtf-motion.js?v=20261025l";
import { estimateVolume } from "./dtf-pricing.js?v=20261024c";

const reduced = matchMedia("(prefers-reduced-motion: reduce)");
const HL = window.HL;
const motion = createMotion(reduced);
initPhotoCarousel(document.querySelector("[data-photo-carousel]"), reduced);
initPreparationCarousel(document.querySelector("[data-preparation-carousel]"), reduced);
if (HL) {
  HL.setReducedMotion(reduced.matches);
  reduced.addEventListener("change", (event) =>
    HL.setReducedMotion(event.matches),
  );
}

// All tabsets share roving focus, explicit panel associations and touch behavior.
function tabsFor(list, onChange = () => {}) {
  const tabs = [...list.querySelectorAll('[role="tab"]')];
  const select = (index, focus = false) => {
    tabs.forEach((tab, i) => {
      tab.setAttribute("aria-selected", String(i === index));
      tab.tabIndex = i === index ? 0 : -1;
      const panel = document.getElementById(tab.getAttribute("aria-controls"));
      const entering = i === index && panel.hidden;
      panel.hidden = i !== index;
      if (entering) motion.enter(panel, { kind: "panel", duration: 320 });
    });
    if (focus) tabs[index].focus();
    onChange(index);
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => select(index));
    tab.addEventListener("keydown", (event) => {
      let next = index;
      if (event.key === "ArrowRight" || event.key === "ArrowDown")
        next = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft" || event.key === "ArrowUp")
        next = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      else return;
      event.preventDefault();
      select(next, true);
    });
  });
  return { select, tabs };
}

// The moving band has a user pause, and sleeps offscreen or in a hidden tab.
const ribbon = document.querySelector("[data-ribbon]");
if (ribbon) {
  const control = ribbon.querySelector("[data-ribbon-pause]");
  let userPaused = false,
    visible = true;
  const syncRibbon = () => {
    ribbon.classList.toggle(
      "is-paused",
      userPaused || !visible || document.hidden || reduced.matches,
    );
    control.disabled = reduced.matches;
    control.setAttribute("aria-pressed", String(userPaused));
    control.setAttribute(
      "aria-label",
      userPaused ? "Reprendre le bandeau" : "Mettre le bandeau en pause",
    );
    control
      .querySelector("[data-ribbon-icon]")
      .setAttribute("d", userPaused ? "m7 4 8 6-8 6Z" : "M7 4v12M13 4v12");
  };
  control.addEventListener("click", () => {
    userPaused = !userPaused;
    syncRibbon();
  });
  document.addEventListener("visibilitychange", syncRibbon);
  reduced.addEventListener("change", syncRibbon);
  if ("IntersectionObserver" in window)
    new IntersectionObserver((entries) => {
      visible = entries[0].isIntersecting;
      syncRibbon();
    }).observe(ribbon);
  syncRibbon();
}

const menu = document.querySelector(".dtf-menu");
const nav = document.querySelector("#dtf-navigation");
function closeMenu(restoreFocus = false) {
  nav.classList.remove("is-open");
  menu.setAttribute("aria-expanded", "false");
  if (restoreFocus) menu.focus();
}
menu.addEventListener("click", () => {
  const open = menu.getAttribute("aria-expanded") !== "true";
  nav.classList.toggle("is-open", open);
  menu.setAttribute("aria-expanded", String(open));
  if (open) motion.enter(nav, { kind: "panel", duration: 240 });
});
nav.addEventListener("click", (event) => {
  if (event.target.closest("a")) closeMenu();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && nav.classList.contains("is-open"))
    closeMenu(true);
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".dtf-header")) closeMenu();
});
matchMedia("(min-width: 821px)").addEventListener("change", () => closeMenu());

const anatomy = document.querySelector("[data-anatomy]");
const stage = anatomy.querySelector("[data-transfer-stage]");
const layerButtons = [...anatomy.querySelectorAll("[data-layer]")];
const tooltip = anatomy.querySelector('[role="tooltip"]');
const transferClose = anatomy.querySelector("[data-transfer-close]");
const accents = ["#8299a2", "#b75f53", "#9d998a", "#ac8c5d"];
const layerDescriptions = [
  ["Film PET", "Pelable à chaud.", "Film PET double face, d’une laize maximale de 56 cm. Il se retire après le pressage."],
  ["Couleur", "Des couleurs vives.", "CMJN + orange, vert, rouge et bleu. Des encres certifiées OEKO‑TEX® pour vos impressions."],
  ["Blanc", "Un toucher plus souple.", "Un blanc optimisé selon le visuel et la couleur du support. Encre certifiée OEKO‑TEX®."],
  ["Poudre", "La tenue au lavage.", "Une poudre premium sélectionnée pour la tenue au lavage. Respectez les consignes de pose et d’entretien."],
];
let figure,
  selectedLayer = -1,
  dismissed = false,
  keyboardUse = false;
function updateLayerInfo(index) {
  const changed = selectedLayer !== index || tooltip.hidden;
  selectedLayer = index;
  const open = index >= 0;
  anatomy.dataset.expanded = String(open);
  stage.setAttribute("aria-expanded", String(open));
  stage.setAttribute("aria-label", "Explorer les couches du transfert");
  transferClose.disabled = !open;
  layerButtons.forEach((button, i) => {
    button.setAttribute("aria-pressed", String(i === index));
    if (i === index && !dismissed)
      button.setAttribute("aria-describedby", tooltip.id);
    else button.removeAttribute("aria-describedby");
  });
  tooltip.hidden = !open || dismissed;
  if (open) {
    const [number, title, copy] = layerDescriptions[index];
    anatomy.style.setProperty("--layer-accent", accents[index]);
    tooltip.querySelector("[data-tooltip-index]").textContent = number;
    tooltip.querySelector("[data-tooltip-title]").textContent = title;
    tooltip.querySelector("[data-tooltip-copy]").textContent = copy;
    stage.setAttribute("aria-describedby", tooltip.id);
    if (changed && !dismissed)
      motion.enter(tooltip, { kind: "tooltip", duration: 220 });
  } else stage.removeAttribute("aria-describedby");

}
function selectLayer(index) {
  dismissed = false;
  stage.removeAttribute("data-dismissed");
  updateLayerInfo(index);
  figure?.select(index);
}
function collapseTransfer(suppress = false) {
  dismissed = suppress;
  if (suppress) stage.setAttribute("data-dismissed", "true");
  figure?.collapse();
  updateLayerInfo(-1);
}
transferClose.addEventListener("click", () => collapseTransfer(true));
stage.addEventListener("pointerenter", (event) => {
  if (event.pointerType === "mouse") selectLayer(1);
});
stage.addEventListener("pointerdown", () => {
  keyboardUse = false;
  dismissed = false;
  stage.removeAttribute("data-dismissed");
});
stage.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    keyboardUse = true;
    if (selectedLayer >= 0) collapseTransfer(true);
    else selectLayer(1);
  }
});
layerButtons.forEach((button, index) => {
  button.addEventListener("pointerenter", (event) => {
    if (event.pointerType === "mouse") selectLayer(index);
  });
  button.addEventListener("focus", () => selectLayer(index));
  button.addEventListener("click", () => selectLayer(index));
  button.addEventListener("keydown", (event) => {
    let next = index;
    if (["ArrowRight", "ArrowDown"].includes(event.key)) next = (index + 1) % 4;
    else if (["ArrowLeft", "ArrowUp"].includes(event.key))
      next = (index + 3) % 4;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = 3;
    else return;
    event.preventDefault();
    keyboardUse = true;
    layerButtons[next].focus();
  });
});
anatomy.addEventListener("pointerleave", (event) => {
  if (
    event.pointerType === "mouse" &&
    !(keyboardUse && anatomy.contains(document.activeElement))
  )
    collapseTransfer();
});
anatomy.addEventListener("focusout", (event) => {
  if (!anatomy.contains(event.relatedTarget)) collapseTransfer();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Tab") keyboardUse = true;
  if (event.key === "Escape") collapseTransfer(true);
});
document.addEventListener("pointerdown", (event) => {
  keyboardUse = false;
  if (!anatomy.contains(event.target)) collapseTransfer();
});
if (HL && window.DTFTransferFigure) {
  HL.inject(document);
  stage.setAttribute("data-hairline", "dtf-transfer");
  const svg = stage.querySelector("svg");
  svg.replaceChildren();
  const defs = HL.mk("defs", {}, svg);
  const film = HL.mk(
    "linearGradient",
    { id: "dtf-film-gradient", x1: "0", y1: "0", x2: "1", y2: "1" },
    defs,
  );
  [
    ["0", "#d7e1e3", ".75"],
    [".4", "#fffdf8", ".2"],
    [".7", "#f8fcfc", ".5"],
    ["1", "#bdccce", ".7"],
  ].forEach(([offset, color, opacity]) =>
    HL.mk(
      "stop",
      { offset, "stop-color": color, "stop-opacity": opacity },
      film,
    ),
  );
  const names = [
    "Film PET",
    "Encres 8 couleurs",
    "Blanc optimisé",
    "Poudre adhésive",
  ];
  const read = {
    set textContent(text) {
      updateLayerInfo(text === "rest" ? -1 : names.indexOf(text));
    },
  };
  figure = window.DTFTransferFigure.mount(
    { stage, svg, read, controlled: true },
    26,
  );
}
updateLayerInfo(-1);
document.querySelectorAll('a[href="#technologie"]').forEach((link) => {
  link.addEventListener("click", () => {
    selectLayer(1);
    stage.focus({ preventScroll: true });
  });
});

const analysis = document.querySelector("[data-analysis]");
const canvas = analysis.querySelector("[data-analysis-canvas]");
const hotspots = [...analysis.querySelectorAll("[data-analysis-pick]")];
const analysisTabs = tabsFor(analysis.querySelector("[data-tabs]"), (index) => {
  canvas.dataset.inspect = index;
  hotspots.forEach((hotspot, i) => {
    hotspot.classList.toggle("is-active", i === index);
    hotspot.setAttribute("aria-pressed", String(i === index));
  });
});
hotspots.forEach((hotspot) =>
  hotspot.addEventListener("click", () =>
    analysisTabs.select(Number(hotspot.dataset.analysisPick)),
  ),
);
initDtfChoreography(document.querySelector("[data-gamut]"), analysis, reduced);

const comparison = document.querySelector("[data-comparison]");
const compareRange = comparison.querySelector("input");
function updateComparison(value) {
  compareRange.value = value;
  compareRange.setAttribute("aria-valuetext", `${value} % de la vue préparée`);
  comparison
    .querySelector(".dtf-comparison__stage")
    .style.setProperty("--compare", `${value}%`);
  comparison.querySelector("output").textContent =
    `${value} % de la vue préparée`;
}
compareRange.addEventListener("input", () =>
  updateComparison(compareRange.value),
);
comparison
  .querySelectorAll("[data-compare-to]")
  .forEach((button) =>
    button.addEventListener("click", () =>
      updateComparison(button.dataset.compareTo),
    ),
  );

const textile = document.querySelector("[data-textile]");
const preview = textile.querySelector("[data-textile-preview]");
const swatches = [...textile.querySelectorAll("[data-color]")];
function refreshLoupe() {
  const copy = preview.querySelector("#dtf-edge-example").cloneNode(true);
  copy.removeAttribute("id");
  preview.querySelector("[data-edge-loupe]").replaceChildren(copy);
}
preview
  .querySelector(".dtf-edge-underbase")
  .setAttribute("d", "M149 283 257 92h62L213 283Zm120 0 71-126h61l-69 126Z");
refreshLoupe();

function setTextile(color, name) {
  preview.style.setProperty("--textile", color);
  preview.dataset.textileColor = color;
  textile.querySelector("[data-textile-name]").textContent = name;
  swatches.forEach((button) =>
    button.setAttribute("aria-pressed", String(button.dataset.color === color)),
  );
}
swatches.forEach((button) =>
  button.addEventListener("click", () =>
    setTextile(button.dataset.color, button.dataset.name),
  ),
);
textile
  .querySelector("input[type=color]")
  .addEventListener("input", (event) =>
    setTextile(
      event.target.value,
      `Personnalisé ${event.target.value.toUpperCase()}`,
    ),
  );
const explanations = [
  "Le blanc dépasse du motif et forme un liseré sur un textile foncé. Le défaut est amplifié dans ce schéma.",
  "Le blanc est réduit vers l’intérieur du motif pour éviter qu’il dépasse. Le dessin couleur reste inchangé.",
  "Certains pixels du bord couleur sont adaptés au textile. Cette correction, distincte du retrait du blanc, dépend du visuel et exige la teinte exacte.",
];
textile.querySelectorAll("[data-edge]").forEach((button) =>
  button.addEventListener("click", () => {
    preview.dataset.edgeState = button.dataset.edge;
    preview
      .querySelector(".dtf-edge-underbase")
      .setAttribute(
        "d",
        button.dataset.edge === "0"
          ? "M145 285 255 90h68L215 285Zm120 0 73-130h67l-71 130Z"
          : "M149 283 257 92h62L213 283Zm120 0 71-126h61l-69 126Z",
      );
    refreshLoupe();
    textile
      .querySelectorAll("[data-edge]")
      .forEach((option) =>
        option.setAttribute("aria-pressed", String(option === button)),
      );
    textile.querySelector(".dtf-edge-explanation").textContent =
      explanations[Number(button.dataset.edge)];
  }),
);

const whiteToggle = textile.querySelector(".dtf-white-toggle");
whiteToggle.addEventListener("click", () => {
  const show = whiteToggle.getAttribute("aria-pressed") !== "true";
  whiteToggle.setAttribute("aria-pressed", String(show));
  preview.classList.toggle("show-white", show);
  whiteToggle.textContent = show
    ? "Revenir au visuel couleur"
    : "Afficher la sous-couche blanche";
});

const alpha = document.querySelector("[data-alpha]");
const alphaTabs = tabsFor(alpha.querySelector("[data-tabs]"), (index) => {
  const preview = alpha.querySelector("[data-alpha-state]");
  preview.dataset.alphaState = index;
  motion.enter(preview, { kind: "panel", duration: 260 });
});
// Hover previews use the same state as tap and keyboard, with no disappearing information.
alphaTabs.tabs.forEach((tab, i) =>
  tab.addEventListener("pointerenter", (event) => {
    if (event.pointerType === "mouse") alphaTabs.select(i);
  }),
);

const ordering = document.querySelector("[data-ordering]");
if (ordering) {
  tabsFor(ordering.querySelector("[data-tabs]"));
  const viewer = ordering.querySelector(".dtf-screen-dialog");
  const image = viewer.querySelector("[data-screen-image]");
  const zoom = viewer.querySelector("[data-screen-zoom]");
  const frame = viewer.querySelector(".dtf-screen-dialog__image");
  function setScreenZoom(enlarged) {
    frame.classList.toggle("is-zoomed", enlarged);
    zoom.setAttribute("aria-pressed", String(enlarged));
    zoom.textContent = enlarged ? "Ajuster à l’écran" : "Taille réelle";
  }
  zoom.addEventListener("click", () =>
    setScreenZoom(zoom.getAttribute("aria-pressed") !== "true"),
  );

  ordering.querySelectorAll("[data-product-screen]").forEach((button) =>
    button.addEventListener("click", () => {
      const original = button.querySelector("img");
      image.src = original.src;
      image.alt = original.alt;
      image.width = original.naturalWidth || original.width;
      image.height = original.naturalHeight || original.height;
      viewer.querySelector("h3").textContent = button.dataset.screenTitle;
      setScreenZoom(false);
      viewer.showModal();
    }),
  );
  viewer
    .querySelector("[data-close-screen]")
    .addEventListener("click", () => viewer.close());
}

// Only real photographs are interactive. Reserved photo areas stay static.
const galleryItems = [...document.querySelectorAll("[data-gallery]")];
const dialog = document.querySelector("[data-gallery-dialog]");
let galleryIndex = 0;
function displayGallery(index) {
  if (!galleryItems.length) return;
  galleryIndex = (index + galleryItems.length) % galleryItems.length;
  const item = galleryItems[galleryIndex];
  const original = item.querySelector("img");
  const source = original?.currentSrc || original?.getAttribute("src");
  if (!source) return false;
  const image = document.createElement("img");
  image.src = source;
  image.alt = original.alt;
  image.dataset.galleryImage = "";
  dialog.querySelector("[data-gallery-media]").replaceChildren(image);
  dialog.querySelector("h3").textContent = item.dataset.gallery;
  dialog.querySelector("[data-gallery-caption]").textContent = item.dataset.galleryCaption;
  dialog.querySelector("[data-gallery-counter]").textContent =
    `${galleryIndex + 1} / ${galleryItems.length}`;
  return true;
}
galleryItems.forEach((item, i) => item.addEventListener("click", () => {
  if (displayGallery(i)) dialog.showModal();
}));
dialog.querySelector(".dtf-lightbox__close").addEventListener("click", () => dialog.close());
dialog.querySelector("[data-gallery-prev]").addEventListener("click", () => displayGallery(galleryIndex - 1));
dialog.querySelector("[data-gallery-next]").addEventListener("click", () => displayGallery(galleryIndex + 1));
dialog.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
    event.preventDefault();
    displayGallery(galleryIndex + (event.key === "ArrowLeft" ? -1 : 1));
  }
});
dialog.addEventListener("click", (event) => {
  if (event.target !== dialog) return;
  const r = dialog.getBoundingClientRect();
  if (event.clientX < r.left || event.clientX > r.right ||
      event.clientY < r.top || event.clientY > r.bottom) dialog.close();
});

// Deep links still reveal the technical tools when their disclosure is closed.
function revealLinkedTool(hash) {
  let id;
  try { id = decodeURIComponent(hash.slice(1)); } catch { return; }
  let target = document.getElementById(id);
  while (target) {
    if (target.tagName === "DETAILS") target.open = true;
    target = target.parentElement;
  }
}
document.addEventListener("click", (event) => {
  const anchor = event.target.closest('a[href^="#"]');
  if (anchor) revealLinkedTool(anchor.getAttribute("href"));
});
window.addEventListener("hashchange", () => revealLinkedTool(location.hash));
if (location.hash) revealLinkedTool(location.hash);

const pricing = document.querySelector("[data-pricing]");
const priceData = document.getElementById("dtf-public-pricing");
if (priceData) {
  const config = JSON.parse(priceData.textContent);
  const number = pricing.querySelector("input[type=number]"),
    range = pricing.querySelector("input[type=range]");
  const money = new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
  });
  const percent = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });
  const priceOutput = pricing.querySelector("[data-unit-price]");
  const ticks = [...pricing.querySelectorAll("[data-tier-min]")];
  const metrics = [
    {
      element: priceOutput,
      key: "unitCents",
      format: (value) => money.format(Math.round(value) / 100),
    },
    {
      element: pricing.querySelector("[data-discount]"),
      key: "percent",
      format: (value) => `${percent.format(Math.round(value * 100) / 100)} %`,
    },
    {
      element: pricing.querySelector("[data-total]"),
      key: "totalCents",
      format: (value) => `${money.format(Math.round(value) / 100)} HT`,
    },
    {
      element: pricing.querySelector("[data-savings]"),
      key: "savingsCents",
      format: (value) => `${money.format(Math.round(value) / 100)} HT`,
    },
  ];
  const initial = estimateVolume(config, 1);
  metrics.forEach((metric) => {
    if (HL) metric.clock = HL.tween(initial[metric.key], 280);
  });
  const numbers = HL?.register(pricing, (_dt, now) => {
    let moving = false;
    metrics.forEach((metric) => {
      metric.element.textContent = metric.format(HL.tval(metric.clock, now));
      if (!HL.tdone(metric.clock, now)) moving = true;
    });
    return moving;
  });
  function updatePricing(value) {
    const quote = estimateVolume(config, value);
    number.value = quote.volume;
    range.value = quote.volume;
    ticks.forEach((button, i) =>
      button.setAttribute(
        "aria-pressed",
        String(
          i === 0
            ? quote.minimum === 0
            : Number(button.dataset.tierMin) === quote.minimum,
        ),
      ),
    );
    pricing.querySelector("[data-pricing-status]").textContent =
      `Pour ${quote.volume} m : ${money.format(quote.unitCents / 100)} HT/m, remise de ${percent.format(quote.percent)} %, hors transport et préparation.`;
    metrics.forEach((metric) => {
      if (HL) HL.tset(metric.clock, quote[metric.key], performance.now(), 0);
      else metric.element.textContent = metric.format(quote[metric.key]);
    });
    numbers?.wake();
    renderHeroQuote(quote);
  }
  const heroPrice = document.querySelector("[data-hero-price]");
  const heroVolume = document.querySelector("[data-hero-volume]");
  const heroTiers = document.querySelector("[data-hero-tiers]");
  const heroButtons = heroTiers
    ? [...heroTiers.querySelectorAll("[data-hero-tier]")]
    : [];
  const heroDefaultVolume = heroVolume?.textContent;
  function renderHeroQuote(quote) {
    if (!heroTiers) return;
    heroButtons.forEach((button, i) =>
      button.setAttribute(
        "aria-pressed",
        String(
          i === 0
            ? quote.minimum === 0
            : Number(button.dataset.heroTier) === quote.minimum,
        ),
      ),
    );
    heroPrice.textContent = money.format(quote.unitCents / 100);
    heroVolume.textContent =
      quote.minimum === 0
        ? heroDefaultVolume
        : `Dès ${percent.format(quote.minimum)} m par mois : −${percent.format(quote.percent)} %.`;
  }
  if (heroTiers) {
    heroTiers.hidden = false;
    heroButtons.forEach((button) =>
      button.addEventListener("click", () =>
        updatePricing(Math.ceil(Number(button.dataset.heroTier))),
      ),
    );
  }
  range.addEventListener("input", () => updatePricing(range.value));
  number.addEventListener("change", () => updatePricing(number.value));
  number.addEventListener("input", () => {
    if (number.value && number.validity.valid) updatePricing(number.value);
  });
  ticks.forEach((button) =>
    button.addEventListener("click", () =>
      updatePricing(Math.ceil(Number(button.dataset.tierMin))),
    ),
  );
  updatePricing(1);
}

motion.revealPage();
