import "./htmx/swap-state.js?v=20260710b";
import "./htmx/feedback.js?v=20260710b";
import "./landing-motion.js?v=20260710b";
import "./product-shell.js?v=20260721g";
import "./product-date-picker.js?v=20260712a";
import "./b2b-configurator.js?v=20260725-support-modal-3";
import "./email-template-editor.js?v=20260714c";
import "./gang-sheet-editor.js?v=20260726-create-order-form";

window.preniumToast = function (message, variant = "info") {
  window.dispatchEvent(
    new CustomEvent("prenium-toast", {
      detail: { message, variant },
    })
  );
};
