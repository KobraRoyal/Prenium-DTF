# Commandes B2B — facturation différée

Documentation **technique** du comportement (champs, calculs, flux, API). Pour la **vision produit** (parcours client / opérateur, grille tarifaire, encours, laize 55 cm, écarts cible vs code), voir **[B2B_PRODUCT_AND_OPERATIONS.md](./B2B_PRODUCT_AND_OPERATIONS.md)**.

## Objectifs

- Découpler le dépôt de commande du paiement immédiat (plus de tunnel « prix + PayPal » pour ce flux).
- Permettre **plusieurs fichiers** par commande, avec **quantité** et **couleur de support** optionnelle (indicatif atelier).
- Garantir que **le prix n’est jamais défini par le frontend** : uniquement `OrderPricingService` (staff) après contrôle technique (dimensions fichier via inspection).
- Préparer le **regroupement facture** via `BillingStatement` et le **plafond d’encours** via `CustomerBillingProfile`.

## Modèle de données

### `Customer` (`customers`) — adresses & logistique

| Champ | Rôle |
|-------|------|
| `billing_address_*`, `billing_country` | Adresse de facturation |
| `shipping_address_*`, `shipping_country` | Adresse de livraison par défaut (réf. expédition / shipping) |
| `default_shipping_mode` | `pickup` (retrait atelier) \| `carrier` (expédition) \| `direct` (livraison directe client) |
| `negotiated_file_preparation_fee_eur` | Optionnel : forfait « préparation fichier » **par fichier** pour ce client ; sinon catalogue |

Voir **[CUSTOMER_PRICING_AND_LOGISTICS.md](./CUSTOMER_PRICING_AND_LOGISTICS.md)** pour la formule de prix et le rôle des services catalogue.

### `CustomerBillingProfile` (`customers`)

| Champ | Rôle |
|-------|------|
| `customer` | OneToOne vers `Customer` |
| `billing_cycle` | `monthly` \| `bi_monthly` |
| `price_per_sqm_eur` | Grille client : prix au m² DTF (optionnel ; sinon **catalogue** DTF) |
| `credit_limit_eur` | Plafond d’encours optionnel (EUR) |
| `enforce_credit_block` | Si vrai : dépassement → `credit_hold_status = blocked` sur la commande tarifée ; sinon → `warning` |

### `Order` (`orders`)

| Champ | Rôle |
|-------|------|
| `billing_mode` | `immediate` (API / ancien flux prix à la création) \| `deferred` (portail B2B actuel) |
| `pricing_status` | `pending` \| `priced` \| `failed` |
| `credit_hold_status` | `none` \| `clear` \| `warning` \| `blocked` |
| `billing_statement` | FK optionnelle vers `BillingStatement` (rattachement période de facturation) |
| `meterage_override_linear_m` | Optionnel : **saisie opérateur au niveau commande** (mètres linéaires totaux sur la laize pour toute la commande). m² total = `linéaire × (DTF_LAIZE_CM/100)` ; ce total est **réparti** sur les fichiers au tarifage. **Prioritaire** sur toute saisie par fichier et sur l’inspection. Saisie sur le panneau staff **Production**. |

Les commandes **existantes** migrées restent en `immediate` + `pricing_status = priced`.

### `OrderUpload` (`uploads`)

| Champ | Rôle |
|-------|------|
| `sort_order` | Ordre d’affichage / traitement |
| `quantity` | Nombre d’exemplaires (≥ 1) |
| `support_color_hex` | `#RRGGBB` ou vide |
| `meterage_sqm`, `unit_price_eur`, `line_total_eur` | Renseignés **après** calcul serveur |
| `meterage_override_linear_m` | Optionnel : **saisie par fichier** (m linéaire / exemplaire sur la laize) — utilisée seulement si **aucune** saisie commande (`Order.meterage_override_linear_m`) ; surface = `linéaire × laize × quantité` |
| `meterage_override_sqm` | Ancienne saisie directe en m² (rétrocompatibilité lecture / tarifs déjà saisis) |

### `BillingStatement` (`billing`)

Regroupement **futur** pour facture périodique : `customer`, `period_start`, `period_end`, `label`, `status`, `total_amount`, `currency`. Les commandes y sont liées par `Order.billing_statement`.

## Flux portail client

1. **Création** : `OrderService.create_b2b_deferred_order` → `status = draft`, `billing_mode = deferred`, montants à 0, `pricing_status = pending`. **Pas** de job production à ce stade.
2. **Uploads** : tant que `draft`, ajout de fichiers + quantité + couleur. Après `submitted`, uploads **interdits** pour les commandes différées.
3. **Soumission** : `OrderService.submit_b2b_deferred_order` → `status = submitted`, création du `ProductionJob`, audit `order.submitted_b2b`.
4. **Affichage prix** : tant que `pricing_status != priced`, l’UI indique un prix « après contrôle » ; après calcul staff, `total_amount` / lignes sont affichés.

URLs utiles :

- Checkout : `portal:client-checkout`
- Soumission : `portal:client-checkout-submit` (remplace l’ancien flux paiement sur ce tunnel)

## Flux staff (tarification)

- Action : `POST` `portal:staff-order-price` (permission `orders.change_order`).
- Service : `OrderPricingService.compute_and_persist_order_pricing`.
- Prérequis : commande `deferred`, `submitted`, au moins un upload ; **soit** une **saisie opérateur** en **mètres linéaires** au niveau **commande** (`Order.meterage_override_linear_m`), **soit** (par fichier) `OrderUpload.meterage_override_linear_m` ou inspection avec **largeur/hauteur** permettant d’estimer la surface (sinon erreur de validation).

Effets :

- Mise à jour des champs métrage/prix sur chaque `OrderUpload`.
- Régénération des `OrderLine` : une ligne **DTF par fichier** (prix au m² = **catalogue**) + une ligne **« Préparation fichier »** (N fichiers × forfait catalogue ou `Customer.negotiated_file_preparation_fee_eur`).
- Mise à jour `order.subtotal_amount` / `total_amount`, `pricing_status = priced`, `credit_hold_status` selon encours.
- Audit `order.pricing_computed`.

## Métrage (serveur)

- **Ordre de priorité** : si `Order.meterage_override_linear_m` est renseigné → m² total commande = linéaire × laize, puis **répartition égale** par fichier (m² par upload = total / nombre d’`OrderUpload`) ; sinon par upload : `meterage_override_linear_m` → m² = linéaire × laize × `quantity` ; sinon **legacy** `meterage_override_sqm` ; sinon estimation **aire en m²** à partir des pixels d’inspection, de `DTF_PRINT_DPI` (défaut **300**) et du mode d’aire, multipliée par `quantity`.
- **Laize (largeur film)** : `DTF_LAIZE_CM` (défaut **55**). Le prix catalogue est au **m²** mais l’atelier imprime sur une laize fixe : en mode **`laize_fit`** (défaut), si le plus petit côté physique du fichier dépasse la laize, la surface facturable minimale est **grand côté × laize** (bande pleine largeur × longueur), et non le simple rectangle pixel×pixel. Mode **`pixel_rectangle`** : aire historique `largeur × hauteur` sans contrainte laize (retrait possible pour cas particuliers).
- Settings : `DTF_PRINT_DPI`, `DTF_LAIZE_CM`, `DTF_METERAGE_AREA_MODE` (`laize_fit` \| `pixel_rectangle`) — voir `config/settings/base.py`.

## Encours

- Périmètre : commandes `deferred`, `priced`, sans `billing_statement`, hors `draft`.
- Comparaison : somme des totaux (hors commande courante au moment du calcul) + montant de la commande tarifée vs `credit_limit_eur` si défini.

## Paiement en ligne

- `PaymentService.initiate_payment_for_customer_order` **refuse** les commandes `billing_mode = deferred` et les montants ≤ 0 (hors flux immédiat classique).

## API REST (`orders`)

La réponse JSON des commandes inclut désormais : `billing_mode`, `pricing_status`, `credit_hold_status`. Le flux `POST` client existant continue de créer des commandes **immediate** avec lignes tarifées à la création (catalogue).

## Fichiers clés (code)

- `apps/orders/services/orders.py` — `create_b2b_deferred_order`, `submit_b2b_deferred_order`, `create_order` (immédiat)
- `apps/orders/services/pricing.py` — `OrderPricingService`
- `apps/uploads/services/uploads.py` — validation upload + verrou après soumission
- `apps/billing/services/payments.py` — garde-fous paiement
- `apps/production/services/workflow.py` — OF : lignes détaillées ou fallback « fichiers » si pas encore de lignes

## Tests

- `tests/orders/test_order_pricing_service.py` — catalogue m², forfait fichier, dérogation client
- `tests/ui/test_shop_checkout_ui.py` — checkout B2B (draft + deferred)

Commande type :

```bash
cd backend && python3 -m pytest ../tests -q
```

## Grille tarifaire : m² et frais par fichier

- **Implémenté** : prix **au m²** = **catalogue DTF** uniquement ; **forfait par fichier** = service catalogue « Préparation fichier » ou **`Customer.negotiated_file_preparation_fee_eur`**. Voir [CUSTOMER_PRICING_AND_LOGISTICS.md](./CUSTOMER_PRICING_AND_LOGISTICS.md).

## Évolutions possibles

- Rattachement automatique des commandes à une `BillingStatement` selon `billing_cycle` et dates de clôture.
- Métrage affiné (PDF, profils DPI par fichier, saisie manuelle staff).
- Report systématique des adresses client sur `Order` / `Shipment` au moment de l’expédition.

## Notifications (livré)

- Après `OrderPricingService.compute_and_persist_order_pricing`, un email transactionnel **« commande tarifée »** est planifié (`schedule_order_priced_email`) pour les commandes `billing_mode = deferred`, avec mention optionnelle du statut d’encours (`blocked` / `warning`).
