# Client (`Customer`) — tarification B2B et logistique par défaut

## Tarification différée (règle métier)

Grille de référence (ajustable dans le **catalogue** `CatalogService`, pas par une grille au m² par client) :

1. **Impression DTF** : prix **au m²** = **`CustomerBillingProfile.price_per_sqm_eur`** si renseigné pour le client, sinon prix du service catalogue **« DTF au mètre »**.  
   - Surface facturable en m² : dérivée du métrage (inspection, saisie opérateur, etc.).  
   - Avec une laize fixe (ex. **55 cm**), un mètre linéaire sur la laize correspond à **0,55 m²** ; le moteur calcule des m² puis applique **m² × prix au m² résolu**.

2. **Préparation / traitement fichier** : **forfait par fichier** traité dans la commande.  
   - **Par défaut** : prix du service catalogue **« Préparation fichier »** (forfait), typiquement **10 €** par fichier.  
   - **Dérogation client** : champ **`Customer.negotiated_file_preparation_fee_eur`** — si renseigné, il remplace le forfait catalogue pour ce client (EUR par fichier).

### Implémentation (`OrderPricingService.compute_and_persist_order_pricing`)

- Une **ligne de commande par fichier** pour le DTF (quantité = m², prix unitaire = prix catalogue au m²).
- Une **ligne supplémentaire** « Préparation fichier » : quantité = nombre de fichiers, prix unitaire = forfait résolu (catalogue ou négocié client), total = N × forfait.

## Adresses et expédition par défaut

Sur le modèle **`Customer`** :

| Champ | Usage |
|--------|--------|
| `billing_address_*`, `billing_country` | Adresse de **facturation** (référence comptable). |
| `shipping_address_*`, `shipping_country` | Adresse de **livraison** par défaut — référence pour **expédition / étiquette** ; peut être reprise ou surchargée au niveau commande plus tard. |
| `default_shipping_mode` | **Retrait atelier** \| **Expédition (transporteur)** \| **Livraison directe au client** — intention logistique par défaut pour le compte. |

Les pays sont stockés en **ISO 3166-1 alpha-2** (ex. `FR`).

## Administration Django

`CustomerAdmin` regroupe facturation, livraison, mode d’acheminement et forfait fichier négocié.

## Catalogue minimal requis

Pour calculer un prix B2B différé, le catalogue doit exposer au moins :

- un service **DTF** (`service_type=dtf_transfer`, `unit=linear_meter`) actif ;
- un service **Préparation fichier** (`service_type=file_preparation`, `unit=fixed`) actif.

Voir la commande `seed_sprint09_recipe` pour des exemples (25 €/m² DTF, 10 € préparation fichier).
