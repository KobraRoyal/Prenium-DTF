# Sprint 38 — Récapitulatif de facturation externalisée

## Objectif

Permettre à l’Atelier de clôturer un mois par client en encours et d’exporter un
récapitulatif fiable pour l’édition de la facture dans un outil comptable externe.

## Contrat métier

- Un récapitulatif couvre un mois civil terminé et un seul `Customer`.
- Sont incluses uniquement les commandes `submitted`, `deferred`, `priced`, non
  annulées et sans `billing_statement`.
- Toutes les commandes incluses utilisent la même devise.
- Un seul `BillingStatement` peut exister pour un client et un mois.
- La génération verrouille le client avant les commandes, comme la tarification,
  puis émet directement un relevé figé (`issued`).
- La clôture refuse une commande dont le sous-total ne correspond pas à la somme
  des lignes, ou dont le total HT ne correspond pas au sous-total + livraison.
- L’identité de facturation, les lignes et les totaux sont conservés dans un snapshot
  immuable. Une empreinte SHA-256 du CSV canonique permet de détecter toute altération.
- Une commande relevée ne peut plus être retarifée, invalidée par changement de
  métrage ou supprimée de la file Atelier. Le relevé lui-même est protégé contre la
  suppression tant qu’il porte des commandes.
- La génération et chaque export CSV sont audités.

## Export comptable

Le CSV est encodé en UTF-8 avec BOM, utilise `;` comme séparateur et la virgule
comme séparateur décimal. Il contient une ligne par commande puis une ligne totale :

- identité et adresse de facturation du client ;
- période et référence opaque du relevé ;
- référence et date de commande ;
- surface DTF, équivalent mètres linéaires et DTF brut HT ;
- taux/montant de remise volume, DTF net et autres services ;
- sous-total HT, livraison HT, total à facturer HT et devise.

IDS Hub ne calcule pas la TVA sur les commandes en encours : le taux, la TVA et le
TTC sont déterminés dans l’outil comptable externe au moment d’éditer la facture.

La migration refuse explicitement tout ancien `BillingStatement` dépourvu de snapshot.
Ces relevés doivent être exportés, rapprochés puis supprimés manuellement avant le
déploiement, afin de ne jamais fabriquer rétroactivement un historique comptable.

Les cellules textuelles sont protégées contre l’interprétation de formules lors de
l’ouverture dans un tableur.

## Permissions et isolation

- Lecture/export : `customers.view_customer` + `billing.view_billingstatement`.
- Génération : permissions précédentes + `billing.add_billingstatement`.
- Les routes utilisent les UUID publics du client et du relevé.
- L’export recherche le relevé dans le scope du client de l’URL ; un croisement de
  deux clients renvoie `404`.

## Fichiers principaux

- `backend/apps/billing/services/statements.py`
- `backend/apps/billing/forms.py`
- `backend/apps/billing/models.py`
- `backend/apps/portal/views_staff_billing_statements.py`
- `backend/templates/portal/staff/customers/_billing_statements.html`
- `tests/billing/test_billing_statements.py`

## Checklist

- [x] Service transactionnel de clôture mensuelle
- [x] Contrainte DB période valide et unique par client
- [x] Préflight des périodes et des relevés historiques avant ajout des contraintes/snapshots
- [x] Export CSV détaillé et sécurisé
- [x] Snapshot comptable figé et empreinte SHA-256
- [x] Permissions serveur et test d’accès croisé
- [x] Audit génération/export
- [x] Gel post-récapitulatif
- [x] Sérialisation tarification/clôture et test PostgreSQL concurrent
- [x] UI Atelier intégrée à la fiche client
- [x] Tests métier et régressions ciblées
- [x] Recette navigateur desktop/mobile (1440 px et 390 px, sans débordement)
- [x] Première revue sécurité et domaine indépendantes
- [x] Contre-revue sécurité et domaine après corrections — aucun blocage restant

## Validation ciblée

```bash
cd backend
pytest -q \
  ../tests/billing/test_billing_statements.py \
  ../tests/customers/test_staff_customer_admin.py \
  ../tests/orders/test_staff_order_delete.py \
  ../tests/orders/test_monthly_volume_discounts.py
```
