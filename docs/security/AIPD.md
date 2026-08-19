# Analyse d’impact relative à la protection des données (AIPD) — Prenium DTF

Document de travail **Art. 35**. Ce n’est **pas un avis juridique**. À faire relire par un DPO / conseil avant ouverture publique large.

Dernière mise à jour : 18 août 2026. Périmètre : portail B2B Prenium DTF / IDS Hub (comptes, commandes, fichiers, paiements, expédition, audit).

## 1. Nécessité

Une AIPD est pertinente ici parce que le traitement combine :

- fichiers de production pouvant contenir des données de tiers (visuels clients) ;
- données d’identification et de connexion ;
- paiements en ligne ;
- transfert possible hors UE (Stripe, PayPal, Google Drive optionnel) ;
- journaux d’adresses IP.

Le responsable de traitement est `LEGAL_CONTROLLER_NAME` (IDS Supply par défaut). Contact : `LEGAL_PRIVACY_EMAIL`.

## 2. Traitements à risque

| Traitement | Risque principal | Mesures déjà en place |
|---|---|---|
| Fichiers de commande | Accès croisé entre organisations, fuite de visuels | Isolation `Customer`, `public_id`, téléchargement médié, tests d’accès croisé |
| Google Drive (optionnel) | Transfert hors UE, copie hors du NAS | Désactivable ; CCT Google mentionnées dans la politique si activé ; sync auditée |
| Paiements Stripe / PayPal | Fuite d’identifiants prestataire, conservation inutile | JSON prestataire minimisé, rétention 90 j, pas de PAN en base |
| Expédition Sendcloud | Adresse destinataire chez le prestataire | Snapshot interne rédigé ; l’API étiquette conserve l’adresse réelle (nécessaire à la livraison) |
| Audit / IP | Traçage excessif | IP purgée (365 j par défaut), rate-limit login / reset / changement d’e-mail |
| Comptes | Usurpation, clôture abusive | Hash mot de passe, reset signé, rectification d’e-mail confirmée, clôture refusée pour l’atelier |

## 3. Droits des personnes

- Information : pages légales publiques.
- Accès / portabilité : export JSON scopé au compte.
- Rectification : identité (nom) immédiate ; e-mail après confirmation sur la nouvelle adresse.
- Effacement : clôture / anonymisation (pièces comptables conservées 10 ans).
- Opposition marketing : pas de prospection depuis le portail.

## 4. Risques résiduels (acceptés à ce stade)

- MFA staff non déployé (flags en base uniquement) — à réévaluer avant exposition large.
- DPA prestataires à signer (Stripe, PayPal, Sendcloud, SMTP, Google si activé).
- Drive hors UE si l’option est allumée.
- Pas de CMP cookies : aucun tracker tiers aujourd’hui ; à revoir si un outil d’audience est ajouté.

## 5. Décision

Le risque résiduel est **maîtrisé pour un usage B2B restreint** (atelier + clients connus), sous réserve de renseigner `LEGAL_*`, de signer les DPA et de relire les pages légales.

Une nouvelle AIPD est due si : ouverture grand public, activation Drive en production, ajout de tracking, ou sous-traitant supplémentaire.
