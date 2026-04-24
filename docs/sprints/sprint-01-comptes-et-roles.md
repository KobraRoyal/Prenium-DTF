# Sprint 01 — Comptes et rôles

## Objectif
Poser le socle auth et rôles.

## Tâches
- [x] custom user
- [x] rôles
- [x] groupes / permissions
- [x] auth client
- [x] auth staff
- [x] base MFA backoffice à préparer

## Tests
- [x] login client
- [x] login staff
- [x] accès refusé selon rôle

## Livré
- service centralisé de scope utilisateur client / staff
- querysets scoped sur `Customer` et `CustomerMembership`
- permissions serveur réutilisables pour scope client, owner-only et accès staff
- routes séparées `api/client/...` et `api/staff/...`
- endpoint utilisateur client connecté avec visualisation du scope
- endpoint customer scoped basé sur `public_id`
- endpoint owner-only minimal pour prouver la différence `owner` / `member`
- endpoint staff protégé par permission Django dédiée
- préparation MFA staff via flags `staff_mfa_required` / `staff_mfa_enabled`
- tests positifs et négatifs d’accès croisé et de séparation client / staff

## Validation
- `Customer` est confirmé comme racine d’isolation des futurs objets métier côté client
- `CustomerMembership` reste le support des rôles locaux `owner` / `member`
- `is_staff` seul ne donne pas accès au portail staff sans permission explicite
- toutes les routes privées Sprint 01 sont protégées côté serveur

## Sprint 01.1 — Stabilisation sécurité
### Objectif
Clarifier la surface staff réelle, brancher l’audit minimal sur les changements sensibles déjà possibles, et figer le cas hybride client/staff par test explicite.

### Tâches
- [x] règle `/admin/` clarifiée comme surface d’administration technique
- [x] audit minimal branché sur les changements sensibles déjà exposés
- [x] test explicite du compte hybride client/staff

### Validation
- `/admin/` ne sert pas de surface applicative staff générique
- les changements sensibles déjà possibles doivent laisser une trace d’audit minimale
- le compte hybride client/staff reste sans ambiguïté de scope côté serveur
