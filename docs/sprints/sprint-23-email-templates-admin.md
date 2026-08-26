# Sprint 23 — Personnalisation des e-mails transactionnels

Date : 2026-07-14  
Statut : **terminé**

## Objectif

Permettre à l’équipe autorisée de personnaliser depuis le portail Atelier les messages transactionnels envoyés aux clients et aux destinataires internes, sans exécuter de code de template enregistré en base.

## Architecture livrée

- `EmailTemplate` : surcharge globale unique par événement et audience, UUID public, activation, version et auteur.
- `EmailTemplateService` : catalogue des modèles par défaut, validation des tags, rendu texte, sauvegarde transactionnelle et audit.
- Deux audiences : `client` et `internal`.
- Sept événements : commande créée, paiement confirmé, commande en traitement, commande traitée/prête à expédier, commande expédiée, tarification B2B et correction fichier demandée.
- Destinataires internes configurés par `INTERNAL_NOTIFICATION_EMAILS` (liste séparée par des virgules).
- Envoi asynchrone Celery existant conservé ; les tâches résolvent le modèle actif au moment de l’envoi.

## Expérience Atelier — mise à niveau du 13 août 2026

- La liste est présentée comme un registre opérationnel : état du catalogue, diffusion,
  personnalisation, objet envoyé et action restent lisibles sur une même ligne.
- L’éditeur place l’aperçu avant la palette de données et expose immédiatement l’audience,
  l’état de diffusion, la source du modèle et sa version.
- La palette de tags est repliable, recherchable sans accent et limitée en hauteur pour ne plus
  repousser l’aperçu sous plusieurs écrans.
- Le compteur d’objet et l’indicateur « À enregistrer » donnent un retour immédiat sans modifier
  le contrat de validation serveur.
- Le responsive empile le registre, les métadonnées, l’éditeur, l’aperçu et les tags sans
  débordement horizontal ; toutes les actions restent utilisables au clavier.

## Contrat des tags

Tags autorisés :

- `{{ site.name }}`
- `{{ customer.name }}`
- `{{ customer.billing_email }}`
- `{{ order.reference }}`
- `{{ order.public_id }}`
- `{{ order.total_amount }}`
- `{{ order.currency }}`
- `{{ order.status }}`
- `{{ order.billing_mode }}`
- `{{ order.credit_status_message }}`
- `{{ shipment.tracking_number }}`
- `{{ shipment.tracking_url }}`
- `{{ shipment.status }}`
- `{{ upload.filename }}`
- `{{ review.reason }}`
- `{{ review.comment }}`
- `{{ user.email }}`
- `{{ user.first_name }}`
- `{{ action.url }}`

Les instructions Django, commentaires de template, tags inconnus, tags mal formés et retours à la ligne dans l’objet sont refusés.

## Permissions

- consultation : `notifications.view_emailtemplate` + accès portail Atelier ;
- modification/activation : `notifications.change_emailtemplate` + accès portail Atelier ;
- le compte seed `staff.ops@prenium.local` reçoit ces deux permissions ;
- le Django Admin expose les enregistrements en lecture seule, pour éviter un second flux d’édition non audité.

## Définition de terminé

- [x] Modèle et migration additive créés.
- [x] Service métier centralisé et moteur de tags à liste blanche.
- [x] Envoi client et interne branché sur les événements métier, dont la correction fichier Atelier.
- [x] Interface liste/édition/aperçu responsive dans le portail Atelier.
- [x] Registre compact, aperçu prioritaire, recherche de tags et état de modification ajoutés.
- [x] Insertion de tags au curseur et feedback toast.
- [x] Permissions lecture/écriture vérifiées côté serveur.
- [x] Action de modification auditée, sans corps du message dans les logs.
- [x] Tests validation, rendu, version, audit, permissions et double audience.
- [x] Doublon « Commande B2B transmise » supprimé au profit du jalon unique « Commande créée ».
- [x] Jalons métier production et expédition branchés après commit, sans confondre création d’étiquette et départ transporteur.
- [x] `Shipment.shipped_at` empêche les notifications répétées lors des pollings Sendcloud suivants.
- [x] Documentation et audit frontend mis à jour.
- [x] CSS reconstruit et recette navigateur desktop/mobile effectuée.

## Exploitation

Configurer en production :

```env
INTERNAL_NOTIFICATION_EMAILS=atelier@example.com,comptabilite@example.com
```

Une audience sans destinataire configuré est ignorée et journalisée sans exposer d’adresse dans les logs applicatifs.
