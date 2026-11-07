import "./htmx/swap-state.js?v=20260829-order-tabs-v2";
import "./htmx/feedback.js?v=20260710b";
import "./landing-motion.js?v=20260710b";
import "./product-shell.js?v=20261107-submit-loading-defer-v2";
import "./product-date-picker.js?v=20260918-date-portal-v2";
import "./b2b-configurator.js?v=20261107-checkout-required-v1";
import "./email-template-editor.js?v=20260813-email-workbench";
import "./gang-sheet-editor.js?v=20261107-checkout-required-v1";
import "./clipboard-copy.js?v=20260829-of-copy-v1";
import "./staff-billing-adjustment.js?v=20261105-laize-meter-price-v2";

window.preniumToast = function (message, variant = "info") {
  window.dispatchEvent(
    new CustomEvent("prenium-toast", {
      detail: { message, variant },
    })
  );
};
