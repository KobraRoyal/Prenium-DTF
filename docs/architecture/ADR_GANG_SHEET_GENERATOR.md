# ADR — Gang Sheet Generator Pro

## Statut

Accepté pour le Sprint 31.

## Contexte

Les clients B2B doivent pouvoir préparer une planche avant toute commande. La composition
d’une planche DTF était réalisée hors plateforme et dépendait auparavant d’un projet créé en
amont. La largeur utile dépend de la machine Atelier,
le prix dépend de la surface consommée et le fichier haute définition ne doit jamais être exposé
au client.

## Décision

Créer l’app dédiée `gang_sheets` autour de quatre modèles :

- `GangSheetSiteSettings`, singleton global administré par l’Atelier ;
- `GangSheet`, tenant-scoped par `Customer`, autonome à la création puis rattaché au projet et à la commande ;
- `GangSheetSourceAsset`, galerie source propre à la planche avec dimensions analysées ;
- `GangSheetItem`, occurrence d’une `AssetVersion` avec position, taille réelle et rotation.

La planche snapshotte la laize, les marges, l’espacement et les bornes de hauteur lors de sa
création. Un changement de machine ne modifie donc jamais silencieusement un brouillon existant.
La hauteur, la surface et l’estimation tarifaire sont recalculées par un service serveur. Le
navigateur fournit un feedback instantané, mais ne constitue pas la source d’autorité.

Les fichiers sont importés directement dans la galerie de la planche via le service `Asset`
partagé. Ils suivent la même validation MIME/signature, le même stockage versionné et la même
analyse asynchrone que les fichiers d’un projet B2B. Les planches historiques conservent leur
projet et leur galerie est reprise par migration depuis les assets de celui-ci.

Le client peut retirer une entrée de galerie tant que la planche reste modifiable et qu’aucune
occurrence de cet asset n’est présente dans la composition. Le retrait supprime uniquement la
relation `GangSheetSourceAsset` : l’`Asset`, ses versions et les octets source restent conservés
pour les autres projets et pour la traçabilité documentaire. L’action est tenant-scopée et auditée.

Le placement automatique utilise une stratégie bottom-left déterministe : occurrences triées par
surface, test des deux orientations sur les arêtes disponibles, score minimisant la hauteur puis
l’abscisse. La validation serveur refuse tout débordement ou chevauchement.

La quantité reste dérivée des occurrences afin de conserver une seule source de vérité. Les ajouts
batch et les répétitions rangées × colonnes sont atomiques, limités à 200 occurrences par action et
annulés intégralement si la géométrie ne tient pas dans les contraintes snapshotées de la planche.

Le produit est volontairement un Gang Sheet Builder, pas un RIP. Il prépare une imposition et un
fichier physique reproductible, sans gérer les profils ICC, les couches de blanc, les trames, les
niveaux d’encre ni le pilote de la machine.

Le rendu Celery produit deux artefacts distincts :

- un PNG basse définition téléchargeable via une route client tenant-scoped ;
- un PDF hybride à taille physique exacte, stocké comme artefact privé et servi uniquement aux
  membres staff autorisés par `gang_sheets.download_final_gangsheet`.

Le compositeur HD préserve la nature de chaque source. Les pages PDF vectorielles ou mixtes sont
placées comme objets PDF sans rasterisation globale : tracés, textes, polices et images embarquées
restent séparés. Les PDF compatibles produits par Illustrator suivent la même voie. Les sources
EPS/AI PostScript sont converties en PDF vectoriel par Ghostscript, sans profil de réduction ni
rééchantillonnage. Les PNG, JPEG et TIFF sont intégrés avec leurs pixels natifs, leur transparence
et leur profil ICC lorsque le format le fournit. Les formats de travail raster non intégrables
directement, notamment PSD, utilisent leur composite aplati en PNG sans redimensionnement.

Le recadrage proposé dans la modal d’import est non destructif. La planche stocke une fenêtre
normalisée `(x, y, largeur, hauteur)` sur `GangSheetSourceAsset`, tandis que l’`AssetVersion`
originale reste inchangée. Les dimensions physiques proposées et les aperçus utilisent cette
fenêtre. Dans le PDF HD, une source PDF ou mixte est placée avec un clip PDF natif ; ses tracés,
textes, polices et images embarquées ne sont donc pas aplatis. Les sources EPS/AI PostScript sont
d’abord converties en PDF vectoriel selon la voie existante, puis clippées. Pour une source raster,
seuls les pixels compris dans la fenêtre sont conservés, sans mise à l’échelle ni rééchantillonnage.

La modal propose un mode Manuel et un mode Auto par fichier. Auto utilise la transparence ou le
fond dominant pour borner les pixels raster. Pour un PDF vectoriel, il unit les limites natives des
tracés, textes et nuances ; pour un PDF mixte, il ajoute les limites des images embarquées. Les
formats EPS/AI/PSD/TIFF sans aperçu navigateur sont analysés via leur aperçu serveur sécurisé. La
proposition visuelle du navigateur reste indicative : lors de l’import, le serveur relit l’original,
recalcule la fenêtre et audite le type détecté (`vector`, `raster` ou `mixed`). Une modification du
cadre Auto dans la modal repasse explicitement le fichier en mode Manuel.

L’aperçu client et les diagnostics de finesse/semi-transparence restent volontairement
rasterisés : ils sont indépendants du livrable HD. Le compositeur crée une page neuve et ne copie
pas les annotations, liens ou actions interactives des PDF sources. La taille, la rotation et la
position sont appliquées dans l’espace physique de la planche en millimètres.

Le stockage Django privé sur le volume média reste la source transactionnelle et le secours local.
Dès qu’un rendu HD est prêt, une seconde tâche Celery synchronise le PDF sur le Shared Drive dans
`Gang Sheets/AAAA/MM/C-<client>/GS-<planche>/`. Chaque révision possède un nom distinct et une
empreinte SHA-256 enregistrée dans `GangSheetDriveSync`. La tâche est idempotente, ses échecs sont
audités et aucun identifiant Drive n’est envoyé au portail client.

## Sécurité

- Tous les objets client sont filtrés par `Customer` et exposés par UUID public.
- Une occurrence ne peut référencer que la version courante analysée d’un asset de sa galerie.
- Les coordonnées de crop sont revalidées côté serveur et contraintes à la surface du visuel.
- Le mode Auto ignore les coordonnées proposées par le navigateur et recalcule depuis l’original.
- Les membres `readonly` ne peuvent modifier, rendre ou valider une planche.
- Aucun chemin de stockage ni `MEDIA_URL` n’est exposé.
- La validation, le rendu et la configuration Atelier sont audités.
- Une révision optimiste empêche un onglet ancien d’écraser un brouillon plus récent.

## Création différée du projet, commande et production

Une planche autonome validée crée, sur action explicite et idempotente, un `B2BOrderProject` en
mode `READY_GANG_SHEET`. Ce projet contient exactement une ligne et un nouvel `Asset` : le PDF
final produit par le serveur. Les fichiers sources restent dans la galerie et ne sont pas recopiés
dans la commande. Son empreinte et ses octets sont conservés. Le PDF HD repasse ensuite dans le
contrôle qualité du tunnel classique afin de produire l’aperçu et de détecter les détails fins et
les semi-transparences. Sa résolution globale n’est toutefois pas déduite du plus grand visuel
embarqué et aucun DPI artificiel n’est annoncé pour la planche : le contrôle distingue les
éléments vectoriels des images raster conservées à leur définition source. Le client choisit la
couleur du support, valide le contrôle, puis transmet le projet avec le tunnel habituel.

L’asset final est relié à `GangSheet.production_asset`. Le portail client peut en afficher l’aperçu
basse définition mais refuse son téléchargement et masque les actions de remplacement/suppression.
La relation métier permet au portail d’ignorer uniquement le faux DPI global calculé à partir
d’une image interne du PDF, tout en conservant les overlays de finesse et de semi-transparence,
ainsi que l’obligation de couleur support. Le PDF HD reste servi uniquement au staff autorisé. Lors du
checkout, la commande référence la même `AssetVersion`, donc le même fichier, puis la planche
validée est rattachée à la commande et devient visible dans le panneau Production Atelier.
Lorsque `GOOGLE_DRIVE_SYNC_ENABLED` est actif, le checkout refuse la création de la commande tant
que la révision HD courante n’est pas marquée synchronisée sur Drive. L’upload de commande conserve
ensuite son workflow Drive historique dans l’arborescence `Commandes/`.

Dès que le PDF HD est sécurisé dans un projet `READY_GANG_SHEET`, le client peut retirer la Gang
Sheet de sa bibliothèque, y compris avant la création effective de la commande. La suppression
n’est autorisée que si la planche validée référence l’asset de production réellement porté par une
ligne de ce projet. Lorsque Google Drive est actif, la révision HD courante doit également être
marquée synchronisée. Le projet, l’`AssetVersion` HD et, lorsqu’ils existent, la commande et son
`OrderUpload` restent conservés. Le caractère non modifiable du livrable est alors dérivé du mode
`READY_GANG_SHEET`, et non plus de la seule présence de la Gang Sheet supprimée. La copie locale
propre au builder est nettoyée ; les artefacts déjà transmis au workflow de commande, à Drive et à
la production ne sont pas supprimés.

## Alternatives refusées

- Enregistrer uniquement un JSON libre dans le projet : indexation, contraintes et permissions
  objet insuffisantes.
- Générer le rendu HD dans le navigateur : résultat non déterministe, contrôles contournables et
  fuite du fichier final vers le client.
- Reproduire le RIP Atelier dans IDS Hub : périmètre matériel et colorimétrique trop spécialisé,
  alors que le builder peut fournir un fichier d’imposition déterministe au RIP existant.
- Réutiliser `OrderUpload` avant création de commande : mélange des agrégats déjà refusé par
  l’ADR Asset partagé.
- Utiliser la variable `DTF_LAIZE_CM` sans snapshot : un changement de configuration réécrirait
  implicitement la géométrie et le prix des brouillons.

## Rollback

L’app est additive. Désactiver les routes et le lien de navigation suffit pour revenir au parcours
projet existant. Les commandes, uploads et jobs de production restent autonomes. Avant suppression
des tables, les fichiers `gang-sheets/` doivent être archivés et leurs références vérifiées.
