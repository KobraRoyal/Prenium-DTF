# Sprint 13 — Demande d’accès, validation IDS et équipe client

## Statut

Livré sur la branche `codex/access-approval-team-invitations`.

## Objectif

Transformer l’ancien tunnel de création immédiate en parcours B2B contrôlé :

1. le prospect dépose une demande en deux étapes ;
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

### Expérience file Atelier — 13 août 2026

- La liste affiche les volumes par statut, le nombre de dossiers prêts à examiner et les urgences
  élevées avant toute ouverture de fiche.
- Une recherche serveur permet de retrouver une entreprise, un contact, un e-mail, un SIREN ou
  un identifiant fiscal dans le statut actif ; la recherche est conservée pendant la pagination.
- Le volume mensuel déclaré et l’urgence sont visibles dans le tableau desktop et les cartes
  mobiles afin de prioriser la revue sans masquer les contrôles de permission existants.
- Les états sans résultat expliquent si la file est à jour ou si la recherche doit être élargie.

### Parcours demande d’accès — 3 septembre 2026

- L’étape entreprise demande désormais l’adresse professionnelle avec les mêmes champs que
  `Customer` (`billing_address_line1`, complément, code postal et ville) afin d’éviter une
  ressaisie après validation.
- Le pays reste le pays de facturation ; lors de l’approbation, l’adresse est reprise en
  facturation et en livraison par défaut sur le compte client.
- L’étape projet ne demande plus de choisir un service : elle se concentre sur le besoin,
  le rythme et l’urgence, puis laisse l’orientation service à l’échange humain.
- Le rail latéral et l’indicateur chiffré/barre redondant ont été remplacés par un fil d’Ariane
  horizontal compact, sticky sous la navigation et avec un fond opaque pour rester lisible au
  défilement.
- Sur desktop, le titre du tunnel, son contexte et le fil d’Ariane sont condensés afin que le
  premier bloc de saisie reste visible immédiatement ; le rythme vertical mobile est préservé.
- Les changements d’étape utilisent une transition View Transitions latérale perceptible sur
  desktop et mobile, avec un fallback CSS et le respect de `prefers-reduced-motion`.
- La confirmation est désormais intégrée à l’étape projet : la case d’accord et l’envoi sont
  visibles directement sous le rythme, sans écran de récapitulatif intermédiaire.
- Les champs texte, sélecteurs et cartes radio partagent une hauteur, un rayon et des états
  focus/sélection cohérents ; les radios sont circulaires afin de ne pas être confondues avec
  des cases à cocher.
- Après une validation serveur, un résumé relie chaque erreur au champ concerné, le premier
  champ invalide reçoit le focus et son message est associé pour les technologies d’assistance.
- L’étape finale annonce avant l’envoi l’e-mail de vérification et sa validité de 48 heures ;
  aucune promesse de délai de réponse non confirmée n’est affichée.
- Tous les choix radio du besoin et du rythme affichent désormais le même indicateur circulaire
  à gauche, y compris le volume mensuel et la fréquence de commande.
- Chaque étape valide désormais les champs requis côté navigateur sans masquer le fallback
  serveur : les messages sont associés au contrôle, et un choix radio efface bien son erreur
  quel que soit l’item sélectionné.
- Le tunnel ne charge plus le module CSS historique du portail ; ses styles restent isolés dans
  le bundle prospect, tandis que les règles d’accès et d’équipe partagées ont été extraites dans
  `access-management.css`.
- Le header indique explicitement « Espace client » ou « Atelier » avec le même composant et le
  même rythme visuel selon le rôle.
- Le tunnel public reprend cette structure de header avec « Accès professionnel » et le bloc
  compte ; les alignements desktop et le menu mobile restent ainsi identiques aux portails.
- Les liens de navigation du header restent de simples liens soulignés au survol ou à l’état
  courant : aucune pastille ni bordure ne s’ajoute sur Prospect, Client ou Atelier.
- Le contexte du tunnel est réduit à un titre, une phrase courte et un fil d’Ariane centré ; il
  se fond dans le fond de page sans carte, bordure ou ombre blanche.
- Chaque partie de formulaire ne porte plus qu’une seule surface : le panneau interne reste
  transparent et la confirmation garde uniquement sa carte de consentement.
- Les vues de recette restent anonymisées : aucune donnée personnelle réelle ne doit être
  utilisée dans une capture d’écran ou un exemple partagé.

## URLs principales

- `/demande-acces/etape-1/` à `/demande-acces/etape-2/`
- `/demande-acces/etape-3/` reste une route legacy redirigée vers l’étape projet.
- `/demande-acces/verifier/<token>/`
- `/staff/access-requests/`
- `/acces/invitation/<token>/`
- `/client/customers/<customer_public_id>/team/`

Les anciennes étapes 3 et 4 redirigent vers l’étape projet pour préserver les anciens liens.

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
- [x] Tunnel réduit à deux étapes et identifiant légal conditionnel
- [x] Tunnel complet refondu en « atelier éditorial » pour desktop et mobile
- [x] Étape projet convertie en cartes de choix tactiles accessibles au clavier
- [x] Confirmation intégrée à l’étape projet, sans récapitulatif intermédiaire
- [x] Fil d’Ariane sticky et transitions d’étapes validés sur desktop et mobile
- [x] Champs input, radios et états focus harmonisés sur le tunnel desktop/mobile
- [x] Récupération accessible après erreur et attente post-envoi explicite
- [x] Validation inline des champs requis et cohérence des en-têtes Client / Atelier
- [x] CSS du tunnel isolé du socle portail partagé
- [x] Backoffice de décision et gestion d’équipe ajoutés
- [x] File Atelier enrichie avec compteurs par état, recherche et signaux commerciaux
- [x] Retour HTMX du formulaire d’invitation avec erreurs inline et état en attente
- [x] Test d’exécution de la tâche e-mail collaborateur et lien signé
- [x] Procédure de rechargement du registre Celery documentée
- [x] Adresse professionnelle prospect alignée sur `Customer` et recopiée à l’approbation
- [x] Parcours prospect enrichi avec aide contextuelle et champs d’adresse accessibles
- [x] Documentation du lot mise à jour
- [ ] Recette SMTP avec le domaine réel en environnement cible
- [x] Recette navigateur desktop/mobile de la file Atelier avec compte de démonstration

## Commandes de validation

```bash
python manage.py migrate
python manage.py makemigrations --check
pytest tests/prospects tests/customers tests/notifications -q
npm run build:css
```
