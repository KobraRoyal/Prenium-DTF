# Landing DTF — clarté métier et sobriété visuelle

## Intention

Passe demandée par l’utilisateur après la rédaction marketing : une offre immédiatement
compréhensible, un ton professionnel, des visuels explicatifs, sans fioritures.
Le parcours reste destiné à un acheteur B2B qui souhaite comprendre le service puis
demander son accès. La marque, les parcours, les tarifs et les conditions sont conservés.

## Rédaction et hiérarchie

- Le titre « Votre DTF au mètre » nomme le produit vendu. La phrase suivante expose
  les deux services : impression 8 couleurs et contrôle des fichiers.
- Les titres décrivent le sujet : couches du transfert, vérification des fichiers,
  renfort local, contours, transparences, modes de commande et tarifs.
- Suppression des formules génériques sur la précision, l’expression et l’accompagnement
  qui répétaient le même bénéfice. Les termes techniques sont expliqués dans leur contexte.
- Les noms des huit encres sont écrits en entier. Les trois états de contour distinguent
  blanc qui dépasse, blanc en retrait et contour couleur adapté au textile.
- Les frais conditionnels de 6 € HT restent visibles. Les règles et limites de commande
  ainsi que les conditions des remises restent disponibles au même endroit.

## Visuels

- L’animation Hairline et l’ordre film → couleur → blanc → poudre sont conservés.
  Retrait des repères de cadrage, du slogan décoratif et du mouvement du hero au pointeur.
- Le contrôle du fichier montre trois zones identifiées sur un motif : trait, ombre,
  contour. Les boutons portent le nom du point observé et exposent leur état.
- Le comparateur de détail montre un dessin commun aux deux vues. Seule une nervure
  reçoit un renfort ; contours, lettrage et proportions restent identiques.
- La carte d’opacité utilise le même motif que la vue couleur, avec gris correspondant
  aux opacités. La préparation illustrative montre des points opaques de tailles
  différentes, plutôt qu’un simple fondu du motif imprimé.
- La trame est une explication graphique, pas la sortie d’un algorithme de production.
  Elle ne constitue ni une promesse de reproduction parfaite ni un résultat imprimé.
- Galerie simplifiée en six emplacements réguliers. Les photos réelles restent à fournir,
  conformément à l’instruction utilisateur. Les deux captures du portail sont conservées.

## Périmètre et hypothèses

Templates `shop/partials/dtf/`, styles et interactions propres à la landing. Aucune
modification de modèle, de base de données, de permission, de facturation ou de fichier client.
Les caractéristiques commerciales restent celles documentées dans les deux passes
précédentes ; aucune certification, durée de vie ni promesse de délai n’a été ajoutée.

## Validation

- 196 tests serveur/UI réussis, dont un contrôle du renfort limité à un seul trait.
- 4 tests JavaScript de calcul tarifaire réussis ; vérification syntaxique et Ruff réussis.
- Recette bureau/mobile : hotspots, comparaison, textile, blanc, opacité et trame fonctionnels.
- Confirmation clavier et contexte mobile tactile : contrôle des zones, opacité, trame,
  comparateur et ouverture/zoom des captures validés.
- Aucun débordement aux largeurs 375, 390, 768, 1024 et 1440 px ; aucune erreur JavaScript.
- Lighthouse mobile local : performance 99, accessibilité automatisée 100, SEO 100 ;
  LCP 2,0 s, TBT 0 ms, CLS 0. Aucun échec sur les noms accessibles des contrôles.
  Cette mesure locale ne constitue pas un audit WCAG exhaustif ni une garantie en production.
- Le détecteur Impeccable ne signale que l’animation de `stroke-width` SVG, interprétée
  comme une largeur de layout. Il s’agit d’un changement géométrique du contour illustré.
- Artefacts locaux : `output/playwright/dtf-clarity-*`.
