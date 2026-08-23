# Recette visuelle — Lot 4 Optimize & Polish

Date : 2026-08-23  
Direction : **Atelier clair et chaleureux** (`DESIGN.md`) — fond crème `#f4f0e6`, surfaces blanches, corail `#ff8775`, violet focus, sans cadres parasites.

## Prérequis

- `npm run build:css` exécuté (bundles `portal-core` + rôle).
- Compte **client** et compte **staff** de test.
- Viewports : **375**, **768**, **1280** px.
- Hard refresh (`Cmd+Shift+R`) après déploiement CSS (`v16`).

## Grille de validation (cocher en recette)

Légende : ✅ conforme · ⚠️ mineur · ❌ bloquant

### Marketing (bundle `marketing.css`)

| Page | URL | Points de contrôle |
|------|-----|-------------------|
| Home | `/` | Fond crème, hero conversion, zéro `agency-*`, CTA corail unique, header sans blur |
| Services | `/services/` | Même shell que home, partials `conversion-*`, pas de section agency |

### Auth (bundle `portal-core.css` seul)

| Page | URL | Points de contrôle |
|------|-----|-------------------|
| Connexion | `/portal/login/` | Carte auth centrée, `ui-input`, pas de nav client/staff |

### Tunnel prospect (`portal-core` + `prospect.css`)

| Page | URL | Points de contrôle |
|------|-----|-------------------|
| Étape 1–3 | `/prospects/…` | Rail progression, champs `ui-input`, erreurs `ui-field-error`, header plat |

### Portail client (`portal-core` + `portal-client.css`)

| Page | URL | Points de contrôle |
|------|-----|-------------------|
| Dashboard | `/portal/client/…/dashboard/` | `page_head`, KPI lisibles, un CTA primaire, fond crème + carte blanche |
| Commandes | `…/orders/` | Pagination partagée, recherche avec `<label for>`, empty state actionnable |
| Projet B2B | `…/order-projects/` | Liste paginée, empty state « Créer une commande » |
| Fiche commande | `…/orders/{id}/` | **Un seul** bandeau statut, onglets HTMX, panels uploads/inspection avec `empty_state` |
| Planches DTF | `…/gang-sheets/` | Liste paginée, cartes sans ombre dure |
| Studio | `…/gang-sheets/{id}/edit/` | + `studio.css`, dialogs sans `product-eyebrow`, espacement `ui-label` |
| Équipe | `…/team/` | Empty state partagé, confirmations destructive |

**Header client (régression v15/v16)**  
- [ ] Pas de bordure grise autour du cluster nav  
- [ ] « Mon compte » ghost sans pill bordée  
- [ ] Liens + CTA « Créer une commande » alignés à droite sans grand vide à gauche  

### Portail staff (`portal-core` + `portal-staff.css`)

| Page | URL | Points de contrôle |
|------|-----|-------------------|
| File Atelier | `/portal/staff/dashboard/` | Files KPI, empty states actionnables |
| Commandes | `/portal/staff/orders/` | `ui-list-section`, pagination |
| Fiche commande | `/portal/staff/orders/{id}/` | Panels inspection/production, pas de double statut |
| Comptes | `/portal/staff/customers/` | Workspace compte, remises |
| Pilotage | `/portal/staff/operations/` | Scan OF, filtres file, commentaire design à jour |
| Demandes accès | `/portal/staff/access-requests/` | File + empty states |

## Budget CSS (mesure locale)

Après `npm run build:css`, comparer les tailles :

| Bundle | Rôle | Cible indicative |
|--------|------|------------------|
| `app.css` | Socle (shell, tokens, boutons) | ~35–45 Ko |
| `portal-core.css` | Header, workflow, shell produit | ~317 Ko minifié |
| `portal-client.css` | Client uniquement | ~37 Ko (+ core ≈ 354 Ko) |
| `portal-staff.css` | Staff uniquement | ~57 Ko (+ core ≈ 374 Ko) |
| `prospect.css` | Tunnel | ~25 Ko (+ core ≈ 342 Ko) |
| `portal.css` (baseline) | Monolithe historique | ~437 Ko — **non chargé en prod** |
| `studio.css` | Éditeur planche | chargé **uniquement** sur studio |

**Gain mesuré (build local v16)** : surface client **−19 %**, staff **−14 %**, prospect **−22 %** vs monolithe.

## Non-régression rapide (5 min)

1. Login → dashboard client → liste commandes → fiche commande (onglet Fichiers vide).  
2. Staff : file atelier → fiche commande → panel Production.  
3. Prospect : step1 → step2 (validation erreur).  
4. Studio : ouvrir une planche, dialog import fichier.  

## Dettes connues (hors recette)

- Purge physique `app-legacy.css` / `landing.css` (hook Impeccable).  
- Miniatures bibliothèque planches (P2-7 audit).  
- Checkout historique : documenté dans `views_checkout.py`, réservé aux comptes sans projets B2B async.
