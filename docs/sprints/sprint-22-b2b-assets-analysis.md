# Sprint 22 — Assets B2B versionnés et analyse technique

## Objectif

Permettre à un client B2B de joindre un fichier à chaque ligne de projet, de le remplacer sans
perdre l'historique et d'obtenir une analyse technique avant transmission à IDS Supply.

## Livré

- [x] `Asset`, `AssetVersion` immuable et `AssetAnalysis` dans l'app `uploads` existante ;
- [x] tenant `Customer` explicite sur chaque objet fichier et validation de cohérence ;
- [x] stockage versionné, hash SHA-256 et version courante ;
- [x] backfill additif des `OrderUpload` sans déplacement ni copie de fichier ;
- [x] analyse Celery Pillow : pixels, DPI source, alpha, fond blanc probable et miniature WebP ;
- [x] DPI effectif calculé à partir des dimensions demandées ;
- [x] ajout, remplacement et téléchargement médié via API et portail HTMX ;
- [x] projet transmissible uniquement lorsque toutes les lignes sont analysées ;
- [x] audit ajout, remplacement, analyse, échec et téléchargement ;
- [x] tests d'isolation inter-tenant, validation, versioning et workflow projet.
- [x] analyse rejouable par version sans dupliquer le rapport technique.
- [x] configurateur client unifié : ajout du fichier et de la ligne dans une seule transaction ;
- [x] aperçu immédiat dans le navigateur et aperçu persistant médié par le backend ;
- [x] dimensions physiques proposées depuis les pixels à 300 DPI, puis confirmées par l'analyse
  serveur à partir des DPI intégrés lorsqu'ils existent ;
- [x] contrôle de transparence sur damier, fond blanc, noir ou personnalisé sans altérer l'original ;
- [x] application automatique de la taille limitée à la première analyse afin de préserver toute
  correction manuelle ultérieure.
- [x] fiche client simplifiée : statut et transmission regroupés, références non essentielles
  retirées de la vue, options projet et édition des visuels repliées par défaut ;
- [x] nom du visuel dérivé automatiquement du fichier avec fallback serveur sans JavaScript.
- [x] configurateur déplacé dans une modale native accessible pour l'ajout et la modification ;
- [x] page projet recentrée sur une liste compacte des visuels avec aperçu, taille, quantité,
  DPI, statut et action `Modifier`.
- [x] miniatures multi-formats générées en tâche asynchrone : PNG/JPEG/WebP/TIFF avec
  Pillow, PSD composite avec psd-tools, PDF et AI compatible PDF avec PyMuPDF, EPS et AI
  PostScript avec Ghostscript ;
- [x] rendu EPS/AI PostScript exécuté avec `SAFER`, délai maximal et limites CPU/mémoire ;
- [x] seule la première page des documents multipages est prévisualisée et l'original versionné
  reste toujours inchangé.
- [x] largeur et hauteur facultatives à l'ajout : les formats non lisibles par le navigateur sont
  créés en mode automatique, puis corrigés par l'analyse serveur ;
- [x] rafraîchissement temporaire de la liste pendant l'analyse afin d'afficher la miniature et les
  dimensions finales sans action manuelle.
- [x] parcours asynchrone exposé comme unique entrée `Nouvelle commande` pour les clients activés ;
  l'ancien upload direct reste uniquement disponible comme repli lorsque la feature est désactivée ;
- [x] suppression du bouton et des libellés client `Configurateur DTF` au profit d'un parcours de
  commande unifié.
- [x] formulaire `Nouvelle commande` simplifié sans choix de mode exposé ; la valeur métier sûre
  reste appliquée par le service ;
- [x] aperçu PDF immédiat avant ajout, rendu localement par PDF.js sur un canvas transparent avec
  page entière contenue dans le damier, sans iframe, fond blanc imposé ni recadrage ;
- [x] suppression des rechargements complets pendant l'analyse : la liste des visuels et le résumé
  sont rafraîchis par HTMX, avec état de progression accessible, jusqu'à disponibilité de la
  miniature Celery.
- [x] largeur, hauteur, DPI effectifs et alertes remontent dans le partial HTMX dès la fin de
  l'analyse ;
- [x] diagnostic résolution explicite : optimale à partir de 300 DPI, acceptable de 200 à 299 DPI,
  insuffisante sous 200 DPI, avec seuils configurables ;
- [x] confirmation client obligatoire et versionnée avant transmission ; changement de dimensions
  et remplacement de fichier invalident la confirmation ;
- [x] confirmation auditée, tenant-scoped et disponible dans le portail comme dans l'API.
- [x] détection asynchrone des détails imprimés strictement inférieurs à 0,5 mm à l'échelle
  physique du fichier analysé, avec overlay WebP privé et rapport technique versionné ;
- [x] surlignage rouge activable dans la modale de validation, avertissement explicite et
  confirmation client étendue au contrôle des détails fins ;
- [x] overlay servi uniquement par une route portail tenant-scoped, sans URL média ni chemin de
  stockage exposé, avec test d'accès croisé entre clients.
- [x] zoom de l'aperçu de 100 à 400 %, avec conservation de la zone observée, défilement dans le
  cadre et remise à zéro accessible sur desktop comme sur mobile ;
- [x] couleur unie exacte du support obligatoire côté service lorsqu'un détail sous 0,5 mm est
  détecté ; le choix multicolore est refusé et la règle est expliquée avant confirmation.
- [x] remplacement du fichier limité à l'état `pending` : l'action reste disponible avant le
  démarrage de l'analyse, puis disparaît dès que l'analyse commence et le service refuse toute
  tentative directe ultérieure ; la modale ouverte est conservée pendant le polling HTMX.
- [x] validation du garde-fou de remplacement : tests service/API/portail/UI, suite globale de
  421 tests, Ruff, formatage, JavaScript, Django et migrations conformes, recette navigateur sur
  le projet signalé et sur un projet temporaire avant analyse.

## Compatibilité

- `OrderUpload` conserve tous ses champs et son comportement existants ;
- son nouveau lien `asset_version` est nullable ;
- aucun `Order`, `OrderItem` ou `ProductionJob` n'est créé ou modifié ;
- les fichiers historiques restent à leur chemin actuel.

## API client

Sous `/api/client/customers/<customer_uuid>/order-projects/<project_uuid>/items/<item_uuid>/` :

- `GET|POST asset/` : consulter ou joindre le fichier initial ;
- `POST asset/replace/` : créer une nouvelle version uniquement avant le démarrage de l'analyse ;
- `GET asset/download/` : téléchargement médié.
- `POST confirm-analysis/` avec `{"confirmed": true}` : confirmer dimensions, résolution et
  alertes de la version courante.

Les réponses ne publient ni chemin de stockage ni URL média brute.

Dans le portail client, l'aperçu utilise une route protégée tenant-scoped :

- `GET .../asset/preview/` : miniature WebP analysée, ou original compatible en attente d'analyse.
- `GET .../asset/thin-zones/` : overlay WebP privé des zones sous 0,5 mm lorsqu'elles existent.

Le contrôle des détails fins est indicatif. Il analyse la transparence lorsqu'elle existe, ou les
pixels non blancs d'un fichier à fond blanc probable. Pour un visuel entièrement opaque sans fond
blanc identifiable, le document complet est traité comme surface imprimée. Le seuil physique est
calculé depuis les dimensions de page/artboard, les DPI intégrés ou, à défaut, la même base 300 DPI
que le dimensionnement automatique.

Lorsqu'une zone fine est détectée, l'atelier doit pouvoir ajouter un contour assorti au support
pour préserver le détail au pressage. La confirmation exige donc une couleur unie explicite au
format HEX ; une valeur absente, multicolore ou invalide est refusée côté serveur.

Pour tous les autres visuels, la couleur support démarre sans sélection. La confirmation exige
ensuite un choix explicite entre `Multicouleur` et une couleur unie saisie au color picker. Revenir
sur un choix actif restaure l'état vide sans injecter artificiellement `#FFFFFF`.

## Déploiement et rollback

1. sauvegarder la base ;
2. appliquer `uploads.0010`, puis le backfill `uploads.0011`,
   `b2b_order_projects.0002`, `uploads.0012`, puis `uploads.0013` ;
3. démarrer le worker Celery avec le code applicatif ;
4. vérifier un ancien upload et un nouveau fichier projet ;
5. en rollback applicatif, revenir au code précédent : les liens ajoutés sont nullable et les
   fichiers historiques n'ont pas bougé.

La migration inverse du backfill est volontairement non destructive : elle ne supprime ni asset
ni fichier.

## Hors périmètre

- nesting et estimation de métrage ;
- contrôle OPS actif et demandes de correction ;
- confirmation tarifaire ;
- conversion en commande.

## Validation

```bash
make check
make migrations-plan
make test-b2b
make lint
make test
```

- [x] Contrôle 0,5 mm couvert par tests algorithme, persistance, modale et isolation tenant.
- [x] Zoom et couleur support obligatoire couverts par tests service, HTMX et recette responsive.
- [x] État initial `None`, choix explicite Multicouleur/HEX et transmission Atelier couverts de bout en bout.
