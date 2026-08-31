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

function accessibleDateLabel(date) {
  return new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(date);
}

function addMonthsClamped(date, offset) {
  const targetMonth = new Date(date.getFullYear(), date.getMonth() + offset, 1);
  const lastDay = new Date(
    targetMonth.getFullYear(),
    targetMonth.getMonth() + 1,
    0,
  ).getDate();
  return new Date(
    targetMonth.getFullYear(),
    targetMonth.getMonth(),
    Math.min(date.getDate(), lastDay),
  );
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

  function enabledDayButtons() {
    return Array.from(
      grid.querySelectorAll('button[role="gridcell"]:not(:disabled)'),
    );
  }

  function focusCalendar(preferredDate = null) {
    const preferredISO = preferredDate ? toISO(preferredDate) : "";
    const selected = selectedDate();
    const selectedISO = selected ? toISO(selected) : "";
    const buttons = enabledDayButtons();
    const target =
      buttons.find((button) => button.dataset.date === preferredISO) ||
      buttons.find((button) => button.dataset.date === selectedISO) ||
      buttons.find((button) => button.getAttribute("aria-current") === "date") ||
      buttons[0];

    grid.querySelectorAll('[role="gridcell"]').forEach((button) => {
      button.tabIndex = button === target ? 0 : -1;
    });

    if (target) {
      target.focus();
      return;
    }
    grid.tabIndex = -1;
    grid.focus();
  }

  function renderGrid(focusTarget = null) {
    monthLabel.textContent = `${MONTHS_FR[viewDate.getMonth()]} ${viewDate.getFullYear()}`;
    grid.replaceChildren();

    const firstWeekday = (new Date(viewDate.getFullYear(), viewDate.getMonth(), 1).getDay() + 6) % 7;
    const daysInMonth = new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 0).getDate();
    const selected = selectedDate();
    const today = startOfDay(new Date());

    const cellCount = Math.ceil((firstWeekday + daysInMonth) / 7) * 7;
    let row = null;

    for (let index = 0; index < cellCount; index += 1) {
      if (index % 7 === 0) {
        row = document.createElement("div");
        row.setAttribute("role", "row");
        row.style.display = "contents";
        grid.appendChild(row);
      }

      const day = index - firstWeekday + 1;
      if (day < 1 || day > daysInMonth) {
        const spacer = document.createElement("span");
        spacer.className = "product-date-picker__day is-empty";
        spacer.setAttribute("role", "gridcell");
        spacer.setAttribute("aria-hidden", "true");
        row?.appendChild(spacer);
        continue;
      }

      const date = new Date(viewDate.getFullYear(), viewDate.getMonth(), day);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "product-date-picker__day";
      button.textContent = String(day);
      button.dataset.day = String(day);
      button.dataset.date = toISO(date);
      button.setAttribute("role", "gridcell");
      button.setAttribute("aria-label", accessibleDateLabel(date));
      button.tabIndex = -1;

      if (date.getTime() === today.getTime()) {
        button.classList.add("is-today");
        button.setAttribute("aria-current", "date");
      }
      if (selected && date.getTime() === selected.getTime()) {
        button.classList.add("is-selected");
        button.setAttribute("aria-selected", "true");
      } else {
        button.setAttribute("aria-selected", "false");
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
          close({ restoreFocus: true });
        });
      }
      row?.appendChild(button);
    }

    if (focusTarget) {
      focusCalendar(focusTarget);
    }
  }

  function moveCalendarFocus(date) {
    const target = startOfDay(date < minDate ? minDate : date);
    viewDate = new Date(target.getFullYear(), target.getMonth(), 1);
    renderGrid(target);
  }

  function open() {
    const current = selectedDate();
    const focusTarget = current && current >= minDate ? current : minDate;
    viewDate = new Date(focusTarget.getFullYear(), focusTarget.getMonth(), 1);
    renderGrid();
    popover.hidden = false;
    root.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    focusCalendar(focusTarget);
  }

  function close({ restoreFocus = false } = {}) {
    popover.hidden = true;
    root.classList.remove("is-open");
    trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus) {
      trigger.focus();
    }
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
    close({ restoreFocus: true });
  });

  grid.addEventListener("keydown", (event) => {
    if (
      !(event.target instanceof HTMLElement) ||
      event.target.getAttribute("role") !== "gridcell"
    ) {
      return;
    }
    const current = parseISODate(event.target.dataset.date);
    if (!current) {
      return;
    }

    let target = null;
    const weekday = (current.getDay() + 6) % 7;
    switch (event.key) {
      case "ArrowLeft":
        target = new Date(
          current.getFullYear(),
          current.getMonth(),
          current.getDate() - 1,
        );
        break;
      case "ArrowRight":
        target = new Date(
          current.getFullYear(),
          current.getMonth(),
          current.getDate() + 1,
        );
        break;
      case "ArrowUp":
        target = new Date(
          current.getFullYear(),
          current.getMonth(),
          current.getDate() - 7,
        );
        break;
      case "ArrowDown":
        target = new Date(
          current.getFullYear(),
          current.getMonth(),
          current.getDate() + 7,
        );
        break;
      case "Home":
        target = new Date(
          current.getFullYear(),
          current.getMonth(),
          current.getDate() - weekday,
        );
        break;
      case "End":
        target = new Date(
          current.getFullYear(),
          current.getMonth(),
          current.getDate() + (6 - weekday),
        );
        break;
      case "PageUp":
        target = addMonthsClamped(current, -1);
        break;
      case "PageDown":
        target = addMonthsClamped(current, 1);
        break;
      default:
        return;
    }

    event.preventDefault();
    moveCalendarFocus(target);
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
      event.preventDefault();
      close({ restoreFocus: true });
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
