# Landing DTF — argumentaire et place de la photographie

## Direction et contenu réel

Refinement de l’identité existante, avec Impeccable / clarify et Taste. Même palette,
polices, hero Hairline et démonstration chromatique. Aucun nouveau tirage de direction :
la direction existante The split stage, seed 1106499781, reste la référence.

Le client a confirmé l’absence actuelle de photos de production et demandé des
emplacements réservés. Aucun visuel de banque d’images ou généré ne représente IDS.Supply.
Les deux captures du portail conservent leurs données de démonstration identifiées.

## Argumentaire avant mise en page

| Chapitre | Question du professionnel | Message | Preuve ou emplacement |
|---|---|---|---|
| Offre | Que puis-je vous confier ? | Votre DTF au mètre, pour séries et réassorts. | Transfert Hairline et accès B2B. |
| Réalisations | Que pourrai-je voir sur textile ? | Vos créations, sur textile. | 5 photos : pièce finie, typographie, multicolore, contour, transfert. |
| Couleurs | Quel intérêt pour mes motifs colorés ? | 8 couleurs. Plus de nuances. | Gamut interactif et macro photo. |
| Préparation | Mon fichier est-il adapté ? | La précision, avant l’impression. | Contrôle floral, 2 photos et détails techniques à déplier. |
| Atelier | Qui prend en charge la production ? | Un atelier près de Rennes. | 3 photos : machine, poudrage/cuisson, pressage. |
| Commande | Comment préparer mon besoin ? | Deux façons de commander. | Captures fichiers/Gang Sheet et photo du conditionnement. |
| Tarifs | Quel budget prévoir ? | Un budget clair. | Grille réelle, simulateur et frais éventuels. |
| FAQ | Que dois-je savoir avant de commencer ? | Questions fréquentes. | Fichiers, formats, support, règlement, livraison et pose. |
| Accès | Quelle est la prochaine étape ? | Lançons votre prochaine série. | Demande d’accès professionnel existante. |

## Copy deck

Hero : « Votre DTF au mètre. »
Soutien : « Des transferts pour vos séries, vos collections et vos réassorts. »
Précision : « Impression 8 couleurs, fichiers vérifiés et commande en ligne. »
Qualification B2B et CTA « Demander votre accès » conservés.

Réalisations : « Vos créations, sur textile. »
« Identités de marque, petites typographies, motifs multicolores : le DTF accompagne
vos collections et vos commandes clients. »

Couleurs : « 8 couleurs. Plus de nuances. »
« Pour les identités colorées, les aplats vifs et les nuances de vos illustrations. »
La composition d’encre est montrée par les huit noms ; le diagramme reste illustratif.

Préparation : « La précision, avant l’impression. »
« L’atelier contrôle votre visuel et prépare les zones sensibles en fonction du textile prévu. »
Les trois outils approfondis restent réunis dans un disclosure natif. Chaque texte
explique son opération ; le contenu n’est pas supprimé pour raccourcir le parcours.

Atelier : « Un atelier près de Rennes. »
« Notre rôle : prendre en charge l’impression pour vous laisser vous concentrer sur
le marquage et vos clients. »
« Préparation du fichier, impression et conditionnement : un dossier suivi jusqu’à l’envoi. »

Commande : « Deux façons de commander. »
« Choisissez le parcours adapté à votre manière de travailler. »
Les conditions du compte et du comptant restent explicites. Aucun nouveau format promis.

Tarifs : « Un budget clair. »
« Estimez votre commande avec la grille en vigueur et les remises mensuelles disponibles. »
Les montants et conditions sont inchangés, y compris les 6 € HT éventuels.

Final : « Lançons votre prochaine série. »
« Présentez votre activité pour demander l’ouverture de votre espace et préparer votre première commande. »

## Photographies à fournir

Douze emplacements et deux captures réelles du logiciel. Les formats sont volontairement
limités : 3:2 et une grande image de galerie qui occupe deux rangées sur ordinateur.
Les placeholders n’ouvrent pas de fenêtre vide. Le viewer est réservé aux images réelles.
Une source statique et un texte alternatif peuvent être fournis au composant photo pour
remplacer chaque emplacement sans refaire la mise en page.

La galerie montre le résultat ; le gamut explique les encres ; la préparation explique
le fichier ; l’atelier identifie le producteur ; la commande explique le parcours.
Les répétitions nécessaires à l’usage (navigation, CTA, FAQ, libellés d’outils) sont conservées.

## Validation

- **198 tests Python** réussis : UI, offre publique et cohérence portail.
- **13 tests JavaScript** réussis : prix, mouvement et horloge des séquences.
- Recette navigateur finale : 9 chapitres, 12 zones photo, absence d’action vide,
  ouverture par lien et lien profond, comparateur, couleurs textile, compensation,
  transparence au clavier, toucher et disclosure sans JavaScript.
- Viewer photo vérifié sur deux images de fixture injectées uniquement dans le
  contexte de test. Aucun de ces visuels ne s’affiche comme production réelle sur la page.
- Régressions hero, gamut, menu, onglets, captures/zoom, FAQ et mouvement réduit validées.
- Débordement horizontal : 0 à 375, 390, 768, 1024 et 1440 px ; aucune erreur JS.
- Ruff, syntaxe JS, `git diff --check` et lint Taste : aucun échec.
- Inspection Taste finale à 1440 / 768 / 390 : **0 FAIL** avec les deux exceptions
  existantes `few-pictures` (photos non fournies) et `eyebrow` (bandeau demandé).
  Aucun élément masqué pour contourner l’audit. Le contenu du disclosure fermé utilise
  une règle `display: none` cohérente avec son état natif, et réapparaît automatiquement
  à l’ouverture, avec ou sans JavaScript.
- Avertissements : palette crème de marque, absence de vidéo réelle, un libellé SVG
  petit, diversité des tailles et mouvement modéré sur téléphone. Pas d’effet ajouté
  aux emplacements vides pour atteindre un quota d’animations.
- Les dix captures de l’inspection finale ont été ouvertes et examinées. La passe
  corrective a rendu les cadres photo visibles sur leur fond et explicité l’état fermé
  du disclosure pour les moteurs de mise en page.

| Largeur | Mots affichés avant → après | Hauteur avant → après | Débordement final |
|---|---|---|---|
| 1440 px | 1035 → 886 | 10858 → 10551 px | 0 px |
| 768 px | 1036 → 888 | 9752 → 8503 px | 0 px |
| 390 px | 1036 → 888 | 12723 → 11016 px | 0 px |

Le comptage automatique inclut les légendes et contrôles visibles, et varie légèrement
avec la largeur. La baisse est d’environ **14 %**. Les informations détaillées restent
accessibles à la demande. La hauteur finale diminue malgré les cinq réservations photo
supplémentaires. La galerie passe de six images isolées à cinq sujets de résultat ; les
sujets de production sont répartis près des arguments qu’ils documentent.

Aucun prix, modèle, accès ou règle de facturation modifié. Pas de nouvelle promesse de
livraison, de tenue au lavage ou de performance colorimétrique.

## Critique finale

ROUND 2

Seen in one second: une offre DTF au mètre pour professionnels, avec une demande d’accès claire.

Idea (one sentence): le professionnel voit le transfert, puis les futurs résultats et les étapes de l’atelier.

Live thing: ouvrir le transfert et explorer son rôle matière, puis préparer le budget et le fichier.

Layout words by section: hero=split / résultat=editorial / couleur=diagramme+macro /
préparation=workstation+disclosure / atelier=photos+texte / commande=captures+photo /
prix=simulateur / FAQ=liste / accès=statement.

Scores: design 6.5 · usability 8.5 · creativity 7.0 · content 5.0 → overall 6.8.

Caps applied: photographies absentes et placeholders explicitement demandés. Autoévaluation
prudente ; ce score ne préjuge pas du résultat après intégration des prises de vue.

Top three problems (most visible first), each with the screenshot it shows in and the fix:
1. `desktop-page-01.jpg` : les grandes surfaces attendent les photographies réelles. Fournir
   d’abord la pièce finie, puis les deux macros de résultat.
2. `tablet-page-01.jpg` : les cadres atelier ont besoin de prises de vue cohérentes. Prévoir
   un plan machine large et deux détails de matière / pose.
3. `mobile-page-02.jpg` : les captures du portail sont petites dans le flux. Leur
   agrandissement natif et le mode taille réelle restent disponibles et testés.

## Intégration ultérieure des photos

Composant : `backend/templates/shop/partials/dtf/photo.html`.
Paramètres : `photo_id`, `title`, `caption`, source facultative `image_src` dans static,
et `alt_text` décrivant le contenu réel de la photo. Les images s’ouvrent alors dans
le viewer existant ; le cadre et sa légende gardent leur emplacement.

Prévoir des sources 3:2, environ deux fois leur largeur affichée, sans dépasser 2400 px
pour les grands plans. Garder les couleurs de l’impression et la texture du textile.
Le cadrage principal de la galerie s’étire sur deux rangées sur ordinateur et revient
au format 3:2 sur mobile. Les textes alternatifs et légendes sont à confirmer avec les
images réellement retenues.

Rapports et captures locaux : `.taste-skill/editorial-before`, `.taste-skill/editorial-final`
et `output/playwright/editorial/`. Aucun nouveau média externe : aucun crédit photo tiers requis.


## Correctif du détecteur — image de galerie sans source

Le signalement `broken-image` était valide : le dialogue contenait initialement une
balise image sans source. Cette balise a été remplacée par un conteneur neutre.
L’image est créée seulement après sélection d’une photo possédant une source valide,
avant l’ouverture du dialogue. Les réservations photo restent statiques.

Aucune règle ignorée, aucun signalement masqué. Détection ciblée Impeccable : aucune
anomalie. Cinq tests de contenu réussis, dont le nouveau contrôle de toutes les sources
d’image de la page initiale. Recette du lecteur complétée par des assertions sur l’absence
d’image factice au repos et la création de l’image réelle à l’ouverture.
