document.addEventListener("alpine:init", () => {
  Alpine.data("toastStack", () => ({
    items: [],
    seq: 1,
    push(detail) {
      const payload =
        typeof detail === "string" ? { message: detail, variant: "info" } : detail || {};
      const message = payload.message;
      if (!message) {
        return;
      }
      const variant = payload.variant || "info";
      const id = this.seq++;
      this.items.push({ id, message, variant });
      window.setTimeout(() => {
        this.items = this.items.filter((row) => row.id !== id);
      }, 4500);
    },
    variantClass(variant) {
      const map = {
        success: "ui-toast--success",
        error: "ui-toast--error",
        warning: "ui-toast--warning",
        info: "ui-toast--info",
      };
      return map[variant] || map.info;
    },
  }));
});
