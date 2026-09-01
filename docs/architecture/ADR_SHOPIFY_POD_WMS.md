# ADR — App Shopify POD + WMS emplacements

## Date
2026-08-30

## Statut
Accepté (décisions audit canvas) — implémentation par lots

## Contexte
Prenium DTF est aujourd’hui un SaaS B2B DTF au mètre (laize 55 cm), avec OF PDF, scan atelier et Drive. L’audit cible une **app Shopify POD** (impression à la demande + pose) **séparée** du flux métrage, avec mapping variante → blank → slots techniques, modes ON_STOCK / VIRTUAL, et **emplacements entrepôt par produit**.

Référence audit : canvas Cursor `audit-shopify-pod-app` (session locale). Ce dépôt n’a pas encore d’app Shopify ni de WMS.

## Décision

### Canal
- App Shopify **fulfillment** (OAuth, webhooks, location Prenium). Token Admin d’une app custom autorisé uniquement pour recette locale (même chiffrement).

### Atelier POD
- Zone dédiée `/staff/atelier/pod/` — **isolée** du pilotage DTF métrage.
- Lot RIP : répertoire **plat** `02_rip/` (un dossier par technique : `02_embroidery/`, etc.) + manifest ; miroir NAS pour watch folder.
- Poste pose plein écran (scan → mockup + zone).

### Mapping variante (M1–M4)
| ID | Décision |
|----|----------|
| M1 | Config **staff Prenium + marchand Shopify** (même contrat métier) |
| M2 | Poses blank **requises + optionnelles** ; NEEDS_CONFIG si slot requis manquant |
| M3 | **Mix techniques** sur une variante (1 slot = 1 zone + 1 technique + HD) |
| M4 | Modes : `POD` \| `ON_STOCK` \| `VIRTUAL` \| `UNMANAGED` \| `DISABLED` |

### WMS (M5)
- Emplacement entrepôt par produit (blank, fini, retour).
- Entités : `Warehouse`, `WarehouseZone`, `StorageLocation`, `StockBalance` (SKU × bin × owner), `StockMovement`, `ProductLocationRule`.
- Picking trié par code emplacement ; scan bin obligatoire ; owner atelier vs client isolé.

### Ordre des lots
`D0` → `D1` → `A` → `B` → `C` → `E` → `F` → `G` (détail dans `docs/sprints/sprint-pod-shopify-wms.md`).

## Conséquences
- Nouvelle app Django (ex. `pod` / `inventory`) plutôt que polluer `production` métrage.
- Services SRP : config variante, RIP lot, reservation stock, movements — jamais dans les vues.
- `public_id` partout ; audit sur mouvements et écritures mapping.
- Tests accès croisé + permissions sur chaque lot sensible.
- Relecture `ids_security_reviewer` obligatoire sur multi-tenant, webhooks Shopify, fichiers HD, stock.

## Alternatives rejetées
- Token Shopify manuel comme canal produit unique (Option B). Recette locale : token app custom chiffré, OAuth reste la cible.
- Sous-dossiers par commande dans `02_rip/` (casse le watch folder RIP).
- Logique métier dans templates HTMX / app blocks Shopify.
- Un seul mode POD sans ON_STOCK / VIRTUAL.
- Stock sans emplacement (qty globale uniquement).

## Ouvert (ne pas décider dans le code sans ADR update)
- 1 lot RIP global vs par boutique
- Sync lot manuel vs auto à accept fulfillment
- 1 OF par commande vs par pièce
- Format RIP PNG/TIFF vs PDF
- Mockup schéma vs photo
- Poste pose : route dédiée vs mode pilotage
