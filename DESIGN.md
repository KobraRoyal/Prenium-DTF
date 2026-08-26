---
name: Prenium DTF
description: Portail B2B DTF clair — production cadrée, fichiers contrôlés, suivi atelier.
colors:
  bg: "#f4f0e6"
  surface: "#fbf6ee"
  raised: "#fffdf8"
  ink: "#1a1815"
  muted: "#6b675c"
  line: "#e2dccb"
  brand: "#ff8775"
  brand-strong: "#e65944"
  accent: "#a83bc4"
  focus: "#770176"
  success: "#287451"
  warning: "#8b5d08"
  danger: "#a33b45"
  action-text: "#1a1815"
typography:
  display: {fontFamily: "Space Grotesk, system-ui, sans-serif", fontWeight: 700, lineHeight: 1.05}
  headline: {fontFamily: "Space Grotesk, system-ui, sans-serif", fontWeight: 700, lineHeight: 0.98}
  body: {fontFamily: "DM Sans, system-ui, sans-serif", fontWeight: 400, lineHeight: 1.45}
  label: {fontFamily: "DM Sans, system-ui, sans-serif", fontWeight: 650, lineHeight: 1.35}
rounded:
  sm: "14px"
  md: "16px"
  lg: "18px"
  pill: "999px"
spacing:
  page: "clamp(1rem, 3vw, 1.75rem)"
  section: "clamp(1rem, 2vw, 1.5rem)"
  action: "0.65rem 1.05rem"
components:
  button-primary: {backgroundColor: "{colors.brand}", textColor: "{colors.action-text}", rounded: "{rounded.pill}", padding: "{spacing.action}", height: "2.75rem"}
  button-secondary: {backgroundColor: "{colors.surface}", textColor: "{colors.ink}", rounded: "{rounded.pill}", padding: "{spacing.action}", height: "2.75rem"}
  input: {backgroundColor: "{colors.surface}", textColor: "{colors.ink}", rounded: "{rounded.sm}", padding: "0.65rem 0.8rem", height: "2.75rem"}
---

## Overview

**Creative North Star: « Atelier clair et chaleureux »**

Prenium DTF est une régie prépresse pour des professionnels qui doivent comprendre un état, agir, puis laisser une trace exploitable. La THESIS est : « Prenium DTF makes every production state legible at a glance, with one calm light shell and one coral action per view. » Le monde construit repose sur un fond crème chaud, des panneaux blancs cassé, un header blanc compact, des lignes fines et des marques de contrôle corail.

La story guide chaque surface : fil d’Ariane, titre d’état, badges calmes, puis une seule prochaine action. La landing est **Persuade**; Client, Atelier et Studio sont **Operate**. Le canevas Studio reste clair pour la fidélité prépresse ; ses poignées, guides, sélection et focus utilisent le corail de marque.

Les routes, permissions, modèles, isolation multi-tenant et logique métier restent inchangés. Les parcours essentiels visent WCAG AA : clavier, focus visible, labels explicites, erreurs actionnables, cibles tactiles `2.75rem`, `prefers-reduced-motion` respecté et aucun contenu essentiel dépendant d’un reveal JavaScript.

**Key Characteristics:**

- Header produit partagé (`ui-foundation-nav`) : lockup corail, nav pills, workspace Atelier/Client, menu compte.
- Fil d’Ariane uppercase sous le header sur toutes les vues authentifiées à profondeur > 1.
- Cartes blanches sur fond crème ; badges sage/ambre pour les statuts métier.
- Une action primaire corail par vue, sans prompts dupliqués.

## Colors

La palette est chaude et mate : le crème accueille, le blanc cassé porte, le corail signale l’action et l’accent violet renforce le focus clavier.

### Primary

- **Corail de marque** (`#ff8775`): action primaire, repère lockup, sélection Studio.
- **Corail fort** (`#e65944`): hover et présence renforcée.

### Neutral

- **Fond crème** (`#f4f0e6`): arrière-plan global produit et portail.
- **Surface blanche cassée** (`#fbf6ee`): header, cartes, champs.
- **Surface levée** (`#fffdf8`): panneaux renforcés et cartes de lecture.
- **Encre chaude** (`#1a1815`): texte principal.
- **Encre muette** (`#6b675c`): aide, métadonnées, labels de facts.
- **Ligne sable** (`#e2dccb`): bordures 1px et séparateurs.

### Status

- **Focus accent** (`#770176`): anneau clavier.
- **Succès sage** (`#287451`), **avertissement ambre** (`#8b5d08`) et **danger rouge** (`#a33b45`): états métier.
- **Texte d’action** (`#1a1815`): texte sur boutons corail.

**The Signal Scarcity Rule.** Le corail est réservé aux actions, sélections, focus et marques d’inspection ; il ne remplit pas les surfaces pour les décorer.

## Typography

**Display Font:** Space Grotesk (avec `system-ui, sans-serif`)

**Body Font:** DM Sans (avec `system-ui, sans-serif`)

Space Grotesk structure titres, navigation et chiffres ; DM Sans porte données, formulaires et statuts.

### Hierarchy

- **Display** (700, taille fluide, line-height proche de 1.05): promesse landing et titres majeurs.
- **Headline** (700, échelle compacte à fluide): état principal d’un dashboard ou d’une fiche focus.
- **Title** (700, panneaux et regroupements).
- **Body** (400, environ 0.88–1rem, 1.45–1.55): instructions et données.
- **Label** (650–700, 0.72–0.88rem, uppercase pour facts et breadcrumb).

**The Two-Voice Rule.** Space Grotesk structure et signale ; DM Sans explique et renseigne.

## Layout

Le shell utilise un conteneur jusqu’à `1180px`, un padding horizontal `clamp(1rem, 3vw, 1.75rem)` et des écarts de section `clamp(1rem, 2vw, 1.5rem)`.

Structure type d’une vue Operate :

1. Header fixe blanc (`product-header`, `ui-foundation-nav`).
2. Fil d’Ariane (`ui-breadcrumb`) quand la profondeur le justifie.
3. Titre premium (`page-head--premium`) ou carte focus (`staff-*-focus`, `client-order-summary`).
4. Contenu : table `ui-data-table`, cartes `ui-data-card` ou workspace `details`.

Landing, Client, Atelier et Studio partagent tokens et lockup ; seule la densité varie. Vérification 1440px et 375px sans overflow horizontal.

## Elevation & Depth

La profondeur est tonale d’abord : `bg` crème, `surface` blanche, `line` pour séparer. Ombres douces et chaudes uniquement sur header et cartes levées : `0 8px 24px rgba(83, 67, 43, 0.08)` ; pas d’ombres dures offset.

**The Tonal Tray Rule.** Une surface se distingue par son ton et sa ligne avant de se distinguer par une ombre.

## Shapes

14px pour petits contrôles, 16px pour panneaux courants, 18px pour surfaces majeures, `999px` pour actions, badges, tabs et nav pills. Bordures fines ; pas de style brutaliste.

## Components

### Buttons

`buttons.css` possède primaire, secondaire, ghost et danger, y compris alias `.btn-*`, `.dui-btn-*`. Primaire corail pill `2.75rem` ; secondaire surface bordée ; ghost transparent pour nav et actions tertiaires.

### Inputs / Fields

Surface blanche, bordure `line`, rayon 14px, hauteur `2.75rem`. Focus accent ; erreur danger ; labels et aide explicites via `ui-field-group`.

### Cards / Containers

Cartes blanches bordées `1px var(--line)`, rayon 16–18px. Fiches focus staff/client regroupent identité, badges et facts en grille horizontale séparée par lignes verticales fines.

### Pages d’erreur HTTP

`templates/404.html` réutilise le shell auth Operate (`product-shell--auth`, carte `product-error-card`) : code discret brand, titre Space Grotesk, CTAs `ui-btn`, recours support. Handler : `handler404` dans `config/urls.py`. Visible avec `DEBUG=False`.

### Tables / listes responsives

`shell.css` possède `ui-table-shell`, `ui-data-table`, `ui-data-card`, `ui-mobile-order-card`, `ui-list-pagination`. Breakpoint table/cartes : 960px. `components/portal/pagination.html` et `components/forms/form_actions.html` mutualisent pagination et actions.

### Navigation / Status

Header : lockup corail, label workspace (point vert « Atelier » / « Espace client »), nav pills avec état actif fond corail pâle, dropdown « Outils » staff, menu « Mon compte ». Breadcrumbs : partials `staff_trail.html` et `client_trail.html` ; wrappers par section pour compatibilité.

Badges : pills calmes `is-success`, `is-warning`, `is-danger`, `is-neutral`.

### Studio crop / inspection

Canevas clair ; chrome, toolbar et poignées corail. `studio-polish.css` reste prioritaire sur les règles legacy de l’éditeur.

## Do's and Don'ts

- **Do** réutiliser `portal/layout.html`, `portal_header.html`, `page_head.html` et les partials breadcrumb.
- **Do** utiliser `#f4f0e6`, `#fbf6ee`, `#fffdf8` et `#e2dccb` pour organiser les niveaux.
- **Do** réserver `#ff8775` et `#e65944` aux actions, sélections et repères d’inspection.
- **Do** vérifier 375px et 1440px, le clavier, les erreurs et `prefers-reduced-motion`.
- **Don't** réintroduire le thème sombre graphite, le lime acide, les ombres dures offset ou le glassmorphism.
- **Don't** dupliquer pagination, tables, boutons ou breadcrumbs si le contrat `ui-*` couvre le besoin.
- **Don't** ajouter gradients décoratifs, eyebrows ou CTA dupliqués sur une même vue.
- **Don't** créer de styles locaux de table ou header si `shell.css` / `product-polish.css` couvrent déjà le cas.
