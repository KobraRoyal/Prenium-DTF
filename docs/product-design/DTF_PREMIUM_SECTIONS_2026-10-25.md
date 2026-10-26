# Sections de landing — passe Impeccable du 25 octobre 2026

## Intention

Étendre le niveau de soin du hero aux sections suivantes : discours commercial B2B, hiérarchie claire, lecture plus courte et commandes explicites. Le hero « Votre DTF. Notre exigence. », Hairline, la palette et les moteurs d’interaction restent inchangés.

Impeccable est appliqué en mode **Persuade**, avec ses références `clarify`, `polish` et `craft-floor`. Le contexte produit et le design existants sont conservés. Une revue rédactionnelle en lecture seule a été confiée à l’agent UI ; la racine possède et intègre tous les fichiers modifiés. Le graphe est absent : aucune indexation n’est lancée.

## Récit et wording

Le parcours commence désormais par les éléments disponibles pour décider : **hero → commande → budget → résultats → couleurs → préparation → atelier → FAQ → accès**. Les alias d’ancres sont conservés près des sections correspondantes.

| Section | Titre livré | Rôle |
| --- | --- | --- |
| Commande | Commandez à votre façon. | Distinguer le dépôt de visuels de la composition dans le Studio. |
| Par fichier | Chaque visuel, bien cadré. | Expliquer dimensions, quantités et couleur du support. |
| Gang Sheet | Votre planche. À votre main. | Présenter la composition libre dans les limites utiles du Studio. |
| Budget | Votre budget, en clair. | Rendre visibles le prix au mètre, les remises et les exclusions. |
| Résultats | Du motif au textile. | Introduire les réalisations prévues, sans prétendre montrer des photos absentes. |
| Couleurs | 8 encres. Plus de nuances. | Relier les encres complémentaires aux aplats, dégradés et illustrations. |
| Préparation | Le soin commence dans le fichier. | Rendre le contrôle et la préparation utiles au professionnel. |
| Atelier | Imprimé près de Rennes. | Situer la fabrication et le suivi jusqu’au conditionnement. |
| FAQ | Avant de commander. | Répondre aux questions qui précèdent la première commande. |
| Final | Votre première commande. | Inviter à demander un accès avec validation préalable du compte. |

Les trois étapes de préparation deviennent : **Contrôler avant d’imprimer**, **Le blanc adapté à votre textile**, **Préparer l’adhérence**. Les démonstrations techniques restent dans un disclosure nommé « Voir les contrôles de préparation ».

La FAQ reformule les huit questions et explicite la différence entre encours et comptant. Les certificats restent attachés aux encres couleur et blanche. Aucun délai, garantie, témoignage ou traitement gratuit n’a été ajouté.

## Composition

- Introductions en deux colonnes sur desktop, empilées sur téléphone ; titre et bénéfice se lisent ensemble.
- Commande : texte d’usage et capture du portail côte à côte sur grand écran, puis lecture verticale. Le bouton d’agrandissement reste visible sous la capture sur téléphone.
- Le panneau actif de commande est contrasté. L’action répétée de demande d’accès sous la démonstration est remplacée par « Estimer mon budget ».
- Budget : contrôle et résultat forment deux zones distinctes. La largeur d’impression et les exclusions figurent à côté du prix. Une requête de conteneur organise les paliers en deux ou quatre colonnes selon leur place disponible ; aucun dernier palier n’occupe seul une rangée disproportionnée.
- Les douze réservations photo restent explicites et non interactives. Leur hauteur est réduite pour ne pas occuper l’essentiel du récit. Les futures vraies photos conservent leur ratio et l’agrandissement existants.
- Couleurs : le texte précède le diagramme dans le DOM et dans la lecture mobile. Les contrôles, l’animation et la certification sont conservés.
- Atelier : texte à gauche, deux emplacements de fabrication à droite ; empilement mobile.
- FAQ : introduction latérale sur desktop, suivie des accordéons sur téléphone. Les questions sont lisibles, tactiles et nommées.
- Final : promesse et prochaine étape sont rapprochées du bouton, avec une disposition horizontale sur desktop et verticale sur téléphone.

Les espacements entre sections sont réduits sans retirer de conditions utiles. Sur desktop à 1440 px, la section commande passe d’environ **1 944 à 1 225 px** et la galerie d’environ **1 022 à 681 px** dans les états examinés. Ces mesures de composition ne sont pas une prédiction de conversion.

## Fichiers

- Templates : `home.html`, puis `dtf/ordering.html`, `pricing.html`, `gallery.html`, `gamut.html`, `analysis.html`, `preparation_carousel.html`, `expertise.html`, `faq.html`, `final.html`.
- Styles : `backend/static_src/css/components/dtf-editorial.css`, chargée en version `20261025-sections-2`.
- Tests : `tests/ui/test_dtf_marketing_content.py` et `tests/ui/test_landing_editorial_redesign.py`.
- Documentation : ce document, l’index de conception, `DESIGN.md` et la checklist du lot 11.10.

Aucun modèle, service métier, route, contrôle d’accès, calcul tarifaire ou traitement de fichiers n’est modifié.

## Recette

- [x] **42 tests Python réussis**, dont les contrats de prix publics, de marque, d’accès, de récit et de médias honnêtes.
- [x] **17 tests JavaScript réussis** pour les moteurs existants de mouvement, scènes, galerie et prix.
- [x] Ruff ciblé et `git diff --check` sans erreur.
- [x] Dix largeurs : **320, 375, 390, 600, 601, 768, 820, 821, 1024, 1440 px**, sans débordement global.
- [x] Titres principaux et titres visibles des modes de commande : **deux lignes au maximum** aux largeurs examinées.
- [x] Onglets de commande et agrandissement du Studio exercés ; fermeture du dialogue au clavier et au toucher.
- [x] Galerie : dernière vue atteinte au clavier, compteur **5 / 5** sur téléphone.
- [x] Préparation : dernière étape atteinte, compteur **3 / 3** ; vrai tap mobile vers la seconde étape.
- [x] Démonstrations avancées ouvertes à 320 px sans débordement.
- [x] FAQ native : une question ouverte à la fois ; toutes les ancres internes ont une cible.
- [x] Gamut : sélection des modes fonctionnelle, y compris en mouvement réduit.
- [x] Simulateur vérifié après stabilisation de ses compteurs animés : **10 m → 11,00 € HT/m et 110,00 € HT** dans la configuration locale.
- [x] Sans JavaScript : 12 réservations photo, 8 questions et lien d’accès final disponibles ; aucun débordement à 390 px.
- [x] Aucune erreur JavaScript relevée pendant les interactions contrôlées.
- [x] Statiques collectés, service local redémarré, six services sains et `/healthz/` en état `ok`.

Un lancement de tests et une inspection ont été interrompus par le redémarrage local ; les résultats ci-dessus proviennent des relances après disponibilité du service. Le rapport d’inspection contenant temporairement la page 502 a été remplacé par celui de la landing.

## Revue visuelle et limites

Deux passes bornées : construction et captures desktop/mobile, puis correction groupée des paliers, d’un titre intermédiaire et de l’ordre du bloc couleurs. La confirmation finale couvre desktop, tablette et téléphone.

Le lint Taste des sources indique **0 FAIL et 1 WARN**, sur le contour des boutons de navigation du carrousel. Ce contour matérialise une commande tactile existante. Les hooks Impeccable ne signalent pas d’anomalie déterministe sur les fichiers traités.

L’inspection Taste de page entière conserve **2 FAIL et 6 WARN** : bandeau d’origine interprété comme surtitre, manque de photos, conventions de palette et typographies, diversité des tailles, absence de vidéo et carrousels hors champ. Ces résultats restent distingués de la recette fonctionnelle. La palette, le bandeau et les carrousels sont conservés ; l’absence de photos de production reste une réserve réelle avant publication.

Les captures de section entière peuvent inclure le header fixe au milieu d’une image longue. Le diagnostic de débordement et de titres repose également sur leurs dimensions réelles dans les viewports.

### Lecture finale

- Élément dominant : le choix de commande et sa capture réelle, puis le budget.
- Idée : montrer comment le soin des fichiers se traduit dans la façon de commander, les couleurs et les étapes de préparation.
- Interaction utile : modes de commande et simulateur ; les démonstrations approfondissent ensuite la preuve.
- Les douze photos en attente empêchent toujours de présenter la page comme une preuve photographique complète de production.

## Livrables locaux

Dans `output/playwright/` :

- `dtf-sections-final-{desktop,tablet,mobile}-{commander,tarifs,couleurs}.png`.
- `dtf-sections-r1-{desktop,mobile}-sheet-{1,2}.jpg`, première revue de toutes les sections.
- `dtf-sections-final-inspection/report.json` et planches finales des trois formats.

Pas de déploiement distant. Les photos et les conditions commerciales encore absentes restent à fournir avant publication.
