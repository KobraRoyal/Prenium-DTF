# Administration staff des comptes clients & conditions tarifaires

## Objectif

Permettre à l’Atelier / admin (portail staff) d’administrer les **comptes clients**
et de définir leurs **conditions tarifaires** sans passer par Django Admin.

## Accès

| Action | Permission |
|--------|------------|
| Liste / fiche | `customers.view_customer` |
| Éditer identité / adresses / règlement | `customers.change_customer` |
| Éditer tarifs / encours / cycle | `customers.manage_customer_pricing` |
| Prérequis portail | `accounts.access_staff_portal` + `is_staff` |

Navigation : **Comptes** (primaire) + entrée **Comptes clients** dans Outils Atelier.

## URLs

- `GET /portal/staff/customers/` — liste filtrable
- `GET /portal/staff/customers/<public_id>/` — fiche
- `POST .../account/` — mise à jour compte
- `POST .../pricing/` — conditions tarifaires

## Conditions tarifaires gérées

- Forfait préparation fichier négocié (`Customer.negotiated_file_preparation_fee_eur`)
- Prix DTF au m² (`CustomerBillingProfile.price_per_sqm_eur`)
- Cycle mensuel / bi-mensuel
- Plafond d’encours + blocage éventuel

Création automatique du `CustomerBillingProfile` si absent.

## Audit

- `customer.account_updated`
- `customer.pricing_conditions_updated`

## Fichiers

- `apps/customers/services/administration.py`
- `apps/customers/forms_staff.py`
- `apps/portal/views_staff_customers.py`
- `templates/portal/staff/customers/`
- `tests/customers/test_staff_customer_admin.py`

## Checklist

- [ ] Staff avec `view_customer` voit la liste et la fiche
- [ ] Sans permission → 403
- [ ] Mise à jour compte audité
- [ ] Mise à jour tarifs crée/maj le profil + audit
- [ ] Utilisateurs rattachés visibles (lecture)
- [ ] Nav « Comptes » visible seulement avec la permission
