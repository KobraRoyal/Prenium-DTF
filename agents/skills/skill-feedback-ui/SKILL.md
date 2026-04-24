---
name: skill-feedback-ui
description: Toasts Alpine + HTMX — preniumToast, en-tête X-Prenium-Toast.
---

# Feedback UI

- Global : `window.preniumToast(message, variant)` avec `variant` ∈ `info|success|warning|error`.
- UI : `components/ui/toast_stack.html` (Daisy `dui-alert-*`).
- HTMX : `static_src/js/htmx/feedback.js` lit `X-Prenium-Toast` sur toutes les réponses (2xx et 4xx) si l’en-tête est présent.
- Backend : `from apps.portal.htmx import with_toast` puis `return with_toast(response, "Message", "success"|"error")` après `render(...)`.
- Build : `npm run build:css` si styles touchés.
