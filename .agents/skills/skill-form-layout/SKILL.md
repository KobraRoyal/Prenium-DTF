---
name: skill-form-layout
description: Layout formulaires Prenium DTF — field_group, form_actions, classes ui-* (forms.css).
---

# Formulaires

- Partials : `templates/components/forms/field_group.html`, `form_actions.html`.
- Styles : `static_src/css/components/forms.css` (`.ui-form-stack`, `.ui-input`, `.ui-sr-only`).
- Login de référence : `templates/portal/login.html` (libellés visibles, pas `ui-sr-only`).
- Auth : `novalidate` + `data-inline-required` sur le `<form>`. Les champs manquants s’affichent en `error-text ui-error-text` sous le champ (`ui-input--error`, `aria-invalid`), jamais via le tooltip HTML5 natif. La bannière `alert--danger` est réservée aux erreurs non liées à un champ (ex. identifiants incorrects via `form.non_field_errors`).
- Runtime : `product-shell.js` (`validateInlineRequiredForm`) lit `data-missing-message` / `data-invalid-message`.
- Champs Django : réutiliser `field_group` avec `label`, `name`, `id`, `type`, `required`, `error`, `help_text`.
- `field_group` et les champs texte tunnel : libellé toujours en `ui-sr-only` ; indication visible via `placeholder` (texte du label par défaut si non fourni). Passer `placeholder="…"` pour un texte différent du libellé. Fieldsets à choix (tunnel prospect) : `legend` en `ui-sr-only`, titres de page + cartes portent le sens visuel.
