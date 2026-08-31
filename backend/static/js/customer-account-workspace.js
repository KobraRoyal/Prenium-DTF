function setCurrentCustomerSection(workspace, sectionId) {
  workspace.querySelectorAll('.staff-customer-workspace__nav a[href^="#"]').forEach((link) => {
    if (link.getAttribute("href") === `#${sectionId}`) {
      link.setAttribute("aria-current", "location");
    } else {
      link.removeAttribute("aria-current");
    }
  });
}

function revealCustomerSection(workspace, hash, { scroll = false } = {}) {
  if (!hash || !hash.startsWith("#")) {
    return false;
  }

  const section = document.getElementById(hash.slice(1));
  if (!(section instanceof HTMLDetailsElement) || !workspace.contains(section)) {
    return false;
  }

  section.open = true;
  setCurrentCustomerSection(workspace, section.id);

  if (scroll) {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    section.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  }

  return true;
}

function initCustomerAccountWorkspace(root = document) {
  root.querySelectorAll("[data-customer-workspace]").forEach((workspace) => {
    if (workspace.dataset.customerWorkspaceReady === "true") {
      return;
    }

    workspace.dataset.customerWorkspaceReady = "true";

    workspace.querySelectorAll('.staff-customer-workspace__nav a[href^="#"]').forEach((link) => {
      link.addEventListener("click", (event) => {
        const hash = link.getAttribute("href");
        if (!revealCustomerSection(workspace, hash, { scroll: true })) {
          return;
        }

        event.preventDefault();
        window.history.pushState(null, "", hash);
      });
    });

    workspace.querySelectorAll("details[data-customer-section]").forEach((section) => {
      section.addEventListener("toggle", () => {
        if (section.open) {
          setCurrentCustomerSection(workspace, section.id);
        }
      });
    });

    revealCustomerSection(workspace, window.location.hash);
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => initCustomerAccountWorkspace());
} else {
  initCustomerAccountWorkspace();
}

window.addEventListener("hashchange", () => {
  document.querySelectorAll("[data-customer-workspace]").forEach((workspace) => {
    revealCustomerSection(workspace, window.location.hash, { scroll: true });
  });
});

document.body.addEventListener("htmx:afterSwap", (event) => {
  initCustomerAccountWorkspace(event.target);
});
