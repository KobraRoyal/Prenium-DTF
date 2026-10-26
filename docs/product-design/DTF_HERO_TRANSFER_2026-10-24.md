# Hero DTF — film interactif et gamut étendu

## Direction demandée

La figure Hairline devient le visuel du hero. L’illustration statique et la section
d’anatomie séparée sont remplacées par un seul transfert interactif : couches proches
au repos, séparation au survol, informations propres à chaque matière.

La figure représente une feuille PET fine, avec réflexion discrète et bord légèrement
relevé. Le motif floral, sa base blanche et la poudre suivent la même silhouette.
L’ordre reste film → couleur → blanc → poudre avant pose. La vue est schématique et
en transparence : blanc et poudre sont atténués au repos pour laisser lire le motif.
Les épaisseurs sont exagérées et la légende l’indique.

## Mouvement et interaction

- Moment central : le transfert s’ouvre au survol, sans ouverture automatique au défilement.
- Continuité : séparation progressive depuis la couche choisie ; retour compact au départ
  du pointeur. Les zones de détection utilisent les silhouettes de destination fixes.
- Informations : une infobulle survolable pour PET, couleur, blanc ou poudre. Les quatre
  boutons donnent aussi un accès direct, au toucher et au clavier.
- Fermeture : bouton « Refermer », Échap, ou sortie du pointeur. Entrée/Espace explorent
  le visuel et les flèches permettent de parcourir les boutons.
- Mobile : les informations occupent une zone réservée pour ne pas déplacer les commandes.
- Budget : noyau Hairline inchangé, un seul ordonnanceur, ressorts bornés, tweens et sommeil
  au repos/hors champ. Le mouvement réduit conserve les états sans déplacement animé.

La géométrie reste dans `dtf-transfer.js`, les matières dans la feuille de style et le
contrôleur accessible dans `dtf-landing.js`. Les couleurs et la vue en transparence
répondent au brief utilisateur ; elles dépassent volontairement le rendu monochrome
du banc Hairline. Le noyau et le banc de contrôle ne sont pas modifiés.

## Schéma des huit couleurs

La section reprend « 8 couleurs. Plus de nuances. ». Un diagramme chromatique remplace
le second motif floral. Deux commandes montrent la base CMJN puis les encres orange,
vert, rouge et bleu. Les deux contours sont des constructions pédagogiques, sans axes
colorimétriques, valeurs Lab, pourcentage de couverture ni comparaison de production.
La légende indique explicitement qu’il ne s’agit pas d’un gamut mesuré.

Sources techniques consultées le 24 octobre 2026 :

- [Fogra — recherche sur l’impression multiprimaire](https://fogra.org/en/research/prepress-technology/multiprimary-printing-13003) :
  la caractérisation et la préparation multicolores conditionnent un rendu prévisible.
- [Fogra — données de caractérisation](https://fogra.org/en/downloads/work-tools/characterisation-data) :
  les données relient les commandes d’un procédé aux couleurs mesurées.
- [ICC — caractérisations CMJN](https://registry.color.org/cmyk-registry/) : référence
  méthodologique pour distinguer un schéma d’une caractérisation colorimétrique.

Ces sources n’attestent ni une mesure ni une certification du procédé IDS.Supply. La
configuration à huit encres reprend le brief existant ; aucun résultat chiffré ajouté.

## Validation

- 196 tests serveur/UI et 4 tests de calcul JavaScript réussis.
- Contrats UI : une seule figure, incluse dans le hero ; identifiants uniques et légende
  du diagramme honnête.
- Validateur Hairline réussi : noyau/banc intacts, géométrie dans le cadre, pointeur stable,
  lecture et console sans erreur. Planche des huit états et planche de mouvement examinées.
- Recette navigateur réussie : quatre matières survolées, infobulles survolables,
  réassemblage au départ, clavier, Échap et fermeture tactile. Le contrôle du film porte
  sur sa zone visible, hors du motif qui le recouvre.
- Contrôles mobiles stables avant/après sélection et infobulles contenues dans leur espace.
  Aucun débordement à 375, 390, 768, 1024 et 1440 px ; aucune erreur JavaScript.
- Deux modes du gamut et exploration avec mouvement réduit validés.
- Lighthouse mobile local : performance 99, accessibilité automatisée 100, SEO 100 ;
  LCP 2,0 s, TBT 0 ms, CLS 0. Mesure locale, sans garantie en production ni audit WCAG exhaustif.
- Artefacts de recette locale : `output/playwright/dtf-hero-*`, `dtf-gamut-*` et
  `hairline-dtf-transfer-*`.
