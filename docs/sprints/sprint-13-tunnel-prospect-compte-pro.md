# Sprint 13 — Tunnel prospect / ouverture de compte pro

## Statut
Livré (implémentation initiale).

## Objectif
Parcours distinct du checkout pour qualifier un visiteur, collecter besoin/volume, puis créer **User + Customer (owner) + ProspectProfile** avec audit.

## Décisions
- **App `apps.prospects`** : modèle `ProspectProfile`, pas de confusion avec `Order` ni checkout.
- **Session** (`prospect_tunnel_v1`) : brouillon par étapes ; vidage après succès.
- **Statuts** : `new` → à la création compte `account_created` (pas d’état `qualified` séparé dans le flux MVP).
- **Source** : `tunnel_web` par défaut.
- **Sécurité** : validations formulaires Django + mot de passe `validate_password` ; email unique vérifié en service ; `@sensitive_post_parameters` sur l’étape mot de passe ; audit `prospect.account_created`.
- **Confirmation** : session one-shot `prospect_confirmation_public_id` + repli sur `user.prospect_profile` au rechargement.

## Fichiers principaux
- `backend/apps/prospects/` (models, forms, views, urls, services, admin, migrations)
- `backend/templates/prospects/*.html`
- `backend/static_src/css/components/prospect-tunnel.css`
- `tests/prospects/test_prospect_tunnel.py`

## URLs
- `/compte-pro/etape-1/` … `/etape-4/`, `/compte-pro/confirmation/`

## Risques / suite
- Pas d’email transactionnel (hors périmètre).
- Pas de rate-limit dédié (à ajouter si abus).
- Qualification commerciale : champs prêts, pas de scoring.

## Commandes
```bash
cd backend && npm run build:css
cd backend && python manage.py migrate
```

## Tests
```bash
pytest tests/prospects/test_prospect_tunnel.py -q
```
