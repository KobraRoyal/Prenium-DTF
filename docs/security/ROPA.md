# Registre des traitements (ROPA) — Prenium DTF

Document de travail Art. 30. À tenir à jour à chaque nouveau sous-traitant.

| Traitement | Finalité | Base | Catégories | Destinataires | Durée |
|---|---|---|---|---|---|
| Comptes portail | Authentification, rôles | Contrat | Identité, e-mail, hash mot de passe | Interne | Vie du compte + anonymisation |
| Demandes d’accès | Qualification B2B | Art. 6.1.b | Identité, téléphone, société, SIREN | Interne | 24 mois si refus/expiré puis anonymisation |
| Commandes / production | Exécuter le contrat | Contrat | Commande, fichiers, notes | Atelier, Drive si activé | Pièces comptables 10 ans |
| Expédition | Livraison | Contrat | Destinataire (nom, adresse, e-mail, tél.) | Sendcloud, transporteur | Snapshot interne rédigé ; prestataire selon sa politique |
| Paiement en ligne | Encaissement | Contrat | Montants, IDs prestataire | Stripe / PayPal | IDs ; JSON brut minimisé (90 j) |
| Facturation | Obligation légale | Art. 6.1.c | Relevé, facture, SIREN, adresses | Comptabilité | 10 ans |
| Journaux d’audit | Sécurité | Art. 6.1.f | Action, acteur, IP | Interne | IP 365 j |
| E-mails transactionnels | Suivi commande / accès | Contrat | E-mail destinataire | SMTP | Selon prestataire mail |

Responsable : `LEGAL_CONTROLLER_NAME` (IDS Supply par défaut). Contact : `LEGAL_PRIVACY_EMAIL`.
