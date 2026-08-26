# Sprint 49 — Mot de passe oublié

Date : 2026-08-25  
Statut : **terminé**

## Objectif

Permettre à un compte existant de réinitialiser son mot de passe depuis `/login/`, avec un recours support visible, sans révéler si l’adresse existe.

## Architecture livrée

- Service `PasswordResetService` : éligibilité, jeton Django, `public_id` dans l’URL (jamais l’ID incrémental), audit.
- Vues portail `/mot-de-passe-oublie/` → e-mail → lien signé 24 h → nouveau mot de passe.
- E-mail transactionnel `password_reset` (audience compte), surchargeable comme les autres modèles Atelier.
- Rate limit IP sur POST `/mot-de-passe-oublie/` + plafond par adresse e-mail.
- Copie de confirmation identique qu’un compte existe ou non.

## Sécurité

- Pas de fuite d’existence de compte dans la réponse HTTP.
- Jeton invalidé après usage ou changement de mot de passe (`PASSWORD_RESET_TIMEOUT=86400`).
- Le lien de confirmation retire le jeton de l’URL (session) avant le formulaire, pour limiter la fuite Referer.
- Comptes inactifs ou sans mot de passe utilisable : aucun e-mail.
- Audit `security.password_reset.requested` / `completed` / `password_reset_rate_limited`.

## UX

- Lien « Mot de passe oublié ? » à côté du champ mot de passe.
- Recours support : `SUPPORT_CONTACT_EMAIL` (mailto) ou message de repli.

## Validation

- [x] Tests service/vues : succès, inconnu, inactif, throttle, rate limit, jeton unique, UID `public_id`.
- [x] Tests UI login / cartes auth.
- [x] Documentation baseline sécurité et recette.
