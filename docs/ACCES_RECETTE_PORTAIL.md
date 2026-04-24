# Accès recette — portail client, staff et admin

Document de rappel pour tester l’application avec différents profils (local ou Docker).

## URLs (ex. Docker : Nginx sur le port `8080`)

| Surface | URL typique |
|--------|-------------|
| Landing | `http://localhost:8080/` |
| Services | `http://localhost:8080/services/` |
| **Connexion portail** (client + staff métier) | `http://localhost:8080/login/` |
| Espace **client** | `http://localhost:8080/client/` |
| Backoffice **staff** (portail métier) | `http://localhost:8080/staff/` |
| **Admin Django** (technique, modèles) | `http://localhost:8080/admin/` |

Adapter le port si votre `.env` définit autre chose (ex. `NGINX_PORT`).

## Comptes seed (mot de passe commun)

Création / mise à jour des utilisateurs de démo :

```bash
# Depuis la racine du repo, avec le conteneur web :
docker compose exec web python manage.py seed_sprint09_recipe
```

Réinitialiser complètement les données du seed :

```bash
docker compose exec web python manage.py seed_sprint09_recipe --reset
```

**Mot de passe pour tous les comptes ci-dessous : `pass1234`** (réservé recette — ne pas réutiliser en production).

| Email | Usage |
|--------|--------|
| `admin@prenium.local` | Superuser → connexion **`/admin/`** (administration Django) |
| `staff.ops@prenium.local` | Staff → portail **`/staff/`** (permissions larges : commandes, fichiers, production, expédition, **facturation / tarif**) |
| `staff.limited@prenium.local` | Staff → portail limité (peu de permissions métier) |
| `client.a.owner@prenium.local` | Client propriétaire (tenant A) → **`/client/`** |
| `client.a.member@prenium.local` | Client membre (tenant A) |
| `client.b.owner@prenium.local` | Client propriétaire (tenant B) — tests **isolation** entre clients |
| `hybrid.ops.client@prenium.local` | Hybride staff + client — recette **séparation de contexte** |

Sans exécuter `seed_sprint09_recipe`, ces comptes n’existent pas en base.

## Données seed (architecture B2B actuelle)

La commande crée des commandes en **facturation différée** (`billing_mode = deferred`), **sans lignes tarifées** tant que le staff n’a pas lancé le calcul : les montants viennent de `OrderPricingService` après saisie métrage (seed : métrage linéaire commande) ou contrôle.

- **Profils facturation** : `CustomerBillingProfile` pour Seed Client A (mensuel, 25 €/m², plafond encours 5000 €) et Seed Client B (bi-mensuel, 18,50 €/m², plafond 1500 €, blocage encours actif).
- **Scénarios** (repère : `customer_note` sur `Order`) :

| `customer_note` | Idée métier |
|-----------------|-------------|
| `SEED09:A_B2B_DRAFT` | Brouillon + 1 fichier (soumission pas faite) |
| `SEED09:A_B2B_SUBMITTED` | Soumise, 4 fichiers (états inspection / Drive variés), **prix en attente** |
| `SEED09:A_B2B_PRICED` | Tarifée (métrage seed) |
| `SEED09:A_B2B_IN_PRODUCTION` | Tarifée + OF en production |
| `SEED09:A_B2B_READY_SHIP` | Tarifée + prête à expédier |
| `SEED09:A_B2B_SHIPPED` | Terminée + expédition seed |
| `SEED09:A_B2B_SHIPPING_FAILED` | Expédition en échec simulé |
| `SEED09:B_B2B_1` | Client B — commande simple soumise |
| `SEED09:B_B2B_BLOCKED` | Client B — OF bloqué |

Voir aussi la vue d’ensemble métier : [architecture/B2B_PRODUCT_AND_OPERATIONS.md](./architecture/B2B_PRODUCT_AND_OPERATIONS.md).

## Comment se connecter

1. Aller sur **`/login/`** (pas sur `/admin/login/` pour le portail applicatif).
2. Saisir email + mot de passe seed.
3. Redirection automatique vers **dashboard client** ou **dashboard staff** selon le profil.

## Rappels sécurité / produit

- **`/admin/`** = surface **technique** Django (superuser), distincte du **portail staff** métier (`/staff/`).
- L’accès staff applicatif exige en général `is_staff` **et** la permission Django **`accounts.access_staff_portal`** (voir décisions projet).
- Les routes client sont sous **`/client/`**, les routes staff sous **`/staff/`** — ne pas mélanger les contextes en recette.

## Après changement de CSS / templates (Docker)

Si la page ne reflète pas les derniers fichiers :

```bash
docker compose restart web
```

## Référence détaillée sprint

- `docs/sprints/sprint-09-ui-front-premium.md` (section *Seed data recette*)
- Commande : `backend/apps/core/management/commands/seed_sprint09_recipe.py`
