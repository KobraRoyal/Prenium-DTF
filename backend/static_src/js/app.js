import "./htmx/swap-state.js?v=20260710b";
import "./htmx/feedback.js?v=20260710b";
import "./landing-motion.js?v=20260710b";
import "./product-shell.js?v=20260710b";

window.preniumToast = function (message, variant = "info") {
  window.dispatchEvent(
    new CustomEvent("prenium-toast", {
      detail: { message, variant },
    })
  );
};
