---
name: Prenium DTF
description: Portail B2B DTF — production cadrée, fichiers contrôlés, suivi atelier.
colors:
  ink: "#0b0b0b"
  paper: "#f5f5f2"
  paper-muted: "#e8e8e3"
  acid: "#d9ff2f"
  acid-strong: "#c7f400"
  grey: "#4a4842"
  brand: "#8f3d1f"
  brand-strong: "#6f2f17"
  success: "#1f7a40"
  focus: "#00b8ff"
  agency-paper: "#fff8ea"
  agency-acid: "#dcff1a"
typography:
  display:
    fontFamily: "Space Grotesk, system-ui, sans-serif"
    fontSize: "clamp(2rem, 4vw, 3.5rem)"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Space Grotesk, system-ui, sans-serif"
    fontSize: "clamp(1.5rem, 3vw, 2.25rem)"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Space Grotesk, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "0"
  body:
    fontFamily: "DM Sans, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "0"
  label:
    fontFamily: "DM Sans, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "0.06em"
rounded:
  none: "0px"
  sm: "4px"
  md: "12px"
  lg: "14px"
spacing:
  xs: "0.45rem"
  sm: "0.75rem"
  md: "1.25rem"
  lg: "2rem"
  xl: "4.5rem"
components:
  button-primary:
    backgroundColor: "{colors.acid}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0.85rem 1.25rem"
    height: "2.75rem"
  button-primary-hover:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "0.85rem 1.25rem"
    height: "2.75rem"
  button-product:
    backgroundColor: "{colors.brand}"
    textColor: "{colors.agency-paper}"
    rounded: "{rounded.none}"
    padding: "0.68rem 1rem"
    height: "2.75rem"
  input-field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0.75rem 0.9rem"
    height: "2.75rem"
---

## Overview

Prenium DTF est un produit B2B d’atelier : interfaces sombres/acides sur le marketing, surfaces claires et denses dans le portail authentifié. La promesse visuelle est « Simple pour vous. Cadré pour l’atelier. » — contraste fort, coins droits, typographie uppercase sur les CTA, zéro décor superflu.

Surfaces :
- **Marketing / landing** (`landing-conversion-page`) : ink `#0b0b0b`, paper `#f5f5f2`, accent acid `#d9ff2f`.
- **Tunnel demande d’accès** (`prospect-journey-page`) : même registre product, barre de progression lime.
- **Portail** : tokens `--ui-*` + legacy `--brand` terracotta pour les actions métier.

## Colors

| Rôle | Token | Hex | Usage |
|------|-------|-----|-------|
| Ink | `--conversion-ink` / `--agency-ink` | `#0b0b0b` | Fonds sombres, texte fort |
| Paper | `--conversion-paper` | `#f5f5f2` | Surfaces claires marketing |
| Acid | `--conversion-acid` | `#d9ff2f` | CTA primaires, accents |
| Grey | `--conversion-grey` | `#4a4842` | Texte secondaire sur paper |
| Brand | `--brand` | `#8f3d1f` | Actions portail |
| Success | `--success` | `#1f7a40` | États OK (bordure pleine, pas side-stripe) |
| Focus | `--agency-focus` / `--focus-ring` | cyan / peach | Anneaux `:focus-visible` |

Règle contraste : texte courant ≥ 4,5:1 ; CTA acid → ink obligatoire (`-webkit-text-fill-color` inclus). Ne jamais laisser `color: inherit` gagner sur un CTA.

## Typography

- **Display / titres** : Space Grotesk, weights 700–800, `letter-spacing` ≥ `-0.04em` (cible `-0.035em` sur H1 landing).
- **Body / UI** : DM Sans.
- Labels / CTA : uppercase, tracking léger (`0.02em`–`0.06em`), jamais uppercase sur paragraphes longs.
- `text-wrap: balance` sur H1–H2 marketing.

## Elevation

Système plat / brutaliste : pas d’ombres molles larges. Élévation = translation hard-offset (`4px 4px 0` paper/ink) ou bordure 1–2px. Pas de glassmorphism, pas de gradient décoratif sur le texte.

## Components

- **Boutons marketing** : `.conversion-button--primary` (acid/ink), `--ghost` (bordure paper). Min-height `2.75rem`. Hover : fond paper + ink.
- **Header** : `.agency-nav__cta`, `.agency-nav__link`, `.agency-menu-toggle` — états hover/focus contrastés forcés sous `.landing-conversion-page`.
- **Formulaires produit** : classes `ui-*` (`forms.css`), field groups, actions sticky bas de tunnel.
- **Progress tunnel** : `.prospect-tunnel__track-fill` anime via `transform: scaleX(var(--progress))`, jamais `width`.
- **Feedback succès** : bordure pleine teintée + fond mix — **interdit** `border-left` épais (side-tab).
- **Motion landing (Kinetic Brutalism)** : signature hero (clip-path + acid underline), board stagger + tilt pointer fin, scroll reveals en `transform` only, barre de progression `animation-timeline: scroll()`, `prefers-reduced-motion` coupe tout.

## Do's and Don'ts

**Do**
- Une action primaire claire par vue.
- Contenu visible par défaut ; motion = enhancement (`transform` seulement).
- Respecter `prefers-reduced-motion`.
- Tokens avant hex durs ; documenter toute nouvelle couleur ici.

**Don't**
- Side-stripe / `border-left` > 1px comme accent.
- Masquer le contenu derrière `opacity: 0` / `blur` jusqu’à une classe JS.
- Animer `width` / `height` / `padding` / `margin`.
- Cards imbriquées, glassmorphism, gradients texte, purple SaaS.
- Eyebrows uppercase trackés sur chaque section.
