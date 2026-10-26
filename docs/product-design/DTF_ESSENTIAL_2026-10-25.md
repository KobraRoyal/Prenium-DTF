# Landing DTF — lecture essentielle, 25 octobre 2026

## Intention

Rendre l’offre immédiatement compréhensible pour un professionnel qui cherche un DTF de qualité. Garder la marque crème/corail, les polices locales et le transfert Hairline. Le repère Odoo demandé sert à la simplicité de lecture ; son URL française a renvoyé un refus 403 dans Chrome et un délai dépassé lors de la consultation web. Aucun asset Odoo n’est repris.

Skills appliqués : Impeccable (distill, clarify, contrôle borné), Taste (direction existante, vérification navigateur). La géométrie Hairline, son moteur et les interactions de décomposition restent inchangés.

## Messages et progression

- Hero : « Le DTF des pros. » Qualité, impression 8 couleurs, préparation pour le textile. Action principale : demander un accès ; action secondaire : voir les tarifs.
- Résultats : cinq photos prévues dans une bande horizontale, sans agrandir artificiellement des images absentes.
- Couleurs : gamme CMJN + orange, vert, rouge et bleu. Démonstration de principe conservée.
- Préparation : trois étapes, une photo et une explication par vue. Vérifier le fichier ; adapter le blanc ; préparer l’adhérence. Les outils de simulation se trouvent dans le volet « Explorer la préparation en détail ».
- Atelier : localisation près de Rennes et livraison en France.
- Commande : composition selon le besoin, avec limites utiles du Studio explicites. Parcours selon le compte ; comptant par Gang Sheet.
- Tarifs : volume mensuel réalisé, simulation estimative et conditions réelles conservées.

## Affirmations et limites

L’utilisateur a confirmé que les encres DTF sont certifiées OEKO‑TEX®. La mention est limitée aux encres couleur et blanche, sans numéro, standard précis, logo, ni certification du transfert ou du vêtement fini. La référence documentaire du certificat reste à archiver lorsqu’elle sera fournie.

Le second « vert » dans la liste demandée est interprété comme « bleu », conformément à la configuration huit couleurs déjà précisée. Aucun changement de configuration machine.

Film PET double face, pelable à chaud, laize maximale 56 cm : information métier fournie par l’utilisateur. La largeur utile de composition et de facturation reste issue de la configuration (55 cm lors de la validation). Ne pas confondre laize du film et surface utile.

Le blanc est préparé selon le visuel et la couleur du textile. La poudre premium est présentée comme un matériau sélectionné pour la tenue au lavage, sans comparaison chiffrée ni promesse universelle. Les consignes de pose et d’entretien restent nécessaires.

Les prix et paliers proviennent de la base par défaut. Le coût éventuel de traitement de fichiers non conformes de 6 € HT reste visible. Aucun tarif ni donnée de catalogue n’a été modifié dans ce lot.

## Photographies et fonctionnement

Douze emplacements identifiés : résultats 5, couleur 1, préparation 3, atelier 2, conditionnement 1. Le poudrage passe de la rubrique atelier au carrousel de préparation. Les emplacements sont des éléments HTML légendés, sans image vide ni action d’agrandissement factice. Les deux captures réelles du portail avec données fictives sont conservées.

Le carrousel utilise le défilement natif et le scroll snap. Flèches, sélection d’étape, compteur, clavier gauche/droite/début/fin et tactile. Pas de rotation automatique. Sans JavaScript, les trois vues restent parcourables horizontalement. En mouvement réduit, la sélection est immédiate. Aucun moteur de rendu ou dépendance supplémentaire.

## Validation

Résultats et réserves du contrôle final consignés à la fin du document.

- 135 tests Python réussis (UI et offre publique), puis 18 tests ciblés réussis après la dernière correction de texte.
- 13 tests JavaScript existants réussis : tarification, entrées et orchestration des scènes.
- Recette Chrome réelle : carrousel (sélection rapide, bornes, clavier, redimensionnement, toucher, défilement natif, mouvement réduit et sans JS), 4 couches Hairline à la souris et au toucher, gamut animé, captures du portail, FAQ, outils techniques et liens profonds.
- Douze réservations photo conservées ; aucune image initiale sans source, aucune action sur une photo absente. Le lecteur photo a été vérifié avec deux sources injectées uniquement dans la recette.
- Aucun débordement de page à 375, 390, 768, 1024 et 1440 px. Aucune erreur JavaScript dans les recettes.
- Contrôle visuel borné : un lot desktop/tablette/mobile, correction des indices décoratifs et des questions trop longues, puis confirmation. Dix captures finales examinées, aucun FAIL Taste.
- Avertissements conservés et motivés : crème de marque demandé ; tailles typographiques héritées de composants et labels ; aucune vidéo réelle disponible ; défilement horizontal volontaire des carrousels, avec commandes ou amorce visuelle et clavier ; petit texte interne au SVG technique ; mesure « empty-middle » incluant les diapositives hors champ, sans vide constaté dans les vues visibles.
- Les exceptions Taste `few-pictures` et `eyebrow` restent celles du lot précédent : photos réelles indisponibles confirmées par l’utilisateur, bandeau demandé. Aucune nouvelle suppression Impeccable. Le signalement antérieur `broken-image` reste corrigé par la création différée d’une image pourvue d’une source ; aucune exception n’a été ajoutée.
- Collecte des statiques et redémarrage local effectués ; six services Docker sains. Pas de mesure FPS ou de nouveau score Lighthouse revendiqué.

Preuves locales non versionnées : `.taste-skill/essential-final/report.json`, dix captures dans ce même dossier ; `output/playwright/hyperframes/regressions.json` ; `output/playwright/editorial/browser-report.json`. Les scripts de recette de ces dossiers ont été adaptés au volet technique désormais fermé par défaut.

## Suivi — suppression des petites notes redondantes

À la demande de l’utilisateur, la légende détaillée sous le transfert Hairline, le résumé du montage, les consignes visuelles répétées et la mention B2B répétée sous le CTA ont été retirés. Les quatre commandes de couche restent visibles ; l’explication apparaît uniquement dans l’infobulle sélectionnée. Sur mobile, cette explication suit les boutons et son espace se replie au repos.

Les légendes de photos en attente ne s’affichent plus : le cadre conserve son titre et « Photo à venir ». Une vraie photo fournie conserve sa légende et son lecteur. La légende répétitive du gamut devient une annonce accessible des changements de mode ; les notes comparatives et les répétitions du carrousel sont retirées. Les simulations techniques partagent une seule mention illustrative. Les captures du portail gardent une courte mention « Capture de démonstration ».

Les montants HT, la grille, les conditions de remise, le traitement éventuel de 6 € HT et la certification des encres sont conservés. Les annonces du simulateur restent accessibles au lecteur d’écran. Aucune suppression générale des petits textes ou de leurs styles : les libellés fonctionnels, statuts et informations utiles restent présents.

Validation : 26 tests Python ciblés réussis ; recette Hairline souris/clavier/tactile et mode réduit réussie, aucun débordement à 375/390/768/1024/1440 px et aucune erreur navigateur. Vues du hero vérifiées à 1440/768/390 px ; gamut et carrousel de préparation examinés. Le montage n’a pas été redessiné. Preuves : `output/playwright/notes/report.json` et captures adjacentes. Collecte des statiques et redémarrage local effectués.
