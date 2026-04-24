---
name: skill-order-tabs
description: Onglets HTMX mutualisés fiche commande — tag Django `order_htmx_tabs`.
---

# Order HTMX tabs

- Tag : `{% load order_tags %}` puis `{% order_htmx_tabs "staff" %}` ou `"client"`.
- Partial : `templates/components/order/order_tabs.html` ; conteneur `.portal-order-tabs` pour le JS.
- JS : `static_src/js/htmx/swap-state.js` (bundlé via `js/app.js`) — état actif des `.chip` + `htmx:afterSwap`.
- Nouvel onglet : ajouter l’entrée dans `apps/portal/templatetags/order_tags.py` (URLs centralisées).
