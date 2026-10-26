# Landing Prenium DTF — rédaction, preuve produit et FAQ

## Objectif

Resserrer le discours pour un acheteur professionnel : comprendre l’offre, voir comment
commander, lever les objections, demander un accès. Le travail conserve l’identité
Prenium DTF By IDS.Supply et les démonstrations matière de la passe précédente.

## Analyse des références

Références consultées le 24 octobre 2026 :

- [Offre transfert DTF Sherpa](https://www.sherpa-transfert.com/collections/transfert-dtf) :
  hiérarchie des modes de commande, présentation des bénéfices et questions pratiques.
- [Guide DTF Sherpa](https://www.sherpa-transfert.com/pages/qu-est-ce-que-le-dtf) :
  pédagogie du procédé et aide au choix selon le besoin textile.

Lecture éditoriale retenue : les modes de commande et les réponses opérationnelles
méritent une place immédiatement identifiable. La nouvelle rédaction donne une fonction
à chaque section : matière, couleur, contrôle du fichier, commande, prix, atelier, FAQ.
Les textes sont originaux. Certifications, volumes, délais garantis et résultats de
lavage annoncés par un concurrent ne constituent pas des preuves pour IDS.Supply.

Les mentions « Fabriqué en Bretagne, près de Rennes », service professionnel et livraison
partout en France viennent directement des instructions utilisateur. Elles ne désignent
pas une certification ni une origine française des encres ou consommables.

## Contenu et conversion

- Hero : bénéfice de la couleur et de la préparation, puis cible professionnelle.
- Anatomie : rôle de chaque matière, sans répéter l’argumentaire du gamut.
- Préparation : une démonstration par sujet, avec limites techniques courtes et visibles.
- Commande : deux parcours illustrés par l’interface réelle et un CTA d’accès cohérent.
- Prix : montant et simulateur conservés ; détails en disclosure native. La mention
  conditionnelle des 6 € HT reste visible hors du disclosure.
- Atelier : ancrage breton et accompagnement, avec emplacement photo des machines.
- FAQ : huit réponses concrètes — accès pro, fichiers, parcours, dimensions, couleur
  textile, prix/remises, fabrication/livraison, pose/entretien.
- Conversion finale : prochaine étape explicite pour préparer une série.

Les dimensions affichées restent alimentées par les réglages globaux du Studio. Les
prix restent liés à la grille par défaut en base ; aucune règle de facturation modifiée.
La FAQ recommande PNG transparent ou PDF et 300 dpi à la taille finale, sans prétendre
que seuls ces formats sont acceptés. Aucun nombre de lavages ni délai ferme ajouté.

## Bandeau d’origine

`shop/partials/dtf/marquee.html` affiche fabrication bretonne, cible B2B et livraison
nationale. Une seule copie est exposée aux lecteurs d’écran ; la seconde boucle est
`aria-hidden`. Le bouton permet pause et reprise explicites. L’animation s’arrête hors
champ et dans un onglet caché. En mouvement réduit, le texte est fixe, se replie sur
plusieurs lignes et le bouton de lecture est retiré.

## Captures de la solution

Assets publiés :

- `img/dtf/screens/order-by-file.webp` : 1080 × 478, 52 348 octets ; cadrage du bloc réel
  `#order-project-items`, quantités, couleurs de support et qualité de deux visuels.
- `img/dtf/screens/gang-sheet-studio.webp` : 1360 × 803, 133 124 octets ; cadrage de la
  vraie zone `.gang-editor__workspace`, avec import, composition et contrôle.

Les images proviennent directement de `locator.screenshot` dans le navigateur. Elles
ne redessinent pas l’interface. Les créations « Collection Floraison » et « Logo atelier »,
le compte et les données sont entièrement fictifs. Légendes visibles : données **et
montants** de démonstration. Aucun UUID ni renseignement client réel dans les cadrages.

Le changement de parcours est un tabset accessible au clavier. Chaque capture s’ouvre
dans un dialogue natif, fermable par Échap. Le bouton « Taille réelle » permet le
panoramique natif dans l’image, notamment sur mobile.

Reproduction : `scripts/capture_marketing_demo.py` impose `config.settings.test` puis
SQLite et médias temporaires avant `django.setup()`. Le serveur de capture reste publié
sur l’interface locale de l’hôte, les synchronisations externes sont désactivées, puis
l’environnement temporaire est supprimé après capture. Le compte de démonstration n’est
jamais créé dans la base de développement habituelle.

Une revue indépendante `ids_security_reviewer` n’a relevé aucun finding exploitable sur
l’isolation et le caractère synthétique. Les WebP ne contiennent pas d’EXIF/XMP/IPTC.

## Photographies à compléter

L’utilisateur a confirmé l’indisponibilité actuelle des photos et demandé des placeholders.
Le bloc atelier réserve une image aux machines/à la production ; la galerie garde six
emplacements pour les résultats textile. Ces emplacements sont identifiés. Aucun visuel
concurrent, photo de stock ou image générée n’est présenté comme une production IDS.

## Validation

- 195 tests pytest réussis : UI publique, contrats du portail, lecture publique des tarifs.
- 4 tests JavaScript de calcul réussis.
- Recette navigateur : bandeau pause/reprise et sommeil hors champ, deux modes de commande,
  dialogue, zoom à taille réelle, FAQ native et clavier, conditions tarifaires et frais
  visibles, conservation de l’interaction des couches.
- Aucun échec ni erreur console ; aucun débordement aux largeurs 375, 390, 768, 1024, 1440.
- Mouvement réduit : bandeau fixe, informations visibles, contrôle superflu retiré.
- Contexte mobile tactile (`isMobile`, `hasTouch`) : taps sur pause/reprise, parcours
  Studio, capture, taille réelle, fermeture et FAQ validés ; aucun débordement.
- Lighthouse mobile local : performance 99, accessibilité automatisée 100, SEO 100 ;
  LCP 2,0 s, TBT 0 ms, CLS 0. Mesure de laboratoire, sans garantie de résultat en production.
- Les noms accessibles du logo et des emplacements galerie proviennent de leurs textes
  visibles ; l’aide de destination du logo reste disponible dans son attribut `title`.
- Détecteur Impeccable : source initiale du viewer ajoutée après son signalement. L’alerte
  restante de largeur concerne `stroke-width` SVG et n’anime pas une largeur de layout.
- Captures et rapport de recette locaux : préfixe `dtf-content-` dans `output/playwright/`.
