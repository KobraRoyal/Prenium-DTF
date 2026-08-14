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

### `CustomerVolumeDiscountTier` (`customers`)

| Champ | Rôle |
|-------|------|
| `customer` | Client propriétaire de la grille ; toutes les lectures et écritures sont scopées par ce client |
| `minimum_monthly_linear_m` | Seuil inclusif du palier en mètres linéaires équivalents |
| `discount_percent` | Taux appliqué à tout le montant DTF éligible du mois lorsque le seuil est atteint |
| `is_active` | Permet de neutraliser un palier sans perdre son historique d’audit |

Les seuils sont uniques par client. Parmi les paliers actifs, la remise doit augmenter strictement
avec le seuil. La configuration Atelier est réservée aux clients en mode compte `deferred` et à la
permission `customers.manage_customer_pricing`.

### `DefaultCustomerVolumeDiscountTier` (`customers`)

Cette grille globale est administrée dans **Atelier → Outils → Remises par défaut** avec la même
permission tarifaire. Lors de l’approbation d’un prospect, chaque palier actif est copié dans une
grille `CustomerVolumeDiscountTier` propre au nouveau client en encours. Il n’existe aucun taux
financier codé en dur : une grille globale vide ne crée aucune remise. Les modifications futures
de la grille globale ne modifient pas les conditions déjà copiées chez les clients existants.

### `Order` (`orders`)

| Champ | Rôle |
|-------|------|
| `billing_mode` | `immediate` (paiement comptant CB après tarification atelier, choisi à la commande) \| `deferred` (encours / facturation différée, choisi à la commande) |
| `Customer.default_billing_mode` | Mode compte : **comptant CB** verrouille la transmission (pas d’option encours) ; **encours** laisse encore choisir le comptant CB commande par commande |
| `pricing_status` | `pending` \| `priced` \| `failed` |
| `credit_hold_status` | `none` \| `clear` \| `warning` \| `blocked` |
| `billing_statement` | FK optionnelle vers `BillingStatement` (rattachement période de facturation) |
| `meterage_override_linear_m` | Optionnel : **saisie opérateur au niveau commande** (mètres linéaires totaux sur la laize pour toute la commande). m² total = `linéaire × (DTF_LAIZE_CM/100)` ; ce total est **réparti** sur les fichiers au tarifage. **Prioritaire** sur toute saisie par fichier et sur l’inspection. Saisie sur le panneau staff **Production**. |
| `volume_discount_month`, `monthly_volume_linear_m` | Mois civil et volume éligible figés au dernier recalcul |
| `volume_discount_threshold_linear_m`, `volume_discount_percent` | Palier atteint et taux appliqué |
| `volume_discount_amount` | Montant HT retiré des lignes DTF de la commande |
| `volume_discount_base_unit_price_eur` | Prix DTF brut au m² conservé pour les recalculs rétroactifs |

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
- Pour une commande en encours, recalcul de toutes les commandes éligibles du même mois avec le
  meilleur palier atteint sur le volume général.
- Audit `order.pricing_computed`.

## Remise générale sur volume mensuel

Le périmètre d’agrégation contient uniquement les commandes du même client qui sont `submitted`,
`deferred`, `priced`, sans `billing_statement` et créées dans le même mois civil. Les commandes
comptant, annulées, en attente de prix ou déjà relevées ne contribuent pas au volume.

```text
volume_mensuel_m = somme(lignes_DTF.quantity_m²) / (DTF_LAIZE_CM / 100)
palier = plus grand seuil actif tel que seuil <= volume_mensuel_m
DTF_remisé_commande = DTF_brut_commande × (1 - remise_palier / 100)
```

Le taux du palier s’applique au DTF de **toutes** les commandes éligibles du mois. La préparation
fichier et le port restent inchangés. Une commande déjà rattachée à un relevé est gelée et exclue.
La modification d’un palier recalcule immédiatement le mois civil courant ; la tarification,
l’invalidation du métrage et l’annulation Atelier recalculent le mois concerné.

Le service verrouille la ligne `Customer` avant l’agrégation afin que deux commandes concurrentes
ne puissent pas conserver des paliers divergents. Les événements
`order.monthly_volume_discount_repriced` et `customer.monthly_volume_discount_applied` assurent la
traçabilité du résultat.

Lorsqu’un meilleur palier est atteint pendant le mois civil courant, une
`VolumeDiscountTierNotification` est créée avec les snapshots du seuil, du volume, du taux et de
la remise cumulée. Sa contrainte `(customer, month, threshold_linear_m)` empêche un nouvel envoi si
une modification ou un recalcul fait repasser le client par le même seuil. En cas de saut de
plusieurs seuils, seul le meilleur palier atteint est notifié afin d’éviter plusieurs e-mails pour
une même commande.

L’e-mail `volume_discount_tier_reached` est envoyé après commit par Celery aux contacts du client,
avec un message distinct par destinataire afin de ne jamais exposer les autres adresses dans `To`.
Une prise en charge `PENDING → SENDING` est persistée avant l’appel SMTP : une panne ambiguë après
acceptation ne provoque donc pas de doublon automatique et reste visible pour réconciliation dans
l’administration (`SENDING` ou `FAILED`, compteur et heure de tentative). Son objet/message sont
modifiables dans **Atelier → Modèles d’e-mails**. Le dashboard client affiche uniquement la synthèse
du client scopé : volume actuel, palier actif et distance jusqu’au prochain seuil.

## Récapitulatif mensuel pour facturation externe

La fiche client Atelier permet de générer manuellement un `BillingStatement` pour un mois civil
terminé. Le service sélectionne uniquement les commandes du client qui sont `submitted`,
`deferred`, `priced` et encore sans relevé. La génération :

1. verrouille le `Customer` puis les commandes candidates, dans le même ordre que la tarification ;
2. refuse une période courante/future, une période déjà clôturée, un mois vide ou plusieurs devises ;
3. vérifie que les lignes correspondent au sous-total et que `sous-total + port = total HT` ;
4. calcule le total depuis les montants `Order.total_amount`, qui valent HT + port pour l’encours ;
5. émet directement le relevé, conserve l’identité et les lignes dans un snapshot immuable,
   puis enregistre l’empreinte SHA-256 du CSV canonique ;
6. rattache les commandes au relevé et audite `billing.statement_generated`.

Le rattachement fige les montants : retarification, invalidation du métrage et suppression Atelier
sont ensuite refusées. La suppression du relevé est protégée tant que des commandes y sont liées.
L’export CSV détaillé est toujours reconstruit depuis le snapshot figé : les modifications ultérieures
du client ou des commandes ne changent donc pas l’historique. Il contient l’identité de facturation,
une ligne par commande et une ligne totale (DTF brut/net, remise volume, services, port et total HT
à facturer). La TVA et le TTC restent calculés par l’outil comptable externe. Le CSV est
servi en UTF-8 BOM, séparé par `;`, protège les cellules texte contre les formules tableur et trace
`billing.statement_exported`.

Les migrations ne reconstruisent jamais un snapshot historique à partir de données potentiellement
modifiées. Un préflight bloque le déploiement si d’anciens relevés existent : ils doivent être
exportés et réconciliés manuellement avant la migration.

Permissions : `customers.view_customer` + `billing.view_billingstatement` pour consulter/exporter,
avec `billing.add_billingstatement` supplémentaire pour générer. Le relevé est toujours récupéré
dans le scope du `customer_public_id` de l’URL.

Routes :

- `POST portal:staff-customer-billing-statement-create`
- `GET portal:staff-customer-billing-statement-export`

## Métrage (serveur)

- **Ordre de priorité** : si `Order.meterage_override_linear_m` est renseigné → m² total commande = linéaire × laize, puis **répartition égale** par fichier (m² par upload = total / nombre d’`OrderUpload`) ; sinon par upload : `meterage_override_linear_m` → m² = linéaire × laize × `quantity` ; sinon **legacy** `meterage_override_sqm` ; sinon estimation **aire en m²** à partir des pixels d’inspection, de `DTF_PRINT_DPI` (défaut **300**) et du mode d’aire, multipliée par `quantity`.
- **Laize (largeur film)** : `DTF_LAIZE_CM` (défaut **55**). Le prix catalogue est au **m²** mais l’atelier imprime sur une laize fixe : en mode **`laize_fit`** (défaut), si le plus petit côté physique du fichier dépasse la laize, la surface facturable minimale est **grand côté × laize** (bande pleine largeur × longueur), et non le simple rectangle pixel×pixel. Mode **`pixel_rectangle`** : aire historique `largeur × hauteur` sans contrainte laize (retrait possible pour cas particuliers).
- Settings : `DTF_PRINT_DPI`, `DTF_LAIZE_CM`, `DTF_METERAGE_AREA_MODE` (`laize_fit` \| `pixel_rectangle`) — voir `config/settings/base.py`.

## Encours

- Périmètre : commandes `deferred`, `priced`, sans `billing_statement`, hors `draft`.
- Comparaison : somme des totaux (hors commande courante au moment du calcul) + montant de la commande tarifée vs `credit_limit_eur` si défini.

## Paiement en ligne

- `PaymentService.initiate_payment_for_customer_order` **refuse** les commandes `billing_mode = deferred` et les montants ≤ 0.
- Pour le paiement immédiat (`billing_mode = immediate`) : **PayPal** et **Stripe Checkout** via abstraction `PaymentGateway`.
- Doc dédiée : [ONLINE_PAYMENTS.md](./ONLINE_PAYMENTS.md).
- La facturation périodique (`BillingStatement`) reste hors paiement en ligne.

## API REST (`orders`)

La réponse JSON des commandes inclut désormais : `billing_mode`, `pricing_status`, `credit_hold_status`. Le flux `POST` client existant continue de créer des commandes **immediate** avec lignes tarifées à la création (catalogue).

## Fichiers clés (code)

- `apps/orders/services/orders.py` — `create_b2b_deferred_order`, `submit_b2b_deferred_order`, `create_order` (immédiat)
- `apps/orders/services/pricing.py` — `OrderPricingService`
- `apps/uploads/services/uploads.py` — validation upload + verrou après soumission
- `apps/billing/services/payments.py` — garde-fous paiement
- `apps/billing/services/statements.py` — clôture mensuelle et export comptable CSV
- `apps/portal/views_staff_billing_statements.py` — permissions et endpoints Atelier du relevé
- `apps/production/services/workflow.py` — OF : lignes détaillées ou fallback « fichiers » si pas encore de lignes

## Tests

- `tests/orders/test_order_pricing_service.py` — catalogue m², forfait fichier, dérogation client
- `tests/orders/test_monthly_volume_discounts.py` — paliers, rétroactivité, mois, relevés et isolation
- `tests/customers/test_volume_discount_tiers.py` — permission Atelier, scope client et invariants
- `tests/notifications/test_volume_discount_tier_notifications.py` — envoi, idempotence et modèle
  d’e-mail Atelier
- `tests/billing/test_billing_statements.py` — clôture, export, permissions, isolation et gel
- `tests/ui/test_shop_checkout_ui.py` — checkout B2B (draft + deferred)

Commande type :

```bash
cd backend && python3 -m pytest ../tests -q
```

## Grille tarifaire : m² et frais par fichier

- **Implémenté** : prix **au m²** = **catalogue DTF** uniquement ; **forfait par fichier** = service catalogue « Préparation fichier » ou **`Customer.negotiated_file_preparation_fee_eur`**. Voir [CUSTOMER_PRICING_AND_LOGISTICS.md](./CUSTOMER_PRICING_AND_LOGISTICS.md).

## Évolutions possibles

- Automatisation optionnelle de la clôture selon `billing_cycle`, en conservant une validation
  opérateur avant génération définitive.
- Métrage affiné (PDF, profils DPI par fichier, saisie manuelle staff).
- Report systématique des adresses client sur `Order` / `Shipment` au moment de l’expédition.

## Flux production vs paiement (comptant CB)

1. Transmission → OF créé (`queued`) pour contrôle fichiers / métrage.
2. Atelier contrôle + calcule le tarif → email `order_awaiting_payment`.
3. **Production (`in_progress`) refusée** tant qu’aucun `Payment` `captured`.
4. Capture Stripe/PayPal → audit `production.unlocked_after_payment` ; lancement autorisé.

L’encours (`deferred`) n’est pas soumis à cette gate.

## Notifications (livré)

- Après `OrderPricingService.compute_and_persist_order_pricing` :
  - **encours** (`billing_mode = deferred`) → email **« commande tarifée »** (`schedule_order_priced_email`), avec mention optionnelle du statut d’encours (`blocked` / `warning`) ;
  - **comptant CB** (`billing_mode = immediate`) → email **« paiement carte à effectuer »** (`schedule_order_awaiting_payment_email`), avec lien vers le panneau Facture client (CTA Stripe après tarification).
- Éditable dans Atelier → Modèles d’e-mails (`order_priced` / `order_awaiting_payment`).
- Au premier passage sur un nouveau seuil du mois courant : e-mail client
  `volume_discount_tier_reached`, idempotent par client/mois/seuil et éditable dans le même
  catalogue Atelier.
