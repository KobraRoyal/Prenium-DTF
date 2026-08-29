import "./htmx/swap-state.js?v=20260829-order-tabs-v2";
import "./htmx/feedback.js?v=20260710b";
import "./landing-motion.js?v=20260710b";
import "./product-shell.js?v=20260828-inline-required";
import "./product-date-picker.js?v=20260712a";
import "./b2b-configurator.js?v=20260826-modal-impeccable-v159";
import "./email-template-editor.js?v=20260813-email-workbench";
import "./gang-sheet-editor.js?v=20260828-studio-groups-v23";

window.preniumToast = function (message, variant = "info") {
  window.dispatchEvent(
    new CustomEvent("prenium-toast", {
      detail: { message, variant },
    })
  );
};
