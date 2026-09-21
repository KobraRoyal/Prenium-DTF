/**
 * Ajustement facturation Atelier (encours) — totaux live + métrage linéaire DTF.
 */
function registerStaffBillingAdjustment() {
  if (typeof Alpine === "undefined" || typeof Alpine.data !== "function") {
    return;
  }
  if (window.__staffBillingAdjustmentRegistered) {
    return;
  }
  window.__staffBillingAdjustmentRegistered = true;

  Alpine.data("staffBillingAdjustment", (config = {}) => ({
    catalog: {},
    taxRate: Number(config.taxRate || 0),
    currency: config.currency || "EUR",
    shippingCode: String(config.shippingCode || ""),
    shippingAmount: config.shippingAmount,
    baselineShippingAmount: Number(config.shippingAmount || 0),
    lines: [],
    subtotal: 0,
    taxAmount: 0,
    total: Number(config.initialTotal || 0),
    totalsReady: false,
    errors: { shipping: "", lines: {} },
    valid: true,

    init() {
      const catalogEl = document.getElementById(config.catalogElId);
      if (catalogEl) {
        try {
          this.catalog = JSON.parse(catalogEl.textContent || "{}");
        } catch (_err) {
          this.catalog = {};
        }
      }
      const linesEl = config.linesElId ? document.getElementById(config.linesElId) : null;
      if (linesEl) {
        try {
          const seed = JSON.parse(linesEl.textContent || "[]");
          if (Array.isArray(seed)) {
            this.lines = seed.map((line) => this.seedLine(line));
          }
        } catch (_err) {
          this.lines = [];
        }
      }
      this.shippingAmount = this.coerceNumber(this.shippingAmount, this.baselineShippingAmount);
      this.baselineShippingAmount = this.coerceNumber(
        this.baselineShippingAmount,
        Number(this.shippingAmount) || 0
      );
      this.lines.forEach((_line, index) => this.syncLinearQty(index));
      this.recompute();
      this.$nextTick(() => this.recompute());
    },

    seedLine(line) {
      const qtyMode = line.qtyMode === "linear" ? "linear" : "quantity";
      const unitPrice = this.coerceNumber(line.unitPrice, 0);
      const laizeM = this.coerceNumber(line.laizeM, 0.55);
      if (qtyMode === "linear") {
        const linearM = this.coerceNumber(line.linearM, 0);
        const qty = this.roundQty(linearM * laizeM);
        return {
          label: line.label || "Ligne",
          qtyMode,
          linearM,
          baselineLinearM: this.coerceNumber(line.baselineLinearM ?? line.linearM, linearM),
          qty,
          baselineQty: qty,
          unitPrice,
          baselineUnitPrice: this.coerceNumber(line.baselineUnitPrice ?? line.unitPrice, unitPrice),
          laizeM,
          laizeCm: Number(line.laizeCm || Math.round(laizeM * 100)),
        };
      }
      const qty = this.coerceNumber(line.qty, 0);
      return {
        label: line.label || "Ligne",
        qtyMode,
        qty,
        baselineQty: this.coerceNumber(line.baselineQty ?? line.qty, qty),
        unitPrice,
        baselineUnitPrice: this.coerceNumber(line.baselineUnitPrice ?? line.unitPrice, unitPrice),
      };
    },

    coerceNumber(value, fallback = 0) {
      if (value === "" || value === null || value === undefined) {
        return fallback;
      }
      if (typeof value === "string") {
        value = value.replace(",", ".").trim();
      }
      const n = Number(value);
      return Number.isFinite(n) ? n : fallback;
    },

    roundQty(value) {
      return Math.round((Number(value) || 0) * 10000) / 10000;
    },

    onShippingModeChange() {
      const catalogValue = this.catalog[this.shippingCode];
      if (catalogValue !== undefined && catalogValue !== null && catalogValue !== "") {
        this.shippingAmount = this.coerceNumber(catalogValue, this.baselineShippingAmount);
      }
      this.recompute();
    },

    onLinearInput(index) {
      this.syncLinearQty(index);
      this.recompute();
    },

    syncLinearQty(index) {
      const line = this.lines[index];
      if (!line || line.qtyMode !== "linear") return;
      const linear = this.effectiveLinear(index);
      if (linear === null) {
        line.qty = null;
        return;
      }
      line.qty = this.roundQty(linear * (line.laizeM || 0.55));
    },

    effectiveLinear(index) {
      const line = this.lines[index];
      if (!line || line.qtyMode !== "linear") return null;
      if (this.isBlank(line.linearM)) return line.baselineLinearM;
      if (!this.isNumeric(line.linearM)) return null;
      return this.coerceNumber(line.linearM);
    },

    effectiveQty(index) {
      const line = this.lines[index];
      if (!line) return null;
      if (line.qtyMode === "linear") {
        const linear = this.effectiveLinear(index);
        if (linear === null) return null;
        return this.roundQty(linear * (line.laizeM || 0.55));
      }
      if (this.isBlank(line.qty)) return line.baselineQty;
      if (!this.isNumeric(line.qty)) return null;
      return this.coerceNumber(line.qty);
    },

    effectiveUnitPrice(index) {
      const line = this.lines[index];
      if (!line) return null;
      if (this.isBlank(line.unitPrice)) return line.baselineUnitPrice;
      if (!this.isNumeric(line.unitPrice)) return null;
      return this.coerceNumber(line.unitPrice);
    },

    effectiveShipping() {
      if (this.isBlank(this.shippingAmount)) return this.baselineShippingAmount;
      if (!this.isNumeric(this.shippingAmount)) return null;
      return this.coerceNumber(this.shippingAmount);
    },

    lineTotal(index) {
      const qty = this.effectiveQty(index);
      const price = this.effectiveUnitPrice(index);
      if (qty === null || price === null || qty < 0.01 || price < 0) {
        return null;
      }
      return this.roundMoney(qty * price);
    },

    formatQty(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "—";
      }
      const rounded = this.roundQty(value);
      const text = String(rounded);
      if (!text.includes(".")) return text;
      return text.replace(/0+$/, "").replace(/\.$/, "");
    },

    dtfQtyHint(index) {
      const line = this.lines[index];
      if (!line || line.qtyMode !== "linear") return "";
      const qty = this.effectiveQty(index);
      if (qty === null) return "Quantité m² selon laize";
      return `= ${this.formatQty(qty)} m² (laize ${line.laizeCm || 55} cm)`;
    },

    isBlank(value) {
      return (
        value === "" ||
        value === null ||
        value === undefined ||
        (typeof value === "number" && Number.isNaN(value))
      );
    },

    isNumeric(value) {
      if (this.isBlank(value)) return false;
      if (typeof value === "string") {
        value = value.replace(",", ".").trim();
      }
      const n = Number(value);
      return Number.isFinite(n);
    },

    roundMoney(value) {
      return Math.round((Number(value) || 0) * 100) / 100;
    },

    validate() {
      const lineErrors = {};
      let ok = true;
      let shippingError = "";
      const shipping = this.effectiveShipping();

      if (shipping === null || shipping < 0) {
        shippingError = "Indiquez un port ≥ 0 (valeur initiale en placeholder).";
        ok = false;
      }

      this.lines.forEach((line, index) => {
        const messages = [];
        if (line.qtyMode === "linear") {
          const linear = this.effectiveLinear(index);
          if (linear === null || linear < 0.01) {
            messages.push("Métrage ≥ 0,01 m");
          }
        } else {
          const qty = this.effectiveQty(index);
          if (qty === null || qty < 0.01) {
            messages.push("Qté ≥ 0,01");
          }
        }
        const price = this.effectiveUnitPrice(index);
        if (price === null || price < 0) {
          messages.push("PU ≥ 0");
        }
        if (messages.length) {
          lineErrors[index] = messages.join(" · ");
          ok = false;
        }
      });

      this.errors = { shipping: shippingError, lines: lineErrors };
      this.valid = ok;
      return ok;
    },

    restoreBlanksFromBaseline() {
      if (this.isBlank(this.shippingAmount)) {
        this.shippingAmount = this.baselineShippingAmount;
      }
      this.lines.forEach((line, index) => {
        if (line.qtyMode === "linear") {
          if (this.isBlank(line.linearM)) {
            line.linearM = line.baselineLinearM;
          }
          this.syncLinearQty(index);
        } else if (this.isBlank(line.qty)) {
          line.qty = line.baselineQty;
        }
        if (this.isBlank(line.unitPrice)) {
          line.unitPrice = line.baselineUnitPrice;
        }
      });
    },

    recompute() {
      this.lines.forEach((_line, index) => this.syncLinearQty(index));
      this.validate();
      let subtotal = 0;
      let linesComplete = true;
      this.lines.forEach((_line, index) => {
        const lineTotal = this.lineTotal(index);
        if (lineTotal === null) {
          linesComplete = false;
          return;
        }
        subtotal += lineTotal;
      });
      const shipping = this.effectiveShipping();
      if (shipping === null || !linesComplete) {
        this.totalsReady = false;
        return;
      }
      this.subtotal = this.roundMoney(subtotal);
      const taxable = this.roundMoney(this.subtotal + shipping);
      this.taxAmount = this.roundMoney(taxable * this.taxRate);
      this.total = this.roundMoney(taxable + this.taxAmount);
      this.totalsReady = true;
    },

    formatMoney(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "—";
      }
      return (
        Number(value).toLocaleString("fr-FR", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }) +
        " " +
        this.currency
      );
    },

    displayTotal() {
      return this.totalsReady ? this.formatMoney(this.total) : "—";
    },

    displaySubtotal() {
      return this.totalsReady ? this.formatMoney(this.subtotal) : "—";
    },

    displayShipping() {
      const shipping = this.effectiveShipping();
      if (shipping === null) return "—";
      return this.formatMoney(shipping);
    },

    displayTax() {
      return this.totalsReady ? this.formatMoney(this.taxAmount) : "—";
    },

    onSubmit(event) {
      this.restoreBlanksFromBaseline();
      this.recompute();
      if (!this.validate()) {
        event.preventDefault();
        return false;
      }
      return true;
    },
  }));
}

document.addEventListener("alpine:init", registerStaffBillingAdjustment);
if (window.Alpine) {
  registerStaffBillingAdjustment();
}

document.body.addEventListener("htmx:beforeSwap", (event) => {
  const target = event.detail?.target;
  if (!target || !window.Alpine || typeof Alpine.destroyTree !== "function") {
    return;
  }
  if (target.querySelector?.("[data-billing-adjustment]") || target.matches?.("[data-billing-adjustment]")) {
    Alpine.destroyTree(target);
  }
});

document.body.addEventListener("htmx:afterSwap", (event) => {
  const target = event.detail?.target;
  if (!target || !window.Alpine || typeof Alpine.initTree !== "function") {
    return;
  }
  if (target.querySelector?.("[data-billing-adjustment]") || target.matches?.("[data-billing-adjustment]")) {
    Alpine.initTree(target);
  }
});
