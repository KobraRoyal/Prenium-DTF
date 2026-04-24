# Sprint 14 — Emails transactionnels

## Objectif
Notifier par email les jalons métier sans bloquer les transactions : commande créée, paiement capturé, soumission commande B2B différée.

## Périmètre
- Service centralisé `apps.notifications` (pas de logique dans les templates de vue).
- Envoi après `transaction.on_commit` (pas d’email si rollback).
- Templates texte Django ; expéditeur configurable (`DJANGO_DEFAULT_FROM_EMAIL`).
- Désactivation possible : `TRANSACTIONAL_EMAILS_ENABLED=false`.
- Destinataires : `created_by`, puis `customer.billing_email`, puis premier membership actif.

## Hors périmètre
- Fournisseur tiers type SendGrid API dédiée (reste `django.core.mail`).
- Pièces jointes PDF.
- Files d’attente Celery pour l’email (possible sprint ultérieur si volume).

## Définition de done
- [x] Hooks sur création commande, capture paiement, soumission B2B.
- [x] Tests avec `TestCase.captureOnCommitCallbacks` + outbox.
- [x] Journalisation des échecs d’envoi sans casser le flux métier (`logger.exception`).
