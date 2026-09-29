# Sprint POD — Shopify + atelier + WMS

**Branche** : `feature/shopify-pod-wms`  
**ADR** : `docs/architecture/ADR_SHOPIFY_POD_WMS.md`  
**Prompt maître** : `docs/prompts/PROMPT_SHOPIFY_POD_ORCHESTRATION.md`  
**Statut** : lots D0–G présents ; identité Shopify et contrôle qualité ajoutés le 25/09/2026. Périmètre produit confirmé : production jusqu’au QC puis notification de l’atelier interne. L’expédition et le fulfillment passent directement par Shopify ↔ Sendcloud, hors plateforme. App block thème hors scope test boutique.

## Objectif
Livrer l’app Shopify POD de production (mapping, RIP plat, pose, QC, notification interne) et le WMS emplacements, **sans** mélanger avec le flux DTF métrage existant.

## Règles transverses (tous lots)
- SRP / DRY : services applicatifs ; pas de logique dans vues / serializers / templates.
- Isolation : `Customer` / org scope serveur ; `public_id` ; jamais ID incrémental en URL.
- Audit : mouvements stock, écritures mapping et fin de production ; aucun accept/reject fulfillment dans la plateforme POD.
- UI : Tailwind + DaisyUI (`dui-`) + HTMX + Alpine ; shell atelier existant.
- Tests : service + permissions + accès croisé ; checklist sprint mise à jour.
- Graphify avant exploration large ; `graphify update .` après code.
- Orchestration : max 3 sous-agents, profondeur 1 ; Terra lecture / Sol écriture ; 1 writer par set de fichiers.

## Lots (ordre strict)

| Lot | Livrable | Apps / domaines | Vues clés | Skills |
|-----|----------|-----------------|-----------|--------|
| **D0** | Techniques + blanks + entrepôt (zones/bins) | `pod`/`catalog`/`inventory` | `/staff/atelier/pod/techniques/`, blanks, plan entrepôt | domain-db, inventory-wms, ui-ux |
| **D1** | `IdsVariantConfig` + drawers staff + Shopify (même contrat) | overlay variante, templates recettes | catalogue, drawer variante, app block | pim-oms, shopify, ui-ux, security |
| **A** | `PodRipLot` DTF : `02_rip/` plat + manifest | rip sync Drive/NAS | lot impression onglet DTF | pod-workflow |
| **B** | OF + étiquette par pièce / technique | PDF, labels | lot, postes | pod-workflow |
| **C** | Poste scan pose DTF | scan service | `/staff/atelier/pod/pose/dtf/` | pod-workflow, ui-ux |
| **E** | Connexion Shopify + webhooks de commandes | OAuth, HMAC, idempotence | boutiques, NEEDS_CONFIG | shopify, security |
| **F** | Broderie / subli (technique 2+) | export formats | `02_embroidery/`, poste broderie | pod-workflow |
| **G** | WMS ops : mouvements, picking, putaway retours | stock services | stocks, picking, putaway | inventory-wms, security |

## Template plan par lot (sortie agent — max ~40 lignes)

```markdown
## Lot X — plan
### Scope IN / OUT
### Entités & services (nouveaux | réutilisés)
### Fichiers autorisés (liste bornée)
### Migrations
### URLs / HTMX
### Tests (fichiers + cas min)
### Risques POD-xx
### DoD checklist
### Délégation (agents + fichiers exclusifs)
```

## DoD global d’un lot
- [ ] Code + migrations
- [ ] Tests verts ciblés
- [ ] Permissions / isolation vérifiées
- [ ] Audit si mutation sensible
- [ ] Doc sprint + ADR si décision ouverte tranchée
- [ ] `graphify update .`
- [ ] Security review si multi-tenant / webhook / fichier / stock

## Lot D0 — statut
- [x] Apps `pod` + `inventory` (techniques, blanks, warehouse, bins, règles défaut)
- [x] Services SRP + audit + `public_id`
- [x] Vues `/staff/atelier/pod/` (hub, techniques, blanks, entrepôt)
- [x] Tests permissions client/staff + bin par défaut
- [x] Mouvements / picking / qty (lot G)

## Lot D1 — statut
- [x] Modèles Shopify mirror + `IdsVariantConfig` + `PodRecipe`/`PodRecipeSlot` + templates
- [x] `VariantConfigPayload` (contrat staff / future app Shopify)
- [x] Catalogue staff + drawer HTMX `/staff/atelier/pod/catalogue/`
- [x] Badges `needs_config` / mix techniques / ON_STOCK / VIRTUAL
- [x] Tests permissions + save POD + apply template
- [ ] App block Shopify embarqué (lot E ou extension D1-bis)

## Lot A — statut
- [x] File RIP (`PodRipWorkItem`) + `PodRipLot` / `PodRipLotFile`
- [x] Export NAS plat `02_rip/` regroupé par session picking (`POD_RIP/<PICK-…>/02_rip/`) — sans manifest / OF / labels RIP
- [x] Noms ASCII `shop_so_pose_sku.ext` + test collision
- [x] UI `/staff/atelier/pod/lots/`
- [x] Sync Google Drive (projection `POD_RIP/{session}/`, NAS plat reste vérité)

## Lot B — statut
- [x] `PodUnit` (1 pièce / qty) liée au scan Zebra de la session picking
- [x] Liste picking A4 + étiquettes Zebra à la création de session (suivi pièce jusqu’à pose/QC)

## Lot C — statut
- [x] Poste `/staff/atelier/pod/pose/dtf/` scan → slots recette → confirmer pose + audit

## Lot E — statut
- [x] Webhook HMAC Shopify `webhooks/shopify/pod/fulfillment/` → file RIP
- [x] Idempotence file QUEUED (même boutique / SO / SKU)
- [x] OAuth app + token admin chiffré + import catalogue + enregistrement webhook
- [ ] App block Shopify embarqué (hors flux test boutique)

## Lot F — statut
- [x] `prepare_lot(technique_code)` + répertoire plat `02_embroidery/` (seed technique Broderie)

## Lot G — statut
- [x] Réception / picking (scan bin POD-17) / putaway RETURNS
- [x] Refus qty dispo insuffisante (POD-18)
- [x] UI `/staff/atelier/pod/stocks/` (owner atelier)
- [x] Owner client dédié (chemin atelier livré)
- [x] SKU fini ON_STOCK (réception / picking zone FINISHED)
- [x] Contrat mapping marchand (sauf `staff_locked`)
- [x] Hub Operate « À produire » : command bar type Pilotage (sélection, confirm, toasts)
- [x] `prepare_lot(work_item_public_ids=…)` : sélection hub = seule vérité (hors page Lots RIP legacy)
- [x] Session picking PDF A4 + étiquettes Zebra séparées
- [x] Navigation POD séparée production/réglages (26/09/2026) : entrée directe header, rail dans l’ordre du workflow, Stocks selon habilitation WMS, page `/staff/atelier/pod/reglages/` avec synthèse en lecture seule. Catalogue/boutiques/supports/techniques/drawers/photos réservés à `manage_pod_catalog`, emplacements à `manage_warehouse`, toujours avec accès atelier POD. Opérateurs : blocages visibles mais aucun lien de configuration. Tests navigation, accès direct et GET sans mutation ; relecture RBAC indépendante.
- [x] Picking A4 optimisé atelier : regroupement emplacement/support/variante, quantité par groupe, cases de contrôle par pièce, identifiant de scan et pagination avec rappel de session. Étiquette Zebra 100 × 50 mm : support/variante, bac, commande et Code 128 centré avec identifiant lisible ; aucune donnée d'expédition. Validation : PDF multi-page, une étiquette par pièce active, dimensions et identifiants cohérents entre les deux sorties.

## Suite Operate (anti-erreur)
- [x] Unifier scan picking (`PodPickSessionLine`) avec `PodUnit.scan_identifier` (réemploi + FK `unit`)
- [x] Webhooks `orders/cancelled` + `orders/updated` → file QUEUED / freeze production
- [x] Pagination / filtres board (`q`, `queue=ready|blocked`)
- [x] Pose refusée sur unités `ISSUE` ; pick lines voidées au cancel Shopify
- [x] Bouton « Réinstaller webhooks » boutiques

## DoD opérationnel
- [x] Chaîne À produire → réservation de blank → picking PDF → scan pièce + bac → débit stock → lot sélection → pose scan unique
- [x] Cancel/qty Shopify ne cassent pas l’atelier (void + freeze)
- [x] Migrations `0007`–`0015` ; tests POD critiques verts
- [x] Docs ops webhooks 3 topics
- [x] Passes Impeccable Operate : nav contexte POD + distill pose/RIP/stocks + cohérence ui-*

## Audit et durcissement du 24/09/2026

### Livré dans cette branche

- [x] Aucun bootstrap démo lors des GET hub/catalogue/drawer/techniques/stock/lots/entrepôt ; seed uniquement explicite.
- [x] Secret webhook démo aléatoire ; ancien secret connu renouvelé par la migration `0013`.
- [x] HMAC Shopify avant entrée, identifiant de livraison obligatoire, inbox persistante avant accusé de réception en mode asynchrone, reçu idempotent sur `webhook_id` global indépendant des headers boutique/topic, reprise périodique des échecs.
- [x] `variant_id` Shopify prioritaire ; SKU de secours seulement sans ID et sans ambiguïté ; ligne non mappable conservée dans l’inbox en échec/rejeu, sans suppression d’orphelin POD.
- [x] `StockBalance.qty_reserved` utilisé à l’ouverture de session ; scan du bac attendu, mouvement `PICK`, libération sur annulation avant prélèvement.
- [x] RIP interdit tant que toutes les pièces ne sont pas prélevées ; lot limité à une boutique et un Customer.
- [x] Visuel RIP issu d’une `AssetVersion` explicite du même Customer : fichier réel, état READY recontrôlé sous verrou, format structurellement vérifié, taille et SHA-256 vérifiés. L’ancienne référence texte ne rend plus un slot imprimable. DTF conserve les octets et l’extension de l’original autorisé.
- [x] Provenance versionnée figée sur chaque `PodRipLotFile`, manifest sans chemin média brut.
- [x] Répertoire RIP strictement plat ; lot et fichiers nettoyés si la transaction échoue après publication ; templates privés limités à leur boutique.
- [x] Écrans POD mobile à 375 px, drawer clavier/focus, erreurs de stock conservant le bon onglet.
- [x] Host drawer variante partagé (`_variant_drawer_host.html` + `showModal`) sur hub, catalogue et fiche produit ; lots RIP oriente vers À produire (picking requis) au lieu d’un CTA « Préparer toute la file ».
- [x] Liaison boutique → Customer explicite et sélection de version HD dans le drawer, sans auto-liaison d’un client réel.
- [x] Reprise supervisée des anciennes lignes picking `UNTRACKED` : annulation logique uniquement si la ligne est encore QUEUED, sans débit/libération de stock, puis réimpression ; test de service ajouté.

### Restant avant une promesse « POD bout en bout »

- [x] Identifiants Shopify de commande et de ligne + unicité métier : deux lignes distinctes de même variante sont traitées séparément ; l’historique sans IDs demeure en mode legacy strict.
- [x] QC : scan, validation/refus motivé, historique, reprise après correction, permissions et audit.
- [x] Notification interne « production POD terminée » après QC complet de toutes les lignes de commande identifiées, une occurrence par passage valide à cet état.
- [ ] Tests de concurrence PostgreSQL pour commandes/webhooks, quantités et réservations ; recette réelle NAS/Drive/RIP sur boutique liée à un Customer.
- [ ] Politique de rotation/chiffrement des secrets boutique historiques et migration de données des boutiques réelles vers `ShopifyStore.customer` ; l’ancien secret OAuth éventuellement copié en clair doit être identifié et purgé de façon contrôlée.
- [ ] Vérifier sur le RIP DTF réel les originaux PDF, AI, EPS et TIFF (transparence, couleur, taille), après validation logicielle isolée ; PSD/DST restent exclus.
- [x] Validation logicielle des originaux DTF (29/09/2026) : import Drive sans conversion, MIME/signature/structure et empreintes contrôlés, PDF mono-page/TIFF mono-image et PostScript réellement mono-page, sortie RIP avec extension et octets d'origine. Relecture sécurité : PDF/AI/EPS client refusés au mapping et au RIP sans provenance Drive interne READY ; MIME AI PDF corrigé dès l'upload. Régression finale : `347 passed, 4 skipped` sur POD/uploads sous SQLite et PostgreSQL. La recette sur le RIP physique reste ouverte ci-dessus.

### Validation du lot

- [x] Tests POD + cohérence UI + architecture portail : 231 passés localement après durcissement.
- [x] Permissions staff/view-only et accès inter-client testés pour stock et version HD.
- [x] `manage.py check`, Ruff, migration check et build CSS portail staff.
- [x] Revue sécurité indépendante du visuel HD et des nouveaux écrans ; les findings sur chemins RIP, rollback des fichiers, templates inter-boutiques, GET avec écritures et formats non validés ont donné lieu à correctifs/tests.
- [ ] Recette manuelle en environnement de staging avec fichiers d’impression représentatifs.

## Reprise du 25/09/2026 — identité Shopify + QC

- [x] `PodShopifyOrder` et `shopify_line_item_id` ajoutés sans backfill implicite ; ingestions `orders/create|updated|cancelled` ciblées par IDs quand présents. Replay, doublon de variante, séparation cross-store/Customer et legacy testés.
- [x] `PodQualityCheck` append-only ; poste `/staff/atelier/pod/controle-qualite/` scan-first, file des pièces posées, décision conforme/refus avec motif, reprise explicite et historique. Les pièces QC validées sont gelées si Shopify annule.
- [x] Pose protégée contre double scan concurrent et appartenance boutique/client incohérente ; droits lecture/gestion conservés.
- [x] 248 tests POD/portail ciblés passent sur SQLite **et PostgreSQL isolé** (`config.settings.test_postgres`) ; un test PostgreSQL supplémentaire valide le double scan QC concurrent sans doublon d’historique (ignoré sur SQLite). Migrations `0016`–`0017` cohérentes sur une base neuve ; contrôle mobile QC à 375 px sans débordement.
- [x] Les verrous picking ont été limités aux lignes cibles (`select_for_update(of=("self",))`) après un échec réel PostgreSQL sur jointures optionnelles.
- [x] Relecture sécurité indépendante de la notification interne et des verrous QC/annulation : aucun P1 restant après correction et test PostgreSQL concurrent.
- [ ] Recette PostgreSQL/staging sur boutique réelle, NAS/Drive/RIP et Web Push navigateur.
- [x] Base Docker locale réconciliée sans perte : sauvegarde complète vérifiée, deux tables legacy vides déplacées transactionnellement dans `legacy_pod_reconcile_20260925`, puis migrations normales `pod.0016`, `pod.0017` et `notifications.0012`. Aucune table supprimée ni migration simulée ; `web`, `worker`, `beat`, `nginx`, PostgreSQL et Redis sains, HTTP 200 sur `/` et `/healthz/`.
- [x] Fin de production POD : notifier uniquement l’atelier interne après QC complet, sans créer de colis, d’étiquette, de tracking ni de fulfillment Shopify.

### Réconciliation PostgreSQL locale du 25/09/2026

- Sauvegarde avant mutation : `/Users/kobrasolution/.codex/backups/prenium-dtf/pre-reconcile-20260925.dump` (format `pg_dump -Fc`, permissions `0600`, lecture vérifiée avec `pg_restore --list` et `--file=/dev/null`) ; SHA-256 `6298d459f7a574f2a01c79f7c3d363da235f06f0fbb29e4d2bcbb2670b91203c`. Ne pas committer ni partager cette archive, potentiellement sensible.
- Préconditions constatées et revérifiées sous verrou : `pod_shopifyorder` legacy = 0 ligne, `pod_shopifyorderline` legacy = 0 ligne, un `pod_podripworkitem` dont `order_line_id` est NULL ; aucune vue ni trigger utilisateur dépendant. Les deux tables et leurs index/contraintes/séquences ont été déplacés dans un schéma d'archive dédié, hors `search_path`, sans `DROP`, `--fake` ni édition de `django_migrations`.
- Après migration : les anciennes tables sont intactes dans `legacy_pod_reconcile_20260925`, la nouvelle table ORM `public.pod_podshopifyorder` est présente (0 ligne), le work item garde son `public_id` `6ff58933-8802-46a1-a7fc-0902b5e8ce08`, toutes les FK inspectées restent valides. `manage.py check` sans erreur ; 24 tests POD ciblés passés (2 ignorés sur SQLite) ; HTTP 200 et six services Docker sains.
- Dette conservée volontairement : `pod_podripworkitem.order_line_id` et sa FK pointent encore vers la table de lignes legacy archivée, sans valeur active. Ne les retirer que dans une migration ultérieure avec sauvegarde et vérification explicite qu'aucune valeur non NULL n'existe.

### Optimisation Operate de la vue « À produire » du 25/09/2026

- [x] Audit visuel desktop et 375 px : l'ancien panneau vide masquait la session active ; débordement horizontal de 277 px sur mobile ; filtre empilé verticalement ; scan proposé alors qu'aucune pièce n'était réservée ; mapping bloquant enfoui après le picking.
- [x] Une prochaine action contextualisée selon la file et les sessions (prélèvement réservé, nouveau picking, mapping, ancien picking, pose ou état vide), sans ajouter d'action d'expédition.
- [x] Mapping bloquant placé avant les sessions et ouvert quand aucune nouvelle pièce n'est prête ; filtres compacts et état vide informatif ; scan affiché uniquement avec une réservation active (ou pour restituer une erreur de saisie).
- [x] Périmètre Alpine du drawer étendu à la surface entière : ouverture, fermeture et restitution du focus vérifiées dans le navigateur sans enregistrement de données.
- [x] CSS reconstruit et versionné, `collectstatic`, 42 tests ciblés verts, Ruff et `manage.py check` sans erreur ; largeur du document égale au viewport à 375 px et 1280 px. Le filtre « Prêtes » donne un accès direct aux mappings bloquants sans afficher une table vide. Détecteur Impeccable : aucun finding.

## Décision produit du 25/09/2026 — séparation production / expédition

- [x] Shopify ↔ Sendcloud gère l’expédition POD directement ; le logiciel atelier n’est pas propriétaire des colis ni du statut transporteur.
- [x] Le scope OAuth par défaut est réduit à `read_products,read_orders` pour les nouvelles connexions ; auditer les autorisations déjà accordées avant toute réautorisation progressive.
- [x] Notification interne : une par passage effectif à QC complet d’une commande Shopify identifiée, avec contrôle tenant, audit et dédoublonnage des POST ; une nouvelle ligne suivie d’un nouveau QC complet génère une nouvelle occurrence.
- [x] Vue Atelier : signal « Production POD terminée » dans le poste scan-first, sans action d’expédition ; lecture seule et état vide conservés.
- [x] Vérification locale : 241 tests POD/notifications/portail passent sur SQLite (3 scénarios PostgreSQL ignorés) ; 9 tests ciblés passent sur PostgreSQL isolé, dont double scan et annulation concurrente. Aucun appel shipping/Sendcloud/fulfillment ajouté.
- [ ] Recette réelle de la boutique liée à un Customer, navigateur Web Push, NAS/Drive/RIP et validation mobile de la nouvelle liste « terminée ».

## Cohérence CRUD POD du 26/09/2026

- [x] 15 vues alignées sur le même workspace : navigation, hiérarchie, formulaires repliables, retours, erreurs, actions et tableaux accessibles. Contrat : `docs/product-design/POD_CRUD_CONTRACT.md`.
- [x] Création/modification/activation/désactivation des techniques, supports, variantes, zones de marquage et emplacements ; identifiants stables et historique préservé, sans suppression physique ni migration pour ce lot.
- [x] Garde-fous travaux en attente, réservations, stock, règles d’emplacement et chaîne de références actives ; mutations auditées et intentions POST inconnues refusées.
- [x] Recherche/pagination des supports, techniques, catalogue et soldes de stock ; valeurs non sensibles conservées après erreur, tokens jamais réaffichés.
- [x] Relecture sécurité indépendante sans finding bloquant : 19 tests CRUD et 47 tests sensibles rejoués indépendamment.
- [x] Régression finale : 238 tests passent, 3 scénarios PostgreSQL ignorés sur SQLite ; Ruff, `manage.py check` et `git diff --check` verts. Graphe AST rafraîchi sans appel LLM.
- [x] Vérification navigateur desktop 1440 px/mobile 390 px des listes, éditeurs, mapping et stocks ; largeur document 390 px sur stocks après correction du conteneur de table. CSS reconstruit/collecté, Gunicorn rechargé, six services Docker sains et `/healthz/` HTTP 200.
- [ ] Recette métier utilisateur : créer une référence de test, la modifier, vérifier les refus de désactivation sur dépendances actives et parcourir production → QC. Aucun mouvement métier réel effectué pendant la recette navigateur de ce lot.

## Interactions POD dynamiques du 26/09/2026

- [x] Navigation, recherche et formulaires POD améliorés par HTMX sans rechargement du document ; OAuth et PDF restent natifs.
- [x] Preview POST de mode/support sans mutation ; champs conditionnels, draft et erreurs inline ; événement de succès pour actualisation du workspace derrière le drawer.
- [x] Correction du contrôle Customer boutique : droit `customers.view_customer` exigé avant résolution/mutation, liste et association masquées sinon ; refus audité hors transaction de mutation pour préserver la trace.
- [x] 243 tests passent, 3 ignorés sur SQLite ; navigation, preview et validation inline vérifiées dans le navigateur.
- [ ] Relecture sécurité indépendante finale : sous-agent interrompu par limite d’utilisation avant validation. Ne pas considérer ce lot validé pour production avant cette relecture.

## Sélection des marquages POD du 26/09/2026

- [x] Possibilités zone/technique héritées du support parent par ses variantes ; choix guidé de la zone puis de sa technique, fichier HD compatible par marquage.
- [x] Ajout/retrait HTMX en brouillon sans mutation ; marquages requis non retirables, couples falsifiés refusés côté serveur ; enregistrement explicite conservé.
- [x] Recette navigateur : retrait puis ajout de Cœur/DTF sans enregistrement ; desktop et mobile 390 px sans débordement. Aucune donnée métier modifiée.
- [x] Relecture sécurité indépendante du nouveau mapping : aucun bloqueur (permissions, Customer des fichiers, capacités parent, preview sans mutation, audit de sauvegarde).
- [x] Régression finale : 248 tests réussis, 3 scénarios PostgreSQL ignorés sur SQLite ; héritage des variantes, multi-techniques par zone et refus des actions non autorisées couverts.
- [x] Impeccable : aucun finding sur les deux partials ; Ruff et `manage.py check` verts, `/healthz/` HTTP 200 ; graphe AST actualisé sans appel LLM.
- [ ] Recette utilisateur avec versions HD réelles validées ; choisir un fichier par marquage puis enregistrer la recette.

## Simplification initiale de la fiche support — 26/09/2026 (remplacée ci-dessous)

- [x] Section « Zones et techniques possibles » : saisie zone + technique du référentiel uniquement, sans HD ni nouvelle obligation ; héritage parent → variantes rappelé.
- [x] Anciennes contraintes requises conservées et signalées, sans mutation de données existantes ; fichiers HD choisis seulement dans le mapping.
- [x] 32 tests ciblés réussis, Ruff et diff-check verts ; contrôle navigateur des choix et largeur document 390 px, détecteur Impeccable sans finding. Graphe AST rafraîchi.

## Zones et techniques indépendantes du support — 26/09/2026

- [x] Décision utilisateur : aucun couple sur le support parent ; deux listes DB `MarkingZone` et `PrintTechnique`, héritées par toutes ses variantes. La recette produit seule associe zone, technique et version HD.
- [x] Migration additive `pod.0018` : seed 8 zones, reprise des ensembles des possibilités actives, sans suppression des anciennes lignes ni des recettes/versions HD ; fallback legacy transitoire hors nouvelles listes configurées.
- [x] Formulaire parent à deux groupes de cases à cocher, sans champ HD/obligation ; POST HTMX et erreurs avec sélection multiple conservée. Anciennes intentions de couples retirées du portail.
- [x] Validation centrale des deux listes pour preview, sauvegarde et readiness ; retraits utilisés par une recette refusés, parent verrouillé par les deux services ; audit et relecture sécurité indépendante sans bloqueur.
- [x] Tests : 261 réussis, 4 scénarios PostgreSQL ignorés sur SQLite ; 13 tests ciblés réussis sur PostgreSQL, incluant retrait concurrent vs sauvegarde de recette. Backfill de données, héritage, combinaison croisée, UUID, dépendances et permissions couverts.
- [x] Sauvegarde locale vérifiée : `/Users/kobrasolution/.codex/backups/prenium-dtf/pre-independent-marking-20260926.dump` (`0600`, `pg_restore --list` et lecture complète vérifiés). Migration locale appliquée après tests ; décomptes supports/variantes/legacy/recettes/slots/HD inchangés : `1/1/2/1/2/308`.
- [x] Recette navigateur sans mutation : 8 zones DB et 2 techniques DB visibles, anciennes sélections reprises, aucune obligation dans le mapping ; largeur document 390 px en mobile. Impeccable sans finding, Ruff et Django check verts ; six services Docker sains, `/healthz/` 200, graphe AST rafraîchi.
- [ ] Recette métier utilisateur : choisir indépendamment les possibilités du parent, puis créer et enregistrer ses marquages HD dans le mapping produit.
- [ ] Bibliothèque HD Drive POD : sélectionner dans le dossier source configuré, figer une version client analysée et vérifier de vrais fichiers PNG/PDF/AI/EPS/TIFF dans le navigateur. Dossier source confirmé le 28/09/2026 mais vide lors du contrôle ; validation réelle en attente de fichiers d'essai.
- [x] Tranche logicielle Drive HD POD : sélecteur HTMX, validation du dossier/fichier exact, URL et provenance client, import asynchrone borné avec analyse PNG, protection des collisions et refus inter-client. `pod.0019` appliquée sur la base Docker locale après sauvegarde ; décomptes inchangés `1/1/1/1/308` (supports/variantes/recettes/slots/versions HD). Tests POD/portail : `206 passed, 4 skipped` sous SQLite ; tests ciblés Drive HD : `9 passed` sous PostgreSQL. Services `web` et `worker` recréés avec `--no-deps`, identifiant du conteneur PostgreSQL inchangé, santé `ok`.
- [x] Reprise automatique Beat des imports HD `PENDING` ou `IMPORTING` périmés et toujours liés à une recette, avec lease Redis de publication anti-doublon (30 minutes, libérée si broker indisponible) ; tests d'échec de publication Celery, de reprise, de deux passages Beat sans doublon et d'absence de fuite HTTP inter-client ajoutés. Les sources `FAILED` ne sont pas rejouées en boucle. Dossier Drive isolé en environnement de test, panne réseau traitée sans erreur 500. Validation finale : POD `197 passed, 4 skipped` (SQLite), ciblés `25 passed` (PostgreSQL), Django/Ruff/healthcheck verts, six services sains ; relecture sécurité indépendante sans P0/P1.
- [ ] Fournir et valider le dossier Drive de production avant d'activer la copie renommée par commande ; vérifier idempotence, collisions, provenance et séparation des clients. Aucune destination implicite.
- [x] Sauvegarde pré-migration Drive HD du PostgreSQL Docker local le 28/09/2026 : `/Users/kobrasolution/.codex/backups/prenium-dtf/pre-pod-drive-hd-20260928.dump` (1,3 Mio, mode `0600`, archive `pg_restore --list` et lecture complète validées, SHA-256 `37264e8e4db3e1dd65b610b29231f621d74a01c2311c145334ec12b7932fef57`). Le premier essai avait été interrompu par une recréation concurrente du conteneur ; le second est complet et vérifié.

## Operate anti-surcharge (29/09/2026)

- [x] Lots RIP retiré de la nav production (diagnostic Réglages seulement) ; produits catalogue chargés seulement avec `?enqueue=1`.
- [x] Suivi : confirm impression + resync Drive en POST léger (enqueue Celery, sans `get_lot` files/units).
- [x] Hub : compteur Pose uniquement (plus de prefetch waiting_units) ; file diagnostic `list_queue(light=True)`.
- [x] Board Suivi : projection lot allégée (`.only`) ; seed ops_demo confirme l’impression avant pose.

## Hors scope (ne pas toucher)

- Pricing B2B métrage, gang sheets, expédition POD et Sendcloud POD (gérés par le connecteur externe Shopify ↔ Sendcloud)
- Refonte pilotage DTF métrage
- Décisions ouvertes ADR sans validation produit
