import "./htmx/swap-state.js";
import "./htmx/feedback.js";
import "./landing-motion.js";
import "./product-shell.js";

window.preniumToast = function (message, variant = "info") {
  window.dispatchEvent(
    new CustomEvent("prenium-toast", {
      detail: { message, variant },
    })
  );
};
