# Modèle B2B Prenium DTF — produit et exploitation

Document de référence : **vision métier**, **parcours acteurs**, **règles de facturation** et **correspondance avec le code**. Pour le détail technique des calculs et des champs, voir [B2B_DEFERRED_BILLING.md](./B2B_DEFERRED_BILLING.md).

---

## 1. Résumé

Le projet vise un **SaaS e-commerce B2B** pour impressions DTF premium : les **clients professionnels** passent des commandes **sans payer au moment du dépôt**. La **facturation** est **périodique** (mensuelle ou bi-mensuelle) et peut s’appuyer sur un **plafond d’encours** par client. L’**opérateur** en back-office saisit le **métrage** (priorité à la **commande**), puis lance la **tarification** ; les montants et le suivi (statuts, lignes, encours) sont **exclusivement côté serveur**.

L’impression est réalisée sur une **laize d’impression utile fixe** (réglage par défaut **55 cm**), ce qui cadre le passage du **métrage linéaire** à la **surface facturable en m²**.

---

## 2. Pas de paiement à la commande (flux standard)

- Le **tunnel client** pour les commandes B2B en **facturation différée** ne vise **pas** un paiement immédiat (pas de carte / PayPal au dépôt pour ce flux).
- Le **règlement** s’inscrit dans une logique **B2B** : facturation **mensuelle** ou **bi-mensuelle**, avec rattachement futur à des **périodes de facturation** (`BillingStatement` — périmètre prévu dans le modèle).
- Les garde-fous **paiement en ligne** côté application **refusent** les commandes en mode différé pour les flux qui supposent un encaissement immédiat (voir services de facturation / paiement).

*Note technique : le modèle `Order` conserve un mode `immediate` pour l’**historique** et d’éventuels flux API ; le **parcours portail B2B** cible actuellement le mode **`deferred`**.`

---

## 3. Paramètres par client (encours, adresses, logistique)

### Encours (`CustomerBillingProfile`, 1–1 avec `Customer`)

| Concept | Rôle métier | Implémentation |
|--------|-------------|----------------|
| **Cycle de facturation** | Mensuel ou bi-mensuel (rythme comptable / factures groupées). | `billing_cycle` : `monthly` \| `bi_monthly` |
| **Plafond d’encours** | Limite optionnelle (EUR) sur le cumul des commandes tarifées non facturées / non soldées. | `credit_limit_eur` (nullable) |
| **Comportement si dépassement** | Alerte seule, ou **blocage** explicite selon politique. | `enforce_credit_block` : si vrai → statut d’encours **bloqué** sur la commande tarifée ; sinon **alerte** |
| **Prix au m² DTF** | Grille optionnelle par client ; sinon catalogue. | `price_per_sqm_eur` (nullable) — prioritaire sur le prix catalogue pour le calcul |

### Facturation, livraison, forfait fichier (`Customer`)

| Concept | Rôle métier | Implémentation |
|--------|-------------|----------------|
| **Adresses** | Facturation et livraison par défaut (réf. expédition). | `billing_address_*`, `shipping_address_*`, pays ISO2 |
| **Mode d’acheminement par défaut** | Retrait atelier, expédition transporteur, ou livraison directe. | `default_shipping_mode` |
| **Forfait fichier négocié** | Dérogation commerciale au forfait catalogue (ex. 10 €). | `negotiated_file_preparation_fee_eur` (nullable) |

Le détail tarifaire (grille m² client ou catalogue, forfait fichier, laize 55 cm) est dans **[CUSTOMER_PRICING_AND_LOGISTICS.md](./CUSTOMER_PRICING_AND_LOGISTICS.md)**.

---

## 4. Frais fixes par fichier traité (grille métier)

Le calcul **inclut** une ligne **« Préparation fichier »** : **N fichiers × forfait**, le forfait étant le **prix du service catalogue** (ex. **10 €**) ou **`Customer.negotiated_file_preparation_fee_eur`** si renseigné. Voir `OrderPricingService.compute_and_persist_order_pricing`.

---

## 5. Parcours client

1. **Création** de commande en **brouillon** (`draft`), **facturation différée**, montants à zéro, **prix en attente**.
2. **Dépôt de fichiers** (quantité, couleur de support optionnelle) tant que la commande est en brouillon.
3. **Soumission** : passage en **soumis** (`submitted`), verrouillage des dépôts, création du **flux production** (ordre de fabrication selon règles métier).
4. **Aucun prix définitif côté client** avant **contrôle** et action **staff** (métrage / tarification).

Références : `OrderService.create_b2b_deferred_order`, `submit_b2b_deferred_order`, portail client (checkout).

---

## 6. Parcours opérateur (back-office)

1. **Contrôle** des fichiers (inspection / dimensions, selon processus atelier).
2. **Saisie du métrage** (panneau **Production**) :
   - **Priorité** : **métrage linéaire au niveau commande** (`Order.meterage_override_linear_m`) — une saisie pour toute la commande, surface totale = **linéaire × laize**, puis **répartition** entre fichiers au calcul (voir doc technique).
   - **Sinon** : saisie **par fichier** ou **estimation** à partir de l’inspection (pixels + DPI + mode d’aire).
3. **Calcul du prix** : action staff **« Calculer le prix »** → `OrderPricingService.compute_and_persist_order_pricing` : lignes de commande, montants, **statut prix calculé**, **encours** recalculé.
4. **Suivi** : les montants, statuts (`pricing_status`, `credit_hold_status`) et lignes **remontent** dans l’interface (fiche commande, listes, notifications transactionnelles « commande tarifée » pour le flux différé).

Si la commande était **déjà tarifée**, une **modification du métrage** peut **invalider** le tarif en cours (retour **prix en attente**, lignes effacées) pour garantir la cohérence ; l’opérateur doit **relancer le calcul**.

---

## 7. Laize 55 cm et métrage

- **Laize d’impression utile** : paramètre **`DTF_LAIZE_CM`** (défaut **55**), exprimé en centimètres dans la configuration Django.
- Le **prix** est exprimé au **m²**, mais la **consommation** est pensée comme une **bande** sur cette largeur : d’où les règles **`laize_fit`** (défaut) vs **`pixel_rectangle`** pour la surface dérivée de l’inspection (voir [B2B_DEFERRED_BILLING.md](./B2B_DEFERRED_BILLING.md)).
- **Métrage linéaire saisi** (m) × **laize (m)** = **surface (m²)** pour la part « commande » ; **répartition** par nombre de fichiers lorsque la saisie est **globale à la commande**.

---

## 8. Synthèse des statuts utiles (commande)

| Champ | Signification courte |
|-------|----------------------|
| `billing_mode` | `deferred` = B2B facturation différée ; `immediate` = autres flux. |
| `pricing_status` | `pending` = pas encore tarifé ; `priced` = tarif calculé ; `failed` = échec de calcul. |
| `credit_hold_status` | Encours : `none` / `clear` / `warning` / `blocked` (selon plafond et règles). |

---

## 9. Paiement et facturation périodique

- **Paiement à la commande** n’est **pas** le modèle nominal du portail B2B décrit ici.
- Le **regroupement** sur une **facture de période** et l’**émission** de factures clients sont portés par le domaine **billing** (`BillingStatement`, etc.) — **évolutions** de clôture de période et rattachement automatique documentés comme pistes dans [B2B_DEFERRED_BILLING.md](./B2B_DEFERRED_BILLING.md).

---

## 10. Fichiers et tests à connaître

| Sujet | Emplacement principal |
|-------|------------------------|
| Création / soumission commande B2B | `apps/orders/services/orders.py` |
| Tarification et métrage | `apps/orders/services/pricing.py` |
| Saisie métrage opérateur (commande / fichier) | `apps/uploads/services/uploads.py` |
| Profil facturation client | `apps/customers/models.py` — `CustomerBillingProfile` |
| UI staff facturation | `templates/portal/staff/panels/billing.html`, vues `portal` |
| Tests tarification | `tests/orders/test_order_pricing_service.py`, `tests/uploads/test_meterage_override.py` |

---

## 11. Glossaire rapide

| Terme | Définition |
|-------|------------|
| **Laize** | Largeur utile de film / bande d’impression (ici typiquement 55 cm). |
| **Métrage linéaire** | Longueur (m) le long de la laize ; combiné à la laize pour obtenir des **m²**. |
| **Encours** | Montant des commandes tarifées non rattachées à une facture / non soldées, comparé au **plafond** client. |
| **Grille** | Prix au m² (et à terme autres composantes, ex. par fichier) par client ou par défaut catalogue. |

---

*Document maintenu avec le code ; en cas de divergence, le dépôt et les tests font foi.*
