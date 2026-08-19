# Sprint 41 — Remise volume mensuelle pour le paiement comptant (prospective)

## Objectif

Étendre les paliers de remise volume DTF aux comptes **paiement comptant CB**, sans
rétroactivité, et **sans régression** du moteur encours (sprint 37).

Le client comptant voit le **nouveau tarif dès qu’un palier est atteint** (devis Gang
Sheet / checkout). Les commandes déjà **payées** conservent le taux snapshoté.

## Décisions validées

| # | Décision | Règle |
|---|---|---|
| 1 | Commande franchissante | La commande qui fait passer le volume au-dessus du seuil **bénéficie déjà** du nouveau taux. |
| 2 | Grille | Réutiliser `DefaultCustomerVolumeDiscountTier`. Si le client n’a **aucune** grille personnalisée (`CustomerVolumeDiscountTier` vide), appliquer la grille **par défaut Atelier** à la volée. Dès qu’une grille client existe, elle prime (copie indépendante, comme l’encours). |
| 3 | Volume historique | Uniquement les commandes **payées** (`Payment.status = captured`). Les devis et commandes en attente Stripe ne comptent pas. |
| 4 | Affichage | Le devis (Gang Sheet / réassort) et le panneau facture affichent le taux et le TTC remisés **dès le franchissement**, avant paiement. |
| 5 | Mix encours + comptant | **Hors scope.** Un compte encours n’a pas de paiement comptant dans ce lot. Le moteur cash ne s’exécute que si `Customer.default_billing_mode = immediate` **et** `Order.billing_mode = immediate`. `reprice_deferred_month` reste strictement encours. |
| 6 | E-mail palier | Oui, même événement `volume_discount_tier_reached`, déclenché **après capture** (pas au devis), copy sans rétroactivité. |

## Contrat anti-régression (non négociable)

- Ne pas appeler `reprice_deferred_month` sur une commande `immediate`.
- Ne pas modifier le périmètre ni le calcul encours : `submitted` + `deferred` + `priced` + sans relevé + mois civil.
- Ne pas faire retomber un compte encours **sans paliers client** sur la grille par défaut (le fallback live est **réservé au comptant**). Sinon, une mise à jour Atelier de la grille globale changerait des prix encours aujourd’hui à 0 %.
- Préparation fichier, port et TVA : hors assiette de remise (inchangé).
- Stripe : le montant de session = `Order.total_amount` **déjà remisé** au persist. Aucun retarif après `CAPTURED`.
- Isolation : lectures/écritures paliers toujours scopées `for_customer` + `public_id`. Permission `customers.manage_customer_pricing` inchangée.
- Les tests `tests/orders/test_monthly_volume_discounts.py` restent verts **sans changement de assertions financières encours**.

## Règle de calcul comptant

```text
volume_paye_m     = somme(DTF m² des commandes immediate + submitted + priced
                          du mois civil, avec Payment CAPTURED) / laize_m
volume_devis_m    = volume_paye_m + linéaire_de_la_commande_en_cours
palier            = plus grand seuil actif tel que seuil <= volume_devis_m
DTF_net           = DTF_brut × (1 - remise_palier / 100)
# snapshoté sur CETTE commande seulement — jamais réécrit ensuite
```

Exemple (5 m → −10 %, 10 m → −20 %) :

| Commande | Payé avant | Volume devis | Taux figé | Après paiement |
|---|---|---|---|---|
| A 4 m | 0 m | 4 m | 0 % | payé 4 m, A gelée |
| B 2 m | 4 m | 6 m | **−10 %** | payé 6 m, A et B gelées |
| C 5 m | 6 m | 11 m | **−20 %** | A 0 %, B −10 %, C −20 % |

## Résolution de grille

```text
si CustomerVolumeDiscountTier existe pour le client
    → paliers client actifs (personnalisé)
sinon si default_billing_mode == immediate
    → DefaultCustomerVolumeDiscountTier actifs (live)
sinon
    → comportement sprint 37 ( palier client uniquement )
```

Copie à la création / bascule vers comptant : étendre `apply_to_customer` aux comptes
`immediate` **si la grille client est vide** (même bulk_create que l’encours). Les
comptes comptant déjà en base sans copie bénéficient du fallback live.

## Tranches verticales

### T1 — Domaine / service paliers (sans toucher au retarif encours)

Fichiers :

- `backend/apps/customers/services/volume_discounts.py`
- `backend/apps/customers/models.py` (docstring palier : plus seulement « encours »)
- `tests/customers/test_volume_discount_tiers.py`

Livrables :

- lever `_validate_deferred_customer` : paliers autorisés si `deferred` **ou** `immediate` ;
- `resolve_ladder(customer)` (personnalisé vs défaut live, comptant only) ;
- `get_current_month_summary` : branche comptant (volume **payé**, pas les deferred) ;
- `apply_to_customer` accepte `immediate` ;
- `CustomerAdministrationService` : copie des défauts aussi à la bascule **vers** comptant si grille vide ;
- fiche Atelier : `volume_discount_available` vrai pour encours **et** comptant ;
- copy Atelier distincte : encours = « rétroactif sur le mois » / comptant = « à partir de ce palier, sans rétroactivité ».

### T2 — Pricing prospectif + devis

Fichiers :

- `backend/apps/orders/services/pricing.py`
- `tests/orders/test_monthly_volume_discounts.py` (garder les tests encours, **ajouter** les cash)
- `tests/b2b_order_projects/test_cash_gang_sheet_self_service.py`
- `tests/orders/test_shipping_vat_pricing.py` (montants devis si palier)

Livrables :

- helper `paid_monthly_dtf_volume_linear_m(customer, month)` via `Exists(Payment CAPTURED)` ;
- dans `compute_and_persist_order_pricing`, si compte + commande `immediate` : appliquer le palier **sur cette commande uniquement** (snapshot identique aux champs existants `volume_discount_*`) ; **ne pas** boucler sur les sœurs ;
- `estimate_gang_sheet_quote` / `estimate_reorder_quote` : même palier, exposer `volume_discount_percent`, `volume_discount_amount_eur`, `dtf_amount_eur` net, `unit_price_eur` effectif, `volume_discount_threshold_linear_m`, `monthly_volume_linear_m` (payé + devis) ;
- verrou `select_for_update` sur `Customer` au persist (pas au devis) pour sérialiser deux checkouts concurrents.

### T3 — UI client (taux visible)

Fichiers :

- `backend/apps/portal/dashboard_focus.py`
- `backend/templates/portal/client/dashboard.html`
- `backend/templates/portal/client/partials/order_project_summary.html`
- `backend/templates/portal/client/panels/billing.html`
- `backend/templates/portal/staff/customers/detail.html`
- `backend/templates/portal/staff/panels/billing.html`
- `backend/apps/portal/views_staff_customers.py`

Livrables :

- dashboard comptant : volume **payé**, palier actuel, taux, reste jusqu’au suivant ;
- devis Gang Sheet : ligne « Remise volume −X % » + TTC déjà remisé sur le CTA ;
- panneau facture : « Palier −X % sur cette commande » (jamais « tout le DTF du mois » en comptant) ;
- Atelier : badge « Comptant — sans rétroactivité » vs « Encours éligible ».

### T4 — E-mail après capture

Fichiers :

- `backend/apps/notifications/services/email_templates.py`
- `backend/apps/notifications/services/transactional.py`
- hook capture Stripe / confirm paiement (`backend/apps/billing/services/` — point unique existant de passage `CAPTURED`)
- `tests/notifications/test_volume_discount_tier_notifications.py`
- `tests/billing/test_stripe_payments.py` ou test dédié capture → palier

Livrables :

- tag `volume.application_scope` (encours : « sur l’ensemble du DTF éligible du mois » ; comptant : « sur cette commande et les suivantes, sans effet rétroactif ») ;
- planification **après** `Payment.Status.CAPTURED` pour un compte immediate, si un palier est atteint et pas encore notifié `(customer, month, threshold)` ;
- ne pas envoyer au simple devis / pricing `pending` paiement.

### T5 — Documentation

- `docs/architecture/CUSTOMER_PRICING_AND_LOGISTICS.md`
- `docs/architecture/B2B_DEFERRED_BILLING.md` (section comptant prospective)
- `docs/tracking/DECISIONS_LOG.md`
- `docs/sprints/sprint-37-remise-volume-mensuelle.md` : lien « voir sprint 41, encours inchangé »

## Tests minimum (DoD)

### Non-régression encours

- palier 5 m / 10 m : A 4 m puis B +2 m puis C +5 m → A/B/C tous à −20 % (test existant) ;
- commande `immediate` d’un compte **encours** : toujours exclue du volume deferred (test existant) ;
- relevé : commande gelée ;
- isolation inter-clients ;
- update palier → retarif mois courant encours.

### Comptant

- compte immediate sans grille client + défauts Atelier → devis et persist utilisent les défauts ;
- grille client présente → ignore les défauts même s’ils changent ensuite ;
- A 4 m payée 0 %, B 2 m (devis et persist) −10 %, A **reste** 0 % après persist et après capture de B ;
- commande priced mais **non capturée** n’entre pas dans `volume_paye` du devis suivant ;
- `estimate_gang_sheet_quote` TTC reflète le palier (CTA) ;
- permission : create palier sur compte comptant OK avec `manage_customer_pricing`, 403 sinon ;
- isolation : client B ne voit ni volume ni palier du client A ;
- capture : un seul e-mail par (client, mois, seuil) ; pas d’e-mail au devis ;
- Stripe : montant session = total remisé ; pas d’appel `reprice_deferred_month`.

## URLs / HTMX

- inchangées : fiche client Atelier, dashboard client, devis projet (`estimate_gang_sheet_quote` déjà appelé par `views_b2b_order_projects.py`) ;
- pas de nouvelle ressource par id incrémental.

## Hors scope

- Verrouillage UI « un encours ne peut plus choisir comptant » (le code l’autorise encore ; le moteur cash est gated sur le **mode compte**). À traiter dans un lot dédié si produit le confirme.
- Crédit / avoir Stripe si un palier est atteint **après** un paiement (interdit par construction).
- Remise sur préparation, port, ou hors DTF.
- Changement de laize / formule m².

## Checklist de validation

- [x] `python backend/manage.py check` — non exécuté ici (Docker indisponible) ; `ruff check` OK sur les fichiers touchés
- [x] aucune migration (champs snapshot `Order.volume_discount_*` réutilisés)
- [x] Ruff check des fichiers du lot
- [x] tests ciblés volume encours **et** cash (13 tests service/pricing verts en local)
- [ ] suite projet Docker (`make test`) — à lancer quand le démon Docker est dispo
- [x] isolation client / pas de retarif post-capture / e-mail palier après capture
- [ ] QA front manuelle dashboard / devis / fiche Atelier

## Hypothèses

- « Personnalisé » = au moins une ligne `CustomerVolumeDiscountTier` pour le client (même inactive). Une grille client dont tous les paliers sont désactivés = 0 % , **pas** de retombée sur les défauts.
- Le mois est le mois civil de `Order.created_at` (fuseau Django), comme l’encours.
- Payé = `Payment.Status.CAPTURED` (même helper que la gate production).
- Recalcul du palier au persist (soumission / tarification Gang Sheet) pour que Stripe reçoive le TTC à jour ; un devis abandonné ne fige rien.
- Si deux devis concurrent voient le même `volume_paye`, les deux peuvent obtenir le palier franchissant ; acceptable (politique prospective, pas de correction a posteriori).
- Nouvelle migration **évitée** : réutiliser les colonnes snapshot déjà sur `Order`.
