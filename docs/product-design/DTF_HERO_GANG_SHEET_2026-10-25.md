# Hero DTF — film courbé et planche multi-motifs

## Demande et direction

Passe Hairline et Impeccable centrée sur le hero existant : retirer son panneau blanc,
poser le transfert directement sur le fond crème, enlever les deux traits du film,
relever légèrement un coin et représenter une planche DTF avec plusieurs visuels.
L’objet et le geste étaient déjà choisis ; aucune étape de choix de concept nécessaire.
La figure garde le kernel et le bench Hairline inchangés.

## Géométrie et matières

- Film PET : contour arrondi et échantillonné sur les segments droits pour que le coin
  se courbe localement. Le relèvement se situe au coin droit de la vue isométrique.
- Les deux marques intérieures et le long reflet rectiligne disparaissent. Un petit
  reflet de matière suit la zone courbée. Le bord extérieur conserve sa faible épaisseur.
- Cinq motifs disposés comme une planche : une grande fleur, un soleil à bandes,
  une petite fleur, un feuillage et trois vagues réunies en un motif.
- Les pièces géométriques des encres servent également au blanc et à la poudre.
  Aucun rectangle blanc uniforme sous les zones transparentes.
- Les grains de poudre sont déterministes et limités à l’union des silhouettes imprimées.
- La sélection utilise les silhouettes de destination ; les espaces transparents
  s’appuient sur la bande de couche la plus proche. Aucune lecture de la géométrie animée.
- Les ressorts, tweens, réduction des mouvements et sommeil hors écran restent ceux
  du moteur Hairline. La figure ne crée aucune boucle de rendu indépendante.

La couleur est appliquée par la feuille de style du site, conformément au brief matière,
et non dans le fichier de figure. Les libellés restent hors du dessin.
Le panneau de fond du hero est transparent ; les contrôles et infobulles conservent
leur surface propre pour leur lisibilité. L’infobulle de bureau est décalée au bord
pour dégager les motifs les plus à droite.

## Repli statique

Le SVG de secours est généré depuis la même géométrie au repos : film et encre seulement,
avec les couleurs calculées figées et les références de gradients locales. Il représente
une illustration technique, jamais une photographie de production.
Le script de capture de la passe se trouve dans `output/playwright/hero-sheet/capture-preview.cjs`.

## Validation

- **17 tests Python ciblés** réussis : contenu marketing, marque, accès et structure.
- **13 tests JavaScript** réussis sur les horloges, les transitions et le prix.
- Le nouveau test SVG vérifie les cinq motifs, l’absence des deux traits sur PET,
  le coin courbé, la taille du fichier et l’absence de référence réseau dans les gradients.
- Validateur Hairline : kernel et bench intacts, figure de 165 lignes conforme.
- Banc Hairline : huit vues dans le cadre 400 × 320, repos 284 × 143 (32 % du cadre),
  réponse « Encres 8 couleurs » au point d’essai, aucune erreur console et arrêt au repos.
- Planches de contrôle, de mouvement et de lecture à 240 px ouvertes et examinées.
- Recette réelle : cinq motifs, zéro marque intérieure sur le film, fond du conteneur
  transparent, quatre couches sélectionnables à la souris, au clavier et au toucher.
- Silhouettes couleur / blanc / poudre identiques à l’arrondi SVG près : moins de
  0,03 unité SVG d’écart mesuré sur leurs boîtes. Ce n’est pas une tolérance de production.
- **646 grains** représentés, tous leurs centres dans les silhouettes après projection.
  Une petite marge graphique intérieure garde les grains hors du bord arrondi du dessin.
- Le contrôle de survol vise le cœur opaque du grand motif de chaque couche ; le centre
  global de la planche contient maintenant des espaces transparents et n’est plus un
  point de contrôle représentatif de la couche supérieure.
- Nouveau SVG statique chargé en HTTP 200 sans JavaScript, références locales et cinq motifs.
- Captures finales desktop, tactile, couches et repli statique examinées.
- Aucun débordement à 375, 390, 768, 1024 et 1440 px ; aucune erreur JS dans la recette.
- Détection Impeccable ciblée et lint Taste : aucun échec ; syntaxe JS, Ruff et diff vérifiés.
- Six services Docker sains. Aucun changement de prix, accès, compte ou règle métier.

La géométrie et les couleurs restent une démonstration illustrative. Les épaisseurs
et les séparations sont exagérées pour la lecture. Les photographies réelles de la
landing restent à fournir ; leurs douze emplacements ne sont pas modifiés.

Artefacts locaux : `output/playwright/hero-sheet/`. Le HTML autonome du banc et ses
planches permettent de rejouer l’illustration sans modifier les fichiers du moteur.

