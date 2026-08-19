# Client (`Customer`) — tarification B2B et logistique par défaut

## Tarification différée (règle métier)

Grille de référence (ajustable dans le **catalogue** `CatalogService`, pas par une grille au m² par client) :

1. **Impression DTF** : prix **au m²** = **`CustomerBillingProfile.price_per_sqm_eur`** si renseigné pour le client, sinon prix du service catalogue **« DTF au mètre »**.  
   - Surface facturable en m² : dérivée du métrage (inspection, saisie opérateur, etc.).  
   - Avec une laize fixe (ex. **55 cm**), un mètre linéaire sur la laize correspond à **0,55 m²** ; le moteur calcule des m² puis applique **m² × prix au m² résolu**.

2. **Préparation / traitement fichier** : **forfait par fichier** traité dans la commande.  
   - **Par défaut** : prix du service catalogue **« Préparation fichier »** (forfait), typiquement **10 €** par fichier.  
   - **Dérogation client** : champ **`Customer.negotiated_file_preparation_fee_eur`** — si renseigné, il remplace le forfait catalogue pour ce client (EUR par fichier).

3. **Livraison** : option choisie par le client (`ShippingMethod` : retrait / standard / express).  
   - Snapshot figé sur `Order` (`shipping_method_code`, `shipping_method_name`, `shipping_amount`).  
   - Retrait atelier (`is_pickup`) → **0 €**.  
   - Seed V1 : standard **8 € HT**, express **18 € HT**.

4. **TVA** : **20 %** (`ORDER_VAT_RATE_IMMEDIATE`) uniquement si `billing_mode=immediate` (comptant CB), sur **sous-total HT + port**.  
   - Encours (`deferred`) : **`total_amount` = HT produit + frais de port** (pas de TVA dans le Hub). La TVA et la facture mensuelle / bimensuelle sont gérées **hors outil** (logiciel de facturation externe).

5. **Remise volume mensuelle client**
   - Encours (`deferred`) : paliers rétroactifs. Volume = commandes `submitted` + `priced` +
     non relevées du mois. Le meilleur palier s’applique à **toutes** ces commandes.
   - Comptant (`immediate`, compte en mode comptant) : paliers **prospectifs**. Volume historique =
     commandes **payées** (`Payment` capturé) du mois. Le palier de la commande en cours =
     volume payé + linéaire de cette commande. Aucun retarif des commandes déjà payées.
   - Les paliers `CustomerVolumeDiscountTier` sont configurés dans la fiche client Atelier
     (encours et comptant). Si un compte comptant n’a aucune grille personnalisée, la grille
     Atelier `DefaultCustomerVolumeDiscountTier` s’applique à la volée. L’encours **ne** retombe
     **pas** sur cette grille live (copie à la création seulement).
   - Le volume équivalent linéaire du mois est la somme des quantités DTF en m² divisée par la
     laize en mètres.
   - Préparation, port et commandes déjà rattachées à un relevé sont exclus.
   - Le client voit sa progression sur son dashboard (titre factuel + message
     commercial). Les messages se personnalisent dans **Atelier → Remises par
     défaut**, sans HTML : placeholders `{remaining_m}`, `{next_percent}`,
     `{current_percent}`, `{volume_m}`, `{threshold_m}`. Champ vide = texte Prenium.
     Il reçoit un e-mail une fois par nouveau seuil atteint dans le mois
     (encours : au retarif ; comptant : après capture). Voir sprint 41.

### Catalogue — résolution anti-régression

- **Préparation fichier** : `Customer.negotiated_file_preparation_fee_eur` si renseigné, sinon service préféré `CATALOG_PREFERRED_FILE_PREP_CODES` (défaut `seed-file-prep`), puis éventuel `seed-*`, puis premier actif.
- **DTF au m²** : `CustomerBillingProfile.price_per_sqm_eur` si renseigné, sinon `CATALOG_PREFERRED_DTF_CODES` (vide par défaut) puis premier actif par `display_order` / `name`.

### Livraison — UX

- Fiche client en **retrait atelier** (`default_shipping_mode=pickup` ou méthode `is_pickup`) : **pas de choix** à la commande, forcé `pickup` / 0 €.
- **Hors retrait** : sélecteur à options comparables (nom, prix HT, délai), même contrat HTMX de recalcul du devis.

### Formule (`OrderPricingService`)

```
subtotal_amount  = DTF + préparation          # HT produit
shipping_amount  = option livraison           # HT port (0 si retrait / legacy sans code)
tax_amount       = (subtotal + shipping) × 20 % si immediate, sinon 0
total_amount     = subtotal + shipping + tax  # Stripe TTC (comptant) ou HT+port (encours)
```

Pour l’encours avec palier :

```text
DTF_net          = DTF_brut × (1 - remise_palier / 100)
subtotal_amount  = DTF_net + préparation
```

Pour le comptant avec palier (même formule, appliquée **uniquement** à la commande en cours) :

```text
volume_devis     = volume_payé_du_mois + linéaire_commande
DTF_net          = DTF_brut × (1 - remise_palier(volume_devis) / 100)
```

### Implémentation (`OrderPricingService.compute_and_persist_order_pricing`)

- Une **ligne de commande par fichier** pour le DTF (quantité = m², prix unitaire = prix catalogue au m²).
- En encours, ces lignes sont recalculées avec le taux mensuel et le prix brut est conservé dans
  `Order.volume_discount_base_unit_price_eur`.
- En comptant (compte `immediate`), le palier prospectif est appliqué à cette commande seulement,
  puis figé après paiement capturé. `estimate_gang_sheet_quote` expose le TTC déjà remisé.
- Une **ligne supplémentaire** « Préparation fichier » : quantité = nombre de fichiers, prix unitaire = forfait résolu (catalogue ou négocié client), total = N × forfait.
- Port + TVA **hors** `OrderLine` (champs Order dédiés) pour ne pas mélanger produit et logistique.
- Même formule dans `estimate_gang_sheet_quote` (devis pré-paiement).

## Adresses et expédition par défaut

Sur le modèle **`Customer`** :

| Champ | Usage |
|--------|--------|
| `billing_address_*`, `billing_country` | Adresse de **facturation** (référence comptable). |
| `shipping_address_*`, `shipping_country` | Adresse de **livraison** par défaut — référence pour **expédition / étiquette**. |
| `default_shipping_mode` | Intention logistique historique : retrait / transporteur / directe. |
| `default_shipping_method` | Option commerciale préférée (FK `ShippingMethod`) ; sinon dérivée de `default_shipping_mode`. |

Les pays sont stockés en **ISO 3166-1 alpha-2** (ex. `FR`).

## Administration Django

`CustomerAdmin` / `ShippingMethodAdmin` : facturation, livraison, options de port et forfait fichier négocié.

## Catalogue minimal requis

Pour calculer un prix B2B différé, le catalogue doit exposer au moins :

- un service **DTF** (`service_type=dtf_transfer`, `unit=linear_meter`) actif ;
- un service **Préparation fichier** (`service_type=file_preparation`, `unit=fixed`) actif ;
- des **`ShippingMethod`** actives (seed migration : pickup / standard / express).

Voir la commande `seed_sprint09_recipe` pour des exemples (25 €/m² DTF, 10 € préparation fichier).
