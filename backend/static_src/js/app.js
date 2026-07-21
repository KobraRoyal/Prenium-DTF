import "./htmx/swap-state.js?v=20260710b";
import "./htmx/feedback.js?v=20260710b";
import "./landing-motion.js?v=20260710b";
import "./product-shell.js?v=20260710b";
import "./product-date-picker.js?v=20260712a";
import "./b2b-configurator.js?v=20260716a";
import "./email-template-editor.js?v=20260714c";
import "./gang-sheet-editor.js?v=20260716b";

window.preniumToast = function (message, variant = "info") {
  window.dispatchEvent(
    new CustomEvent("prenium-toast", {
      detail: { message, variant },
    })
  );
};
