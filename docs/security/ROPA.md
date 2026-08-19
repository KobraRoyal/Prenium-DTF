# Registre des traitements (ROPA) — Prenium DTF

Document de travail Art. 30. À tenir à jour à chaque nouveau sous-traitant. Ce n’est pas un avis juridique.

Responsable : `LEGAL_CONTROLLER_NAME` (IDS Supply par défaut). Contact : `LEGAL_PRIVACY_EMAIL`.

## Traitements internes

| Traitement | Finalité | Base | Catégories | Destinataires | Durée |
|---|---|---|---|---|---|
| Comptes portail | Authentification, rôles | Contrat | Identité, e-mail, hash mot de passe | Interne | Vie du compte + anonymisation |
| Rectification e-mail | Mettre à jour l’identifiant | Contrat / Art. 16 | E-mail actuel et cible, jeton signé | Interne + SMTP | Jeton 24 h ; audit selon rétention |
| Demandes d’accès | Qualification B2B | Art. 6.1.b | Identité, téléphone, société, SIREN | Interne | 24 mois si refus/expiré puis anonymisation |
| Commandes / production | Exécuter le contrat | Contrat | Commande, fichiers, notes | Atelier, Drive si activé | Pièces comptables 10 ans |
| Expédition | Livraison | Contrat | Destinataire (nom, adresse, e-mail, tél.) | Sendcloud, transporteur | Snapshot interne rédigé ; prestataire selon sa politique |
| Paiement en ligne | Encaissement | Contrat | Montants, IDs prestataire | Stripe / PayPal | IDs ; JSON brut minimisé (90 j) |
| Facturation | Obligation légale | Art. 6.1.c | Relevé, facture, SIREN, adresses | Comptabilité | 10 ans |
| Journaux d’audit | Sécurité | Art. 6.1.f | Action, acteur, IP | Interne | IP 365 j |
| E-mails transactionnels | Suivi commande / accès | Contrat | E-mail destinataire | SMTP | Selon prestataire mail |

## Sous-traitants / destinataires

Statut DPA = **à signer** tant qu’aucun contrat signé n’est classé hors git. Ne pas indiquer « signé » sans pièce.

| Prestataire | Finalité | Localisation / transfert | DPA | Doc |
|---|---|---|---|---|
| Stripe | Paiement en ligne | UE + hors UE possible (CCT Stripe) | À signer | [stripe.com/privacy](https://stripe.com/privacy) |
| PayPal | Paiement en ligne | UE + hors UE possible | À signer | [paypal.com/privacy](https://www.paypal.com/privacy) |
| Sendcloud | Étiquettes, tracking | UE (si compte UE) | À signer | Doc Sendcloud / DPA compte |
| Google Drive | Copie fichiers commande (optionnel) | Hors UE possible, CCT Google | À signer si activé | Workspace / Drive DPA |
| SMTP (configuré) | E-mails transactionnels | Selon l’hébergeur mail | À signer | Contrat hébergeur |
| NAS Synology (auto-hébergé) | App, base, médias | France (défaut `LEGAL_HOSTING_DESCRIPTION`) | Interne (responsable) | Runbook déploiement |
