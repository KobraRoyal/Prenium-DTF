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

Navigation : **Comptes** dans la nav primaire Atelier uniquement (pas de doublon dans Outils).
Liste responsive : table desktop, cartes cliquables sous 1024px.

## URLs

- `GET /portal/staff/customers/` — liste filtrable
- `GET /portal/staff/customers/<public_id>/` — fiche
- `POST .../account/` — mise à jour compte
- `POST .../pricing/` — conditions tarifaires
- `POST .../volume-discounts/` — création et modification des paliers propres au client
- `POST .../billing-statements/` — clôture mensuelle pour export comptable

## Organisation UX de la fiche

Depuis août 2026, la fiche staff est organisée comme un espace de travail à cinq
destinations : **Compte**, **Tarification**, **Remises volume**, **Facturation** et
**Accès portail**.

- l’en-tête reprend le `page_head` Atelier (fil d’Ariane, titre raison sociale, sous-titre) ;
- la navigation locale reste visible sur desktop et devient horizontale sur mobile ;
- chaque destination repose sur un élément natif `<details>` : le contenu reste
  accessible sans JavaScript et utilisable au clavier ;
- **Compte** est ouvert par défaut ; les adresses et notes internes utilisent un
  second niveau de divulgation pour réduire la longueur initiale du formulaire ;
- les sous-sections regroupent titre, aide et chevron sur une seule ligne stable ;
  les choix de règlement se présentent en paire sur écran large et les localités
  utilisent une grille `code postal / ville`, puis le pays en pleine largeur ;
- un lien direct avec fragment (`#billing-statements`, par exemple) ouvre la bonne
  destination et la fait défiler dans la zone visible ;
- une destination contenant des erreurs de formulaire est rendue ouverte côté
  serveur, y compris pour les adresses, notes et paliers de remise ;
- les listes (paliers, récapitulatifs, accès) suivent le contrat commandes :
  table `ui-data-table` ≥ 960 px, cartes `ui-mobile-order-card` en dessous ;
- création / configuration des paliers et génération d’un récapitulatif passent
  par une `<dialog>` native, rouverte automatiquement en cas d’erreur de formulaire.

## Conditions tarifaires gérées

- Forfait préparation fichier négocié (`Customer.negotiated_file_preparation_fee_eur`)
- Prix DTF au m² (`CustomerBillingProfile.price_per_sqm_eur`)
- Cycle mensuel / bi-mensuel
- Plafond d’encours + blocage éventuel

Création automatique du `CustomerBillingProfile` si absent.

## Audit

- `customer.account_updated`
- `customer.company_profile.updated` (édition client par propriétaire / administrateur du compte)
- `customer.pricing_conditions_updated`

## Fichiers

- `apps/customers/services/administration.py`
- `apps/customers/forms_staff.py`
- `apps/portal/views_staff_customers.py`
- `templates/portal/staff/customers/`
- `static_src/css/components/customer-account-workspace.css`
- `static_src/js/customer-account-workspace.js`
- `tests/customers/test_staff_customer_admin.py`

## Checklist

- [ ] Staff avec `view_customer` voit la liste et la fiche
- [ ] Sans permission → 403
- [ ] Mise à jour compte audité
- [ ] Mise à jour tarifs crée/maj le profil + audit
- [ ] Utilisateurs rattachés visibles (lecture)
- [ ] Nav « Comptes » visible seulement avec la permission

### Validation UI de l’espace de travail

- [x] Une destination principale est visible sans parcourir toutes les autres sections
- [x] Les cinq liens locaux ouvrent la bonne section et mettent à jour le fragment URL
- [x] Les erreurs de formulaire rouvrent automatiquement la section concernée
- [x] Aucun débordement horizontal de page à 390 px
- [x] Les sections utilisent des contrôles natifs accessibles au clavier
- [x] Les sous-sections Compte restent alignées avec libellés courts ou longs
- [x] Les champs d’adresses restent alignés sans colonnes desktop trop étroites
- [x] Recette navigateur desktop et mobile effectuée
- [x] Tests de cohérence UI et tests clients/facturation ciblés au vert
