---
name: skill-feedback-ui
description: Toasts Alpine + HTMX — preniumToast, en-tête X-Prenium-Toast.
---

# Feedback UI

- Global : `window.preniumToast(message, variant)` avec `variant` ∈ `info|success|warning|error`.
- UI : `components/ui/toast_stack.html` — classes Operate `ui-toast ui-toast--*`, tokens DESIGN.md (pas Daisy `dui-alert`).
- Styles : `static_src/css/components/feedback.css` + verrou portail dans `entries/portal-core.css`.
- HTMX : `static_src/js/htmx/feedback.js` lit `X-Prenium-Toast` sur toutes les réponses (2xx et 4xx) si l’en-tête est présent.
- Backend : `from apps.portal.htmx import with_toast` puis `return with_toast(response, "Message", "success"|"error")` après `render(...)`.
- Build : `npm run build:css:app` (+ `portal-core` si verrou touché) puis `collectstatic`.
