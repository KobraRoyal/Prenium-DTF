# Sprint 16 — PDF métiers (facture + ordre de fabrication)

## Objectif
Produire des PDF téléchargeables pour la facturation et l’atelier, générés côté serveur et médiatisés par permissions.

## Périmètre
- Facture PDF post-paiement (**ReportLab** — remplace le fichier texte à l’émission).
- OF PDF : contenu aligné sur `ProductionWorkflowService.build_manufacturing_order` (scan, récap, lignes, fichiers).
- Téléchargement : client facture (route existante) ; staff OF (`/api/staff/production/orders/<uuid>/manufacturing-order.pdf`).
- Aucun lien public non signé ; permissions inchangées.

## Hors périmètre
- Mise en page graphique « marketing ».
- Archivage légal long terme hors app.

## Définition de done
- [x] Génération testée (magic bytes `%PDF`, `application/pdf`).
- [x] Pas de chemin fichier brut exposé en JSON (payload OF inchangé côté API).
