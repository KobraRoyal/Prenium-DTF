import "./htmx/swap-state.js?v=20260710b";
import "./htmx/feedback.js?v=20260710b";
import "./landing-motion.js?v=20260710b";
import "./product-shell.js?v=20260710b";
import "./product-date-picker.js?v=20260712a";
import "./b2b-configurator.js?v=20260715b";
import "./email-template-editor.js?v=20260714c";

window.preniumToast = function (message, variant = "info") {
  window.dispatchEvent(
    new CustomEvent("prenium-toast", {
      detail: { message, variant },
    })
  );
};
