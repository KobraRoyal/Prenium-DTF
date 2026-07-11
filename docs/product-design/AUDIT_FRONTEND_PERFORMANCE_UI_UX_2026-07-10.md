# Audit frontend UI/UX et performance — 10 juillet 2026

## Verdict

**Score global : 95 / 100 — landing premium.** La proposition DTF B2B est comprise rapidement, le CTA principal est visible sur mobile, la direction « atelier éditorial » est distinctive et aucun P1 de clarté, crédibilité ou accessibilité ne reste ouvert.

| Axe | Score | Observation |
| --- | ---: | --- |
| Clarté immédiate | 19 / 20 | Offre, contrôle prépresse et cible B2B explicites dans le hero. |
| Structure & flux | 14 / 15 | Parcours hero → capacités → process → preuves → brief cohérent. |
| Crédibilité | 18 / 20 | Process et traçabilité concrets ; les références client réelles restent à enrichir. |
| Différenciation | 15 / 15 | Univers atelier fort, non générique, cohérent avec le métier DTF. |
| Conversion | 19 / 20 | Accès pro prioritaire, CTA répété et formulaire intégré. |
| Cohérence visuelle & mobile | 10 / 10 | Aucun overflow à 375 px, cibles tactiles et contrastes conformes. |

## Mesures avant / après

Audit Lighthouse mobile exécuté sur la même stack Docker locale (`http://127.0.0.1:8080/`).

| Indicateur | Avant | Après |
| --- | ---: | ---: |
| Performance | 68 | **98** |
| Accessibilité | 95 | **100** |
| Bonnes pratiques | 100 | **100** |
| SEO | 100 | **100** |
| First Contentful Paint | 4,3 s | **1,0 s** |
| Largest Contentful Paint | 5,8 s | **2,4 s** |
| Speed Index | 4,3 s | **1,0 s** |
| Total Blocking Time | 0 ms | **0 ms** |
| Cumulative Layout Shift | 0 | **0** |

## Corrections livrées

- Polices variables DM Sans et Space Grotesk auto-hébergées, préchargées et servies sans dépendance Google Fonts.
- Runtime marketing dédié : la landing et Services ne chargent plus HTMX et Alpine inutilement.
- Compression gzip Nginx et cache statique immuable de 30 jours.
- Rendu différé des sections hors écran avec taille intrinsèque sur l’axe vertical uniquement.
- Hero mobile resserré : promesse plus courte, deux CTA sur une ligne et deux preuves prioritaires.
- Contrastes des CTA et cartes colorées corrigés jusqu’au score Lighthouse accessibilité 100.
- Menu mobile, desktop, Services et Connexion validés dans un navigateur réel, console sans erreur ni avertissement.

## Backlog restant

### P1

Aucun.

### P2

- Ajouter des preuves client vérifiables (cas chiffrés, logos autorisés ou témoignages réels) quand les contenus seront disponibles.
- Brancher une mesure terrain RUM/Core Web Vitals en production pour compléter la mesure Lighthouse locale.

### P3

- Générer une variante responsive plus légère de l’image hero pour les écrans étroits.
- Étudier un découpage CSS par surface si le volume du design system continue de croître.

## Checklist de validation

- [x] Landing desktop 1440 × 1000.
- [x] Landing et Services mobile 375 × 812 sans overflow horizontal.
- [x] Menu mobile ouvert/fermé et libellé accessible synchronisé.
- [x] Page Connexion vérifiée après allègement du runtime marketing.
- [x] Console navigateur : 0 erreur, 0 avertissement.
- [x] Lighthouse : 98 performance, 100 accessibilité, 100 bonnes pratiques, 100 SEO.
- [x] Compression gzip et cache statique vérifiés sur Nginx.
- [x] `npm audit` : 0 vulnérabilité connue.
- [x] Suite complète : 263 tests passés.
- [x] Ruff check/format et `manage.py check` validés.

