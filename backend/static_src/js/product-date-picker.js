const MONTHS_FR = [
  "Janvier",
  "Février",
  "Mars",
  "Avril",
  "Mai",
  "Juin",
  "Juillet",
  "Août",
  "Septembre",
  "Octobre",
  "Novembre",
  "Décembre",
];

function parseISODate(value) {
  if (!value) {
    return null;
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value));
  if (!match) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return null;
  }
  return date;
}

function toISO(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDisplay(date) {
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  return `${day}/${month}/${date.getFullYear()}`;
}

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function initProductDatePicker(root) {
  const hidden = root.querySelector('input[type="hidden"]');
  const trigger = root.querySelector("[data-date-trigger]");
  const display = root.querySelector("[data-date-display]");
  const popover = root.querySelector("[data-date-popover]");
  const grid = root.querySelector("[data-date-grid]");
  const monthLabel = root.querySelector("[data-date-month]");
  const prevButton = root.querySelector("[data-date-prev]");
  const nextButton = root.querySelector("[data-date-next]");
  const clearButton = root.querySelector("[data-date-clear]");

  if (!hidden || !trigger || !display || !popover || !grid || !monthLabel) {
    return;
  }

  const placeholder = root.dataset.placeholder || "Choisir une date";
  const minDate = startOfDay(new Date());
  let viewDate = parseISODate(hidden.value) || new Date();
  viewDate = new Date(viewDate.getFullYear(), viewDate.getMonth(), 1);

  function selectedDate() {
    return parseISODate(hidden.value);
  }

  function updateDisplay() {
    const current = selectedDate();
    if (current) {
      display.textContent = formatDisplay(current);
      display.classList.remove("is-placeholder");
      trigger.dataset.hasValue = "true";
      return;
    }
    display.textContent = placeholder;
    display.classList.add("is-placeholder");
    delete trigger.dataset.hasValue;
  }

  function renderGrid() {
    monthLabel.textContent = `${MONTHS_FR[viewDate.getMonth()]} ${viewDate.getFullYear()}`;
    grid.replaceChildren();

    const firstWeekday = (new Date(viewDate.getFullYear(), viewDate.getMonth(), 1).getDay() + 6) % 7;
    const daysInMonth = new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 0).getDate();
    const selected = selectedDate();
    const today = startOfDay(new Date());

    for (let index = 0; index < firstWeekday; index += 1) {
      const spacer = document.createElement("span");
      spacer.className = "product-date-picker__day is-empty";
      spacer.setAttribute("aria-hidden", "true");
      grid.appendChild(spacer);
    }

    for (let day = 1; day <= daysInMonth; day += 1) {
      const date = new Date(viewDate.getFullYear(), viewDate.getMonth(), day);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "product-date-picker__day";
      button.textContent = String(day);
      button.dataset.day = String(day);

      if (date.getTime() === today.getTime()) {
        button.classList.add("is-today");
      }
      if (selected && date.getTime() === selected.getTime()) {
        button.classList.add("is-selected");
        button.setAttribute("aria-pressed", "true");
      }
      if (date < minDate) {
        button.classList.add("is-disabled");
        button.disabled = true;
      } else {
        button.addEventListener("click", () => {
          hidden.value = toISO(date);
          updateDisplay();
          renderGrid();
          hidden.dispatchEvent(new Event("change", { bubbles: true }));
          close();
        });
      }
      grid.appendChild(button);
    }
  }

  function open() {
    const current = selectedDate();
    if (current) {
      viewDate = new Date(current.getFullYear(), current.getMonth(), 1);
    } else {
      viewDate = new Date(minDate.getFullYear(), minDate.getMonth(), 1);
    }
    renderGrid();
    popover.hidden = false;
    root.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
  }

  function close() {
    popover.hidden = true;
    root.classList.remove("is-open");
    trigger.setAttribute("aria-expanded", "false");
  }

  trigger.addEventListener("click", (event) => {
    event.preventDefault();
    if (root.classList.contains("is-open")) {
      close();
      return;
    }
    open();
  });

  prevButton?.addEventListener("click", (event) => {
    event.preventDefault();
    viewDate = new Date(viewDate.getFullYear(), viewDate.getMonth() - 1, 1);
    renderGrid();
  });

  nextButton?.addEventListener("click", (event) => {
    event.preventDefault();
    viewDate = new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 1);
    renderGrid();
  });

  clearButton?.addEventListener("click", (event) => {
    event.preventDefault();
    hidden.value = "";
    updateDisplay();
    renderGrid();
    hidden.dispatchEvent(new Event("change", { bubbles: true }));
    close();
  });

  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element) || !root.classList.contains("is-open")) {
      return;
    }
    if (!root.contains(event.target)) {
      close();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && root.classList.contains("is-open")) {
      close();
    }
  });

  updateDisplay();
}

export function mountProductDatePickers(scope = document) {
  scope.querySelectorAll("[data-product-date-picker]").forEach((root) => {
    if (root.dataset.datePickerReady === "true") {
      return;
    }
    root.dataset.datePickerReady = "true";
    initProductDatePicker(root);
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => mountProductDatePickers());
} else {
  mountProductDatePickers();
}

document.body.addEventListener("htmx:afterSwap", (event) => {
  const target = event.detail?.target;
  mountProductDatePickers(target instanceof HTMLElement ? target : document);
});
