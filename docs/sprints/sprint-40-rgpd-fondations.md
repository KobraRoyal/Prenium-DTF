# Sprint 40 — Fondations RGPD

## Objectif

Rendre le produit **présentable** au regard du RGPD sans casser le métier : information des personnes, exercice des droits, minimisation des traces techniques, rétention.

Les textes légaux sont des **modèles à faire relire par un conseil**. Renseigner SIREN, adresse et e-mails via les variables `LEGAL_*`.

## Livré

- Pages publiques : mentions, confidentialité, cookies, accord de sous-traitance (accessibles même si l’accueil redirige vers le login).
- Pied de landing + login + case du tunnel prospect liés à ces pages.
- Portail **Mon compte → Données** : export JSON, clôture/anonymisation (sauf comptes atelier).
- Réinitialisation de mot de passe, rate-limitée comme le login.
- Payloads Stripe/PayPal et snapshots destinataires Sendcloud minimisés en base (l’API Sendcloud reçoit toujours l’adresse complète).
- Tâche Celery quotidienne `core.apply_privacy_retention`.

## Hors périmètre (volontaire, anti-régression)

- MFA staff (flags déjà en base, pas de TOTP).
- CMP / bandeau cookies (aucun tracker aujourd’hui).
- Désactivation de Google Drive (reste optionnel ; mentionné dans la politique si activé).
- Signature juridique des DPA prestataires (Stripe, PayPal, Sendcloud, SMTP).

## Fichiers clés

- `backend/apps/core/legal.py`, vues et templates `shop/legal/`
- `backend/apps/accounts/services/privacy.py`
- `backend/apps/portal/views_privacy.py`, `views_password_reset.py`
- `docs/security/ROPA.md`, `docs/security/BREACH_PLAYBOOK.md`

## Tests

- `tests/core/test_legal_pages.py`
- `tests/accounts/test_privacy_rights.py`
- `tests/accounts/test_password_reset.py`
- `tests/core/test_privacy_retention.py`
- accès croisé export + régression Sendcloud / login

## Checklist de validation

- [ ] Renseigner `LEGAL_CONTROLLER_*` et e-mails privacy en production
- [ ] Relire les 4 pages légales
- [ ] Vérifier un export JSON sur un compte client de recette
- [ ] Vérifier qu’un compte atelier ne peut pas se clôturer
- [ ] Confirmer que Beat exécute `core.apply_privacy_retention`
