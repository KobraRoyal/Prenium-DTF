# Système UI/UX Pro Max — 11 juillet 2026

## Objectif

Appliquer les règles UI/UX Pro Max à l’ensemble du frontend Prenium DTF sans diluer son identité « atelier éditorial » ni introduire une esthétique SaaS générique.

## Périmètre

- 68 templates inventoriés dans `backend/templates/`.
- Acquisition : accueil et services.
- Tunnel prospect : étapes 1 à 4 et confirmation.
- Portail client : connexion, dashboard, commandes, détail, checkout et panneaux.
- Portail staff : dashboard, commandes, détail et panneaux opérationnels.
- Composants partagés : navigation, breadcrumbs, formulaires, boutons, onglets, tableaux, feedback et empty states.

## Source de vérité

Le système persistant est disponible dans `design-system/prenium-dtf-ids-hub/` :

- `MASTER.md` : règles globales, tokens, composants, responsive et définition de terminé.
- `pages/public-marketing.md` : acquisition publique.
- `pages/operations-dashboard.md` : client et staff.
- `pages/checkout.md` : checkout et tunnel prospect.

Les recommandations automatiques navy/bleu, glassmorphism, parallax et CTA pulsants ont été écartées car elles contredisaient l’identité existante, la performance ou l’accessibilité. Les règles structurelles UI/UX Pro Max ont été conservées : contraste, cibles tactiles, feedback, hiérarchie, navigation, responsive et reduced motion.

## Correctifs transversaux ajoutés

- Lien clavier « Aller au contenu principal » commun à toutes les surfaces.
- Un unique `main#main-content` sur accueil, services, tunnel, connexion et portails.
- Thème natif clair déclaré sur les vues produit claires afin d’harmoniser les contrôles système.
- Focus du lien d’évitement contrasté, sans animation lorsque reduced motion est actif.
- Contrats automatisés empêchant la disparition du lien d’évitement ou le retour d’un color scheme sombre.

## Validation

| Surface | Performance | Accessibilité | Bonnes pratiques | SEO | CLS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Accueil | 98 | 100 | 100 | 100 | 0 |
| Services | 100 | 100 | 100 | 90 | 0,021 |
| Tunnel prospect | 99 | 100 | 100 | 90 | 0 |
| Connexion | 99 | 100 | 100 | 90 | 0 |

- Recette : 375 × 812, 812 × 375 et 1440 × 1000.
- Aucun débordement horizontal sur les vues contrôlées.
- Console navigateur : 0 erreur, 0 avertissement.
- Lien d’évitement premier élément focusable et cible principale unique.
- Hiérarchie de titres séquentielle corrigée sur checkout et fiches client/staff (`h1` → `h2` → `h3` → `h4`).
- Connexion recentrée sur le formulaire et les bénéfices utiles, sans exposition des rôles ou de l’architecture interne.
- Logo Prenium DTF factorisé et identique sur landing, tunnel, connexion, portail client et portail staff.
- Lighthouse connexion : 99 performance, 100 accessibilité, 100 bonnes pratiques, CLS 0.
- 27 tests de cohérence UI passés.
- Suite complète : 270 tests passés.
- Build CSS, Ruff, formatage et `manage.py check` validés.
- Six services Docker sains.

Les scores SEO à 90 concernent des pages fonctionnelles secondaires sans description marketing dédiée ; ils ne bloquent ni l’usage ni l’accessibilité.
