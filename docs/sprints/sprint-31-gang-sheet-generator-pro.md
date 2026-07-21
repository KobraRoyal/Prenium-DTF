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
- Répétition régulière d’une occurrence en rangées × colonnes avec espacements X/Y contrôlés.
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
- Réglage Atelier de la laize, des marges, de l’espacement et des bornes de hauteur.
- Interface client harmonisée avec le portail : en-tête, cartes, boutons, typographies et palette du
  design system IDS Hub, avec progression explicite en quatre étapes.
- Studio responsive structuré Galerie → Composition → Contrôle, métriques prioritaires, états vides
  guidés et zone de travail conservant ses interactions tactiles à 375 px.
- Ajout de visuel unifié avec Order Project : sélection du fichier en premier, puis ouverture
  automatique du configurateur déjà prérempli avec aperçu et paramètres utiles.
- Suppression sécurisée d’une planche avant validation, depuis la bibliothèque ou le studio, avec
  confirmation explicite, conservation des sources et nettoyage des rendus générés.
- Retrait dynamique d’un visuel libre de la galerie, avec blocage explicite tant que des occurrences
  l’utilisent et conservation du fichier source versionné.
- Suppression d’une Gang Sheet dès que son HD est sécurisé dans un projet `READY_GANG_SHEET` et,
  lorsque Drive est actif, synchronisé dans sa révision courante ; projet, commande éventuelle,
  asset HD, upload de production et verrouillage métier restent conservés.
- Galerie actualisée automatiquement pendant l’analyse : un visuel devient ajoutable dès que son
  contrôle technique se termine, sans rechargement manuel du studio.

## Fichiers principaux

- `backend/apps/gang_sheets/{models,forms,tasks,admin}.py`
- `backend/apps/gang_sheets/services/{gang_sheets,geometry,rendering,hybrid_pdf}.py`
- `backend/apps/gang_sheets/migrations/0001_initial.py`
- `backend/apps/gang_sheets/migrations/0003_gangsheet_production_asset_*.py`
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
- [x] Suppression auditée, tenant-scopée et bloquée pendant le rendu ou après rattachement métier.
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
- [x] Les annotations et liens interactifs des sources ne sont pas propagés au PDF de production.
- [x] Intégration checkout : planches validées rattachées à la commande.
- [x] Build Tailwind/DaisyUI exécuté.
- [x] Classes dynamiques du canvas conservées après minification Tailwind.
- [x] Suite complète : 476 tests passés ; Ruff check global, format du lot, Django check, migrations et JavaScript conformes.
- [x] Recette navigateur desktop et mobile : quantité, imposition automatique, grille 2 × 2,
  proportions, compteurs et absence d’overflow à 375 px, sans erreur console.
- [x] Recette UI du nouveau studio : cohérence avec le portail, ordre mobile Galerie → Composition →
  Contrôle, métriques et états vides lisibles, aucune erreur console.
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
- [x] Tests Drive précommande : octets HD exacts, arborescence, idempotence, nouvelle révision,
  échec audité, tâche Celery, isolation client et blocage checkout si la sauvegarde est incomplète.
- [x] PDF contrôlé avec Poppler : une page exacte de 550 × 130 mm, sans script ni chiffrement, rendu visuel conforme.
- [ ] Test RIP/Atelier du PDF HD sur la machine de production cible.

## Hypothèses

- Le PDF HD est le format intermédiaire de production accepté pour ce lot. La validation RIP réelle
  reste nécessaire avant de déclarer un format TIFF/PNG géant comme alternative.
- Le prix affiché est une estimation HT fondée sur la surface pleine `laize × hauteur` et le tarif
  DTF au m² du client ; le pricing de commande existant reste la source du montant facturé.
- Le projet de commande n’existe qu’après validation et action explicite du client. Il ne contient
  qu’une ligne correspondant au PDF final ; les sources restent rattachées à la planche.
- Le périmètre reste un builder d’imposition. Les profils ICC, couches de blanc, trames, encres et
  pilotes imprimante restent sous la responsabilité du RIP Atelier.
