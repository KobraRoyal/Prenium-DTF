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
- App Shopify de **production POD** (OAuth, webhooks de commandes et catalogue). Token Admin d’une app custom autorisé uniquement pour recette locale (même chiffrement). L’app ne demande pas de scopes `assigned_fulfillment_orders` par défaut et ne se déclare pas prestataire d’expédition.

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

### Provenance HD et export RIP (durcissement du 24/09/2026)
- La bibliothèque Drive HD POD est une **source d'import**, pas une version imprimable mutable : le mapping sélectionne un fichier dans le seul dossier source configuré côté serveur et conserve son lien/provenance. Une version locale figée et analysée, explicitement rattachée au `Customer` de la boutique, reste nécessaire pour rendre la recette prête. La copie Drive renommée vers la production est un flux distinct, non activé avant configuration et validation de son dossier cible.
- Un slot POD référence une version immuable `AssetVersion` appartenant au `Customer` explicitement associé à la boutique Shopify. Une référence textuelle historique reste visible pour migration, mais ne rend pas la recette imprimable.
- L’export RIP est un **pass-through** des octets de cette version, sans conversion implicite. Avant publication, le service revalide l’état d’analyse `READY` et l’appartenance client sous verrou transactionnel, puis vérifie extension/MIME, signature, structure du format, taille et SHA-256. Le manifest conserve le `public_id` de version et le hash, jamais un chemin média brut. Si la transaction échoue après publication, le répertoire propre au lot est nettoyé.
- Les relations `ShopifyStore.customer`, `PodRecipeSlot.source_asset_version`, `PodRipLot.customer`, `PodRipLotFile.source_asset_version` et `PodPickSession.customer` sont ajoutées de manière nullable pour préserver l’historique. **Aucun backfill automatique** ne devine le propriétaire d’une boutique réelle ; une boutique non liée est bloquée pour le picking/RIP.
- **Décision DTF du 29/09/2026** : sur demande explicite de l’atelier, DTF accepte PNG, PDF, AI (PDF-compatible ou PostScript), EPS et TIF/TIFF comme originaux HD. Le fichier source validé est transmis au RIP avec son extension réelle, sans rasterisation ni conversion ; le lot peut donc mélanger ces extensions. Pour limiter l'exécution de contenu actif par le RIP, les PDF/AI/EPS doivent provenir de la bibliothèque Drive HD interne avec une `PodDriveHdSource` READY liée à cette même version et à ce même `Customer` ; un dépôt vectoriel client ne suffit pas, même analysé READY. La validation exige une extension/MIME/signature cohérente, une structure lisible, une seule page ou image pour PDF/AI/TIFF, et l’analyse `READY`. Ghostscript compte toutes les pages effectivement interprétées des fichiers PostScript, même sans commentaires DSC fiables. Les notices techniques d’aperçu non bloquantes restent en métadonnées ; les vrais avertissements qualité restent bloquants. PSD/DST/SVG et ces formats pour les autres techniques restent refusés. La compatibilité réelle du logiciel RIP DTF avec chaque format doit être vérifiée avec un fichier d’essai avant usage atelier. Une technique Broderie peut exporter un PNG si son équipement l’accepte ; cela ne vaut pas prise en charge DST.
- Les événements Shopify identifiés portent désormais une commande `PodShopifyOrder` unique par `(boutique, external_order_id)` et une ligne `PodRipWorkItem` unique par `(commande, shopify_line_item_id)`. Deux lignes de même variante sont ainsi distinctes pour l’upsert, le replay, l’update et l’annulation. Les objets historiques restent sans identité, sans backfill déduit ; les payloads legacy restent séparés et refusent l’ambiguïté de variantes répétées.
- Une unité posée passe par le contrôle qualité explicite `PRESSED → QC_PASSED | QC_FAILED`. Un refus conserve un `PodQualityCheck` append-only avec motif et opérateur ; la reprise `QC_FAILED → PRESSED` est une action staff auditée. L’annulation Shopify bloque aussi les pièces déjà posées ou validées QC.
- L’inbox webhook conserve le corps exact après validation HMAC et avant l’accusé de réception asynchrone. La clé d’idempotence est `webhook_id` global : ni le topic ni le domaine boutique, non couverts par le HMAC du corps, ne peuvent créer une seconde livraison du même ID. Un échec de traitement reste `failed` et est repris par Celery Beat après backoff. Le corps est effacé après succès. Les anciens reçus sans corps restent `processed` ; les collisions historiques sont conservées sous un ID synthétique traçable pendant la migration `0015`.
- Les boutiques réelles historiques ne sont pas auto-liées à un Customer. Les secrets webhook boutique hérités d’une ancienne copie du secret OAuth ne sont pas auto-purgés : leur provenance n’est pas déductible de la base après rotation. Une reprise contrôlée est obligatoire avant déploiement général.

### Frontière de responsabilité POD (25/09/2026)
- La plateforme gère la production POD jusqu’au QC final. Quand toutes les lignes POD actives et toutes leurs pièces sont conformes, elle notifie **l’atelier interne** que la production de la commande est terminée. Cette notification n’est ni une déclaration d’expédition ni une promesse de livraison.
- Un événement interne est créé par **passage effectif** à l’état QC complet, lié au contrôle de la dernière pièce. Un ajout de ligne Shopify ou une reprise QC rend l’avis précédent obsolète ; un nouveau passage complet produit un nouvel événement, sans doublon lors d’un POST répété. L’inbox affiche seulement le dernier avis encore valable par commande.
- Les transitions QC et annulation Shopify sérialisent les écritures dans l’ordre boutique → commande → pièce/ligne ; polling, fanout et livraison revalident l’état courant avant toute alerte.
- L’expédition, les étiquettes, le suivi et le fulfillment Shopify sont gérés directement par le connecteur **Shopify ↔ Sendcloud**, hors de cette plateforme. Aucun appel Sendcloud ni fulfillment Shopify sortant ne doit être déclenché par le QC POD.
- `shipping.Shipment` reste réservé aux commandes DTF internes (`Order` + `ProductionJob`) et ne doit pas être relié aux commandes Shopify POD. La route webhook historique nommée `.../pod/fulfillment/` reçoit des événements `orders/*` ; son nom ne décrit pas une responsabilité d’expédition.
- Les installations Shopify existantes peuvent conserver des scopes fulfillment déjà accordés. Réduire le défaut pour les nouvelles installations ne les révoque pas : auditer `oauth_scopes`, puis réautoriser progressivement les boutiques concernées, sans reconnexion forcée ni rotation automatique de secret.

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
- Sync lot manuel vs auto à réception de commande
- 1 OF par commande vs par pièce
- Validation sur le RIP physique de chaque format DTF autorisé (PDF/AI/EPS/TIFF), colorimétrie et transparence incluses
- Mockup schéma vs photo
- Poste pose : route dédiée vs mode pilotage
