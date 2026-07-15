# Sprint 14 — Emails transactionnels

## Objectif
Notifier par email les jalons métier sans bloquer les transactions : commande créée, paiement capturé, prise en charge Atelier, commande traitée, expédition et événements nécessitant une action client.

## Périmètre
- Service centralisé `apps.notifications` (pas de logique dans les templates de vue).
- Envoi après `transaction.on_commit` (pas d’email si rollback).
- Modèles texte sécurisés ; expéditeur configurable (`DJANGO_DEFAULT_FROM_EMAIL`).
- Désactivation possible : `TRANSACTIONAL_EMAILS_ENABLED=false`.
- Destinataires : `created_by`, puis `customer.billing_email`, puis premier membership actif.
- Envoi asynchrone Celery avec retry ; déclenchement exclusivement après commit.
- Une soumission B2B est une création de commande, pas un second événement de notification.

## Hors périmètre
- Fournisseur tiers type SendGrid API dédiée (reste `django.core.mail`).
- Pièces jointes PDF.

## Définition de done
- [x] Hook unique de création pour commande immédiate ou soumission B2B.
- [x] Hooks sur capture paiement, première mise en production, fin de traitement et premier scan transporteur.
- [x] Création d’étiquette Sendcloud exclue du jalon « expédiée » tant que le transporteur n’a pas pris le colis en charge.
- [x] Tests avec `TestCase.captureOnCommitCallbacks` + outbox.
- [x] Journalisation des échecs d’envoi sans casser le flux métier (`logger.exception`).

## Extension Sprint 23

Les anciens fichiers de templates Django ont été remplacés par des modèles par défaut dans le service `apps.notifications`, surchargeables depuis le portail Atelier. Le moteur accepte uniquement une liste blanche de tags et n’exécute jamais les instructions Django enregistrées. Voir `sprint-23-email-templates-admin.md`.

## Correctif QA — 2026-07-15

- l’analyse technique d’un fichier ne déclenche aucun e-mail transactionnel ;
- l’accusé « Commande créée » reste exclusivement programmé après la transmission effective de la commande B2B ;
- avant tout transport d’e-mail externe, les domaines réservés aux tests (`example.com`, `example.net`, `example.org`, `.test`, `.invalid` et `.localhost`) sont bloqués centralement ;
- les backends locaux `console`, `dummy`, `filebased` et `locmem` conservent ces destinataires afin que les tests puissent inspecter leurs messages sans livraison externe ;
- le journal de sécurité expose uniquement le domaine bloqué, jamais l’adresse complète.

### Validation

- [x] test de non-déclenchement pendant l’analyse d’un asset ;
- [x] test de blocage d’un destinataire QA avec backend SMTP ;
- [x] test de conservation d’un véritable destinataire client avec backend SMTP ;
- [x] test du jalon normal de soumission B2B conservé.
- [x] suite globale validée (`420 passed`), sans migration.
