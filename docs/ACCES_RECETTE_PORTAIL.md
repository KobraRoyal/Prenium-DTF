# Accès recette — portail client, staff et admin

Document de rappel pour tester l’application avec différents profils (local ou Docker).

## URLs (ex. Docker : Nginx sur le port `8080`)

| Surface | URL typique |
|--------|-------------|
| Landing | `http://localhost:8080/` |
| Services | `http://localhost:8080/services/` |
| **Page introuvable (404)** | toute URL hors routes (ex. `http://localhost:8080/chemin-introuvable/`) — template Operate `404.html` ; avec `config.settings.dev`, mettre `DJANGO_DEBUG=False` pour la voir (sinon 404 technique Django) |
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
| `staff.ops@prenium.local` | Staff → portail **`/staff/`** (permissions larges : commandes, fichiers, production, expédition, **facturation / tarif**, **demandes d’accès**) |
| `staff.limited@prenium.local` | Staff → portail limité (peu de permissions métier) |
| `client.a.owner@prenium.local` | Client propriétaire (tenant A) → **`/client/`** |
| `client.a.member@prenium.local` | Client membre (tenant A) |
| `client.b.owner@prenium.local` | Client propriétaire (tenant B) — tests **isolation** entre clients |
| `client.cash.owner@prenium.local` | Client **comptant CB** (Seed Client Comptant) — remise volume prospective, Gang Sheet / checkout |
| `hybrid.ops.client@prenium.local` | Hybride staff + client — recette **séparation de contexte** |

Sans exécuter `seed_sprint09_recipe`, ces comptes n’existent pas en base.

## Données seed (architecture B2B actuelle)

La commande crée des commandes en **facturation différée** (`billing_mode = deferred`) pour les clients A et B, **sans lignes tarifées** tant que le staff n’a pas lancé le calcul : les montants viennent de `OrderPricingService` après saisie métrage (seed : métrage linéaire commande) ou contrôle.

Le **Seed Client Comptant** (`client.cash.owner@prenium.local`) est en `default_billing_mode = immediate`, avec les paliers Atelier 5 m −10 % / 10 m −20 %. Aucune commande n’est pré-créée : le parcours à tester est Gang Sheet → devis remisé → paiement CB.

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
2. Saisir email + mot de passe seed. Champs vides : message rouge sous le champ (pas de bulle « Veuillez renseigner ce champ »). Identifiants incorrects : bannière en tête de formulaire.
3. Redirection automatique vers **dashboard client** ou **dashboard staff** selon le profil.
4. Lien **Mot de passe oublié ?** → `/mot-de-passe-oublie/` (e-mail locmem / SMTP selon l’environnement).

## Rappels sécurité / produit

- **`/admin/`** = surface **technique** Django (superuser), distincte du **portail staff** métier (`/staff/`).
- L’accès staff applicatif exige en général `is_staff` **et** la permission Django **`accounts.access_staff_portal`** (voir décisions projet).
- Les routes client sont sous **`/client/`**, les routes staff sous **`/staff/`** — ne pas mélanger les contextes en recette.

## Après changement de CSS / templates (Docker)

Nginx sert les statics depuis le volume **`django_static`** (collectstatic), pas directement `static_src/`.

Si la page ne reflète pas les derniers styles (ombres brutalistes, ancien cache-bust `?v=`…) :

```bash
cd backend && npm run build:css:docker
docker compose restart web
```

Puis hard-refresh navigateur. Les templates portail chargent les bundles de surface avec la version
partagée `?v=20260828-auth-inline-v2` (`portal-core.css`, bundle de rôle, `studio.css` et
`app.js`). Le cache de `gang-sheet-editor.js` reste versionné séparément dans l'import de `app.js`.

## Référence détaillée sprint

- `docs/sprints/sprint-09-ui-front-premium.md` (section *Seed data recette*)
- Commande : `backend/apps/core/management/commands/seed_sprint09_recipe.py`
