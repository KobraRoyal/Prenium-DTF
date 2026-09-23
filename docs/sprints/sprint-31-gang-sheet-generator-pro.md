# Sprint 31 — Gang Sheet Generator Pro

## Objectif

Permettre à un client B2B de créer une planche avant tout projet, d’y importer et analyser ses
fichiers, puis de composer une planche DTF avec géométrie contrôlée, placement optimisé, prix
instantané, rendu asynchrone et séparation stricte entre aperçu client et fichier HD de production.

## Périmètre livré

- Création et liste de planches autonomes, sans projet B2B préalable.
- Laize globale imposée par l’Atelier et snapshot des contraintes à la création.
- Galerie propre à chaque planche, import multiple et analyse technique asynchrone réutilisant `Asset`.
- Galerie filtrable avec statut d’analyse, dimensions détectées et compteur d’utilisation.
- Quantité par visuel (jusqu’à 200 occurrences par action), créée atomiquement et immédiatement
  soumise à l’imposition automatique.
- Espacements horizontal X et vertical Y persistants, appliqués à l’imposition automatique.
- Occurrences multiples, déplacement, redimensionnement, rotation, duplication et suppression.
- Verrouillage des proportions, raccourcis clavier, compteur d’occurrences et taux d’occupation.
- Placement automatique bottom-left avec rotation et hauteur automatique arrondie au pas Atelier.
- Détection en direct et validation serveur des débordements et chevauchements.
- Dimensions affichées en centimètres ; surface et estimation HT recalculées en temps réel.
- Sauvegarde de brouillon protégée contre les mises à jour concurrentes.
- Rendu Celery : aperçu PNG basse définition et PDF HD hybride à taille physique exacte.
- Préservation de la nature source dans le PDF final : PDF vectoriel sans aplatissement, document
  mixte conservant tracés et images, raster intégré à sa définition native et alpha préservé.
- Conversion EPS/AI PostScript en PDF vectoriel sans rééchantillonnage ; PSD conservé comme
  composite raster sans redimensionnement.
- Validation puis création idempotente d’un projet `READY_GANG_SHEET` avec le seul PDF final.
- Sources conservées sur la planche ; sortie HD verrouillée côté client puis rattachée au checkout.
- Sortie PDF HD transmise octet pour octet au checkout après le même contrôle qualité qu’une
  commande classique : aperçu, finesse, semi-transparence, sélection du support et validation.
- Contrôle du livrable sans faux DPI global calculé à partir d’un seul visuel embarqué : chaque
  élément raster conserve sa définition source et les éléments vectoriels restent indépendants du DPI.
- PDF HD visible uniquement dans le panneau Production Atelier avec permission dédiée.
- Synchronisation Google Drive privée et asynchrone dès le rendu HD, avant création de commande,
  avec arborescence dédiée, révision, SHA-256, idempotence et suivi d’échec.
- Réglage Atelier de la laize utile, de l’espacement et des bornes de hauteur. Le champ historique
  de marge reste en base pour compatibilité mais n’est plus exposé ni appliqué à la géométrie.
- Interface client harmonisée avec le portail : en-tête, cartes, boutons, typographies et palette du
  design system IDS Hub, avec progression explicite en quatre étapes.
- Studio responsive structuré Galerie → Composition → Contrôle, métriques prioritaires, états vides
  guidés et zone de travail conservant ses interactions tactiles à 375 px.
- Ajout de visuel unifié avec Order Project : sélection du fichier en premier, puis ouverture
  automatique du configurateur déjà prérempli avec aperçu et paramètres utiles.
- Recadrage non destructif dans la modal d’un nouveau visuel, avec navigation par fichier lors
  d’un import multiple, dimensions de placement recalculées et source originale conservée.
- Choix Manuel/Auto par fichier : détection des pixels visibles pour le raster, des objets natifs
  pour le vectoriel et union illustration + pixels pour les documents mixtes, confirmée côté serveur.
- Canvas physique non déformé : ratio laize/hauteur respecté même sur les planches courtes, aperçu
  clipsé dans son cadre et redimensionnement 90°/270° aligné sur les axes visibles.
- Barre contextuelle sur le visuel sélectionné : rotation, duplication, recadrage et suppression
  accessibles directement sur le canevas ; le recadrage synchronise la révision courante avant
  d’ouvrir la modale d’analyse de la source, puis redessine le canvas après application. L’URL
  d’aperçu du canvas porte la révision validée de la planche afin d’afficher immédiatement le
  nouveau cadrage malgré le cache privé des aperçus.
- La carte d’un visuel prêt présente sa quantité réelle sur la planche (0 à 200). La saisie
  ajuste atomiquement les occurrences après sauvegarde du brouillon : les nouveaux exemplaires
  sont placés dans l’espace libre sans déplacer les existants, une réduction préserve les groupes,
  et un manque de place ou une révision obsolète n’applique aucune modification partielle.
- Panneau d’espacement simplifié sans création de grille : réglages X/Y indépendants, accessibles
  sans sélection, puis application explicite avec réorganisation automatique de la planche.
- Crop HD adapté aux sources raster, vectorielles et mixtes : pixels natifs sans rééchantillonnage,
  clip PDF préservant les objets vectoriels et voie EPS/AI vectorielle inchangée.
- Suppression sécurisée d’une planche avant validation, depuis la bibliothèque ou le studio, avec
  confirmation explicite, conservation des sources et nettoyage des rendus générés.
- Retrait dynamique d’un visuel libre de la galerie, avec blocage explicite tant que des occurrences
  l’utilisent et conservation du fichier source versionné.
- Suppression d’une planche depuis la bibliothèque, y compris après validation ou commande,
  sauf pendant le rendu ; lorsque Drive est actif, le HD doit d’abord être synchronisé. Projet,
  commande éventuelle, asset HD et upload de production restent conservés.
- Bibliothèque de compositions uniquement : cartes uniformes vers le studio, sans filtre ni
  libellé « commandée ». Le Studio d’une planche déjà commandée conserve « Je commande » et
  crée une nouvelle commande (PDF HD réutilisé). La recommande d’une commande existante
  permet aussi de modifier les quantités même lorsque le livrable est un PDF HD de planche.
- [x] Calendrier « Date souhaitée » : popover porté hors overflow (body / dialog) pour rester
  entièrement visible dans l’inspecteur Studio et les autres vues `product-date-picker`.
- Galerie actualisée automatiquement pendant l’analyse : un visuel devient ajoutable dès que son
  contrôle technique se termine, sans rechargement manuel du studio.
- Outils de précision P1 : historique local Annuler/Rétablir borné à 40 opérations de composition,
  aimantation avec guides visuels, distribution régulière et écart exact de la sélection.
- Texte de composition : bouton Texte dans le studio, inspecteur (contenu, police au
  catalogue, taille en mm, couleur, alignement, gras), géométrie identique aux visuels,
  cadre shrink-wrap (largeur et hauteur) limité à la planche, retours à la ligne
  explicites, édition directe sur la planche (clic : écrire, placeholder
  sélectionné, texte existant au caret, Échap termine), PDF HD vectoriel sans
  fichier source.
- Zoom de précision : cadrage de l’objet, du groupe ou de la planche (`Maj+2`),
  ancrage du zoom +/− sur la sélection, plage 50–400 % sans mutation des mm.
- Sélection multiple par cadre à la souris et mode multi-tap tactile, avec sélection globale ; les
  anomalies sont focalisables et les débordements corrigeables lorsqu’ils tiennent dans la planche.
- Suppression atomique de plusieurs occurrences sélectionnées, avec confirmation du nombre,
  audit métier unique et désélection par clic ou tap sur le fond vide du canvas.

## Fichiers principaux

- `backend/apps/gang_sheets/{models,forms,tasks,admin}.py`
- `backend/apps/gang_sheets/services/{gang_sheets,geometry,rendering,hybrid_pdf,text_items}.py`
- `backend/apps/gang_sheets/migrations/0001_initial.py`
- `backend/apps/gang_sheets/migrations/0003_gangsheet_production_asset_*.py`
- `backend/apps/gang_sheets/migrations/0006_gangsheet_axis_spacing.py`
- `backend/apps/gang_sheets/migrations/0008_gangsheetitem_text_kind.py`
- `backend/apps/portal/views_gang_sheets.py`
- `backend/templates/portal/client/gang_sheets/`
- `backend/templates/portal/staff/gang_sheets/settings.html`
- `backend/static_src/js/gang-sheet-editor.js`
- `backend/static_src/css/components/gang-sheet.css`
- `tests/gang_sheets/`

## Permissions et traçabilité

- [x] Scope `Customer` vérifié à chaque accès objet.
- [x] UUID publics uniquement dans les routes.
- [x] Accès croisé à une planche ou un asset refusé.
- [x] Membres client en lecture seule bloqués sur toutes les mutations.
- [x] Configuration limitée à `gang_sheets.configure_gangsheet`.
- [x] PDF HD limité au staff avec `gang_sheets.download_final_gangsheet`.
- [x] Aucun chemin de stockage ni URL média brute exposé.
- [x] Création, mutation, rendu, validation, rattachement et réglage audités.
- [x] Suppression auditée, tenant-scopée et bloquée uniquement pendant le rendu (Drive requis
  si un HD/commande existe).
- [x] PDF final du projet généré non téléchargeable et non remplaçable côté client.
- [x] IDs, dossier et lien Google Drive jamais exposés au portail client.
- [x] Asset de production identifié par la relation tenant-scopée `GangSheet.production_asset` :
  PDF non modifiable, mais confirmation qualité et couleur support autorisées.

## Checklist de validation

- [x] Migration additive générée et `makemigrations --check` propre.
- [x] Tests service : snapshot, prix, occurrences, quantité batch, grille, placement, hauteur et concurrence.
- [x] Tests sécurité : cross-tenant, lecture seule et permission PDF HD.
- [x] Test de rendu PNG/PDF et taille physique gérée côté serveur.
- [x] Tests structurels PDF : tracés vectoriels, document mixte, définition raster native,
  transparence, rotation en dimensions réelles et conversion EPS vectorielle.
- [x] Tests de crop : manifeste multi-fichiers, bornes serveur, isolation client, dimensions utiles,
  pixels natifs raster et conservation des commandes vectorielles/mixes dans le PDF HD.
- [x] Tests de crop Auto : transparence PNG, fond opaque JPEG, objets PDF vectoriels, union PDF mixte,
- [x] Recadrage post-import opérationnel : cadre initialisé après HTMX, tracé direct sur l’image réelle et MIME restauré pour l’auto-crop des fichiers privés.
  recalcul serveur autoritaire et contrat UI Manuel/Auto.
- [x] Test de non-régression canvas : absence de hauteur minimale déformante, calque d’aperçu clipsé
  et inversion des axes lors du redimensionnement d’une occurrence tournée.
- [x] Test UX des actions contextuelles : rotation, duplication, recadrage et suppression accessibles
  sur le canevas, duplication révisionnée sous verrou, panneau X/Y sans répétition, application
  serveur et comportement responsive.
- [x] Multi-sélection avec Maj/Ctrl/Cmd, déplacement groupé et six alignements selon deux
  référentiels explicites : cadre global de la sélection ou zone utile de la planche.
- [x] Historique Annuler/Rétablir, aimantation et guides, cadre de sélection, multi-tap tactile,
  distribution régulière, écart précis et anomalies focalisables avec correction sûre du débordement.
- [x] Suppression par lot tenant-scopée, protégée en lecture seule, auditée et atomique si un ID de
  la sélection est absent ; payload JSON borné avant verrouillage, isolation inter-planche/inter-client
  et fichiers dérivés préservés en cas de rollback ; clic/tap sur le fond pour désélectionner sans
  casser le cadre souris.
- [x] Les annotations et liens interactifs des sources ne sont pas propagés au PDF de production.
- [x] Intégration checkout : planches validées rattachées à la commande.
- [x] Build Tailwind/DaisyUI exécuté.
- [x] Classes dynamiques du canvas conservées après minification Tailwind.
- [x] Suite complète : 517 tests passés ; Ruff check global, format du lot, Django check, migrations et JavaScript conformes.
- [x] Recette navigateur desktop et mobile : quantité, imposition automatique avec espacements X/Y,
  proportions, compteurs et absence d’overflow à 375 px, sans erreur console.
- [x] Recette navigateur des alignements : sélection simple/multiple, gauche sur sélection, droite
  sur planche avec marge, six commandes accessibles et panneau responsive sans débordement.
- [x] Recette navigateur P1 : sélection multiple, écart précis, Annuler/Rétablir jusqu’à l’état
  enregistré, anomalies recalculées, ratio physique du canvas et réglages sans overflow à 375 px.
- [x] Recette navigateur suppression par lot : sélection de trois visuels, confirmation et suppression
  atomique, désélection par clic sur la zone vide, bouton responsive à 375 px et aucune erreur console.
- [x] Zoom cadrage sélection/groupe/planche, ancrage visuel, plage 50–400 %, sans mutation mm.
- [x] Texte studio : corps en `cqw` de planche (plus de lettre unique géante), cadre mesuré
  en px/mm, quatre poignées d’angle pour agrandir, curseur grab pour déplacer.
- [x] Barre d’outils Composer : Enregistrer en icône seule (disquette / check), même taille
  que les outils zoom et historique.
- [x] Import + recadrage : plus d’alerte « Quitter le site » ; la composition est enregistrée
  avant le POST du formulaire.
- [x] Import direct depuis la zone de dépôt, analyse asynchrone dans la galerie compacte,
  détail technique par fichier et recadrage post-import synchronisé avec les occurrences placées.
- [x] Zone de dépôt toujours visible et modale fichier alignée sur la commande : overlays, zoom,
  fonds de contrôle, recadrage manuel/automatique et conservation de l’original.
- [x] Actions de recadrage post-import maintenues dans la modale : l’auto-crop, le cadrage manuel
  et le rétablissement de l’original enregistrent immédiatement le résultat, synchronisent la
  révision et les dimensions sans rechargement, puis ferment la modale après le rafraîchissement
  du canvas ; en cas d’erreur, la modale reste ouverte avec le motif et les anomalies dupliquées
  restent retirées du résumé.
- [x] Aligner / répartir : un groupe mémorisé se comporte comme un seul objet (écarts internes
  conservés, visuels isolés inchangés).
- [x] Inspecteur Réglages : un langage de champs / titres / actions ; les nouveaux imports sont
  placés automatiquement après analyse sans réorganiser la composition.
- [x] Recette du sélecteur direct Gang Sheet et Order Project : annulation sans modale, sélection puis
  aperçu automatique, import galerie et modale plein écran sans overflow à 375 px.
- [x] Tests de suppression : composition et rendus supprimés, sources conservées, statuts liés,
  lecture seule et accès croisé refusés.
- [x] Tests de retrait galerie : visuel libre, visuel utilisé, HTMX, source conservée, lecture seule,
  isolation client et audit.
- [x] Tests de suppression après création du projet puis post-commande : garde Drive, projet,
  commande, asset/version HD et upload préservés, verrouillage `READY_GANG_SHEET` maintenu après
  disparition de la planche.
- [x] Test de galerie dynamique : polling limité aux analyses en cours, disponibilité immédiate à
  l’état prêt et endpoint strictement tenant-scopé.
- [x] Tests de transfert HD : analyse planifiée, empreinte et octets préservés, overlays qualité
  conservés, faux DPI neutralisé, validation du support et checkout sur la même version.
- [x] Texte de composition : item `kind=text` sans asset, contrainte XOR, audit `text_item_added`.
- [x] Tests texte : ajout, duplication, layout, police invalide, PDF vectoriel, rendu, lecture seule
  et isolation inter-clients.
- [x] PDF contrôlé avec Poppler : une page exacte de 550 × 130 mm, sans script ni chiffrement, rendu visuel conforme.
- [ ] Test RIP/Atelier du PDF HD sur la machine de production cible.

## Hypothèses

### Stabilisation issue de l’audit Studio — septembre 2026

Branche : `codex/gang-sheet-audit-fixes`.

- [x] Conflit de révision : aucun renvoi silencieux du brouillon obsolète ; récupération explicite.
- [x] Reprise du suivi du rendu après une erreur réseau, sans double lancement.
- [x] Dimensions vides, nulles ou non finies refusées avant mutation locale.
- [x] Panneaux mobiles inactifs réellement masqués ; propriétés accessibles sans recouvrement.
- [x] Préflight distinguant géométrie, avertissements source et résolution à taille finale.
- [x] Proportions libres expliquées et restauration du ratio source disponible.
- [x] Tests de comportement JavaScript, services, permissions et rendu hybride sans régression.
- [x] Relecture sécurité indépendante et recette navigateur desktop/mobile.
- [x] Laize interprétée comme zone imprimable complète : origine `0,0` et contact exact des bords
  valides ; seuls les dépassements réels sont signalés et bloquent le rendu.
- [x] Duplication positionnée sans chevauchement, avec refus atomique si aucun espace utile n’est libre.
- [x] Groupes protégés : redimensionnement individuel et auto-placement refusés avant dissociation.
- [x] API layout durcie : révision entière obligatoire et payload JSON mal structuré refusé sans erreur 500.
- [x] Recadrage des PDF avec rotation interne 90°/270° identique entre aperçu et PDF HD.
- [x] Tests de non-régression dédiés aux limites utiles sur les quatre rotations, groupes,
  duplication, concurrence et repère PDF tourné.
- [x] Import multi-fichiers enrichi : dropzone accessible, progression, analyse asynchrone par
  fichier, anomalies et overlays médiés, reprise des erreurs et résultats récents en modale.
- [x] Import et galerie adaptés à leur largeur réelle : dropzone compact sans colonne écrasée,
  noms longs repliés sans défilement horizontal, contrôles uniques accessibles et actions tactiles
  de 44 px sur les cartes ; style partagé avec la commande par fichier et limite réelle de cinq
  fichiers par lot.
- [x] Galerie alignée sur la commande par fichier : badges « 300 DPI », « Zones < 0,5 mm » et
  « Pas de dégradé » / « Dégradés détectés », action « Contrôler le visuel » et aucune
  couleur de support.
- [x] Placement initial automatique par POST révisionné et idempotent : verrouillage planche/source,
  contrôle tenant et version courante, respect des groupes et des coordonnées existantes, rotation
  0°/90° au premier emplacement libre et reprise explicite en cas de manque de place. Les sources
  historiques restent en placement manuel ; seuls les nouveaux imports demandent ce placement.
- [x] Recadrage manuel, automatique et retour à l’original conservés après placement ; les
  occurrences sont redimensionnées atomiquement et toute collision ou sortie de laize annule
  l’opération.

Les espacements d’auto-imposition restent des préférences, pas de nouveaux minimums de coupe.
Les avertissements de source ne sont pas assimilés automatiquement à un refus de fabrication.
Le contrôle qualité du PDF et du support au checkout ainsi que la validation RIP atelier restent
distincts du contrôle de composition du Studio. Aucun nouveau profil ICC ni traitement de blanc
n’est introduit dans ce lot.

Validation du lot : 1 274 tests Python réussis dans Docker ; quatre ignorés, dont les deux
harness Node exécutés séparément avec succès sur l’hôte. Les deux autres dépendent d’une
table legacy absente et de verrous PostgreSQL (suite utilisant SQLite). Ruff, contrôle Django,
absence de migration, build des assets et relecture sécurité indépendants conformes.
Recette réelle : 390 × 844 et 1280 × 720, canevas inactif de hauteur nulle, défilement de
l’inspecteur sans superposition, acceptation qualité activant/désactivant la confirmation,
saisie vide restaurée et console sans erreur. Aucune planche client confirmée pendant la recette.

Préflight : pixels natifs après crop pour PNG/JPEG/TIFF ; aucun DPI global inventé pour les
PDF mixtes ou formats réencodés. Les avertissements sont regroupés à l’écran, acceptés
explicitement sur une empreinte de composition courante, puis audités sans messages libres.
Les informations d’absence de DPI vectoriel restent informatives. Les choix d’espacement
et de déformation volontaire restent disponibles, avec restauration des proportions source.

Pre-commit est conforme sur les fichiers du lot. Son passage global a également révélé des
écarts historiques de fins de fichiers/espaces hors périmètre ; ses retouches automatiques
sur ces fichiers ont été annulées. Le détecteur UI signale le damier de travail et une image
d’aperçu initialement sans source : ces éléments sont intentionnels (canevas et aperçu chargé
dynamiquement), pas des défauts visuels observés. Graphe AST actualisé sans appel LLM.

- Le PDF HD est le format intermédiaire de production accepté pour ce lot. La validation RIP réelle
  reste nécessaire avant de déclarer un format TIFF/PNG géant comme alternative.
- Le prix affiché est une estimation HT fondée sur la surface pleine `laize × hauteur` et le tarif
  DTF au m² du client ; le pricing de commande existant reste la source du montant facturé.
- Le projet de commande n’existe qu’après validation et action explicite du client. Il ne contient
  qu’une ligne correspondant au PDF final ; les sources restent rattachées à la planche.
- Le périmètre reste un builder d’imposition. Les profils ICC, couches de blanc, trames, encres et
  pilotes imprimante restent sous la responsabilité du RIP Atelier.
