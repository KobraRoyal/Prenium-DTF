# Sprint 13 — Demande d’accès, validation IDS et équipe client

## Statut

Livré sur la branche `codex/access-approval-team-invitations`.

## Objectif

Transformer l’ancien tunnel de création immédiate en parcours B2B contrôlé :

1. le prospect dépose une demande en trois étapes ;
2. il confirme son adresse e-mail sous 48 heures ;
3. un membre IDS autorisé approuve ou refuse la demande ;
4. après approbation, l’organisation reste inactive jusqu’à l’activation du propriétaire ;
5. le propriétaire ou un administrateur de l’organisation peut inviter des collaborateurs.

## Règles métier

- France : SIREN de neuf chiffres obligatoire.
- Hors France : numéro de TVA ou identifiant fiscal de 4 à 32 caractères alphanumériques obligatoire.
- Une demande ouverte maximum par adresse e-mail normalisée.
- Aucun `User`, `Customer` ou mot de passe n’est créé à la soumission.
- L’approbation crée un `Customer` inactif et une invitation propriétaire valable 72 heures.
- L’organisation devient active seulement après acceptation de cette invitation.
- Une invitation est signée, versionnée, expirante et à usage unique.
- Un compte existant doit être authentifié avec l’adresse invitée.
- Les rôles d’organisation sont `owner`, `admin`, `member` et `readonly`.
- Un administrateur peut gérer l’équipe, mais ne peut pas promouvoir un autre administrateur ; seul le propriétaire garde ce pouvoir.
- Le propriétaire ne peut pas être désactivé depuis l’interface d’équipe.

## Sécurité et isolation

- Routes client basées sur les UUID publics et rescopées par `CustomerMembership` actif.
- Les actions d’équipe refont toutes le contrôle côté serveur ; masquer un bouton ne constitue jamais une autorisation.
- Tests d’accès croisé entre deux organisations.
- Permission staff séparée `prospects.review_prospectprofile` pour décider.
- Transitions métier atomiques et verrouillées en base.
- Audit des soumissions, vérifications, décisions, invitations, acceptations, changements de rôle et désactivations.
- Limite de cinq soumissions par heure et par couple IP/adresse e-mail.
- `X-Forwarded-For` est ignoré par défaut ; ne l’activer que derrière un proxy maîtrisé.
- Les liens publics sont construits depuis `PUBLIC_BASE_URL` ; utiliser impérativement l’URL HTTPS réelle en production.

## Notifications

- vérification de l’adresse du prospect ;
- nouvelle demande vérifiée à l’équipe interne ;
- demande approuvée avec lien d’activation ;
- demande refusée avec motif ;
- invitation d’un collaborateur ;
- confirmation d’activation.

Les modèles sont personnalisables dans le backoffice des e-mails. Les valeurs d’exemple restent réservées à l’aperçu et ne sont jamais injectées dans un envoi réel.

### Correctif invitation équipe — 15 juillet 2026

- La soumission du formulaire équipe rafraîchit désormais le panneau par HTMX, conserve les erreurs inline et affiche immédiatement l’invitation en attente.
- Le message de succès distingue la création en base de la prise en charge asynchrone de l’e-mail ; il ne prétend plus que le SMTP a déjà terminé au retour HTTP.
- La tâche `notifications.send_customer_invitation_email` est couverte par un test de livraison avec lien signé public.
- Cause de l’incident constaté : le worker Celery était resté démarré avec l’ancien registre de tâches et a rejeté la nouvelle tâche comme non enregistrée. Après tout ajout ou renommage de tâche, redémarrer le worker et vérifier son registre avant la recette e-mail.

```bash
docker compose restart worker
docker compose exec -T worker sh -lc \
  'cd /app/backend && celery -A config inspect registered'
```

## URLs principales

- `/demande-acces/etape-1/` à `/demande-acces/etape-3/`
- `/demande-acces/verifier/<token>/`
- `/staff/access-requests/`
- `/acces/invitation/<token>/`
- `/client/customers/<customer_public_id>/team/`

L’ancienne étape 4 redirige vers l’étape 3 pour préserver les anciens liens.

## Configuration

```env
PUBLIC_BASE_URL=https://app.example.com
INTERNAL_NOTIFICATION_EMAILS=access@example.com
TRANSACTIONAL_EMAILS_ENABLED=True
PROSPECT_RATE_LIMIT_MAX_ATTEMPTS=5
PROSPECT_RATE_LIMIT_WINDOW_SECONDS=3600
PROSPECT_RATE_LIMIT_TRUST_X_FORWARDED_FOR=False
```

Les paramètres SMTP existants restent ceux de l’environnement. Aucun secret n’est ajouté au dépôt.

## Checklist de validation

- [x] Modèles et migrations additives créés
- [x] Migration des anciens profils prospect prévue
- [x] Services de transitions et d’invitations centralisés
- [x] Permissions staff et objet client vérifiées côté serveur
- [x] Tests d’accès croisé et d’élévation de rôle ajoutés
- [x] Audit des actions sensibles ajouté
- [x] Notifications asynchrones ajoutées
- [x] Tunnel réduit à trois étapes et identifiant légal conditionnel
- [x] Tunnel complet refondu en « atelier éditorial » pour desktop et mobile
- [x] Étape projet convertie en cartes de choix tactiles accessibles au clavier
- [x] Récapitulatif, consentement et étapes post-envoi clarifiés
- [x] Backoffice de décision et gestion d’équipe ajoutés
- [x] Retour HTMX du formulaire d’invitation avec erreurs inline et état en attente
- [x] Test d’exécution de la tâche e-mail collaborateur et lien signé
- [x] Procédure de rechargement du registre Celery documentée
- [x] Documentation du lot mise à jour
- [ ] Recette SMTP avec le domaine réel en environnement cible
- [ ] Recette navigateur desktop/mobile avec comptes de démonstration

## Commandes de validation

```bash
python manage.py migrate
python manage.py makemigrations --check
pytest tests/prospects tests/customers tests/notifications -q
npm run build:css
```
