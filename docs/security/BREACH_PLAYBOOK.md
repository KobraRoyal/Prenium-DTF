# Playbook violation de données (Art. 33-34)

Objectif : pouvoir notifier la CNIL **sous 72 heures** si la violation est susceptible d’engendrer un risque.

## 1. Détection

Sources : alerte NAS, logs applicatifs, `AuditLogEntry`, signalement interne, prestataire (Stripe, Sendcloud, Google).

## 2. Confinement

- Révoquer secrets exposés (voir runbook déploiement).
- Couper l’accès compromis (compte, token, webhook).
- Ne pas restaurer un dump dans la base active.

## 3. Qualification

Noter : nature, catégories de personnes, volume approximatif, données concernées (e-mail, fichiers, IBAN, etc.), conséquences possibles.

## 4. Notification

- **CNIL** si risque pour les personnes : téléservice notifications, dans les 72 h.
- **Personnes** si risque élevé : e-mail clair, sans exposer d’autres données.
- **Clients B2B** si la violation porte sur des visuels dont ils sont responsables : les informer sans délai injustifié (rôle sous-traitant).

## 5. Trace

Conserver un dossier d’incident (hors git) : chronologie, décisions, preuves de notification.

Contact interne : `LEGAL_PRIVACY_EMAIL`.
