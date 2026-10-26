# Passe Impeccable — corrections UI, 25 octobre 2026

## Périmètre

Corriger les défauts de la landing existante en préservant son style inspiré d’Odoo, la palette, les textes commerciaux et Hairline. Lecture du playbook Polish, diagnostic technique Audit et contrôle réel de la page. Aucun backlog de critique enregistré n’était disponible pour cette URL. Le détecteur initial ne signale aucun défaut déterministe ; les problèmes ci-dessous viennent de la vérification des usages et des dimensions réelles.

## Défauts traités

- P2 — Galerie sans commande visible : seuls le défilement natif et le clavier permettaient d’atteindre les cinq vues. Ajout de flèches, d’un compteur et de commandes clavier début/fin/gauche/droite. Deux photos sur grand écran, une sur mobile ; dernières vues accessibles malgré le nombre impair de photos. Les cadres restent des photos en attente ; les flèches parcourent les cadres et n’ouvrent pas un média factice.
- P2 — Couleur textile sélectionnée invisible : le pseudo-élément ne définissait aucune bordure, malgré le changement de couleur prévu pour l’état actif. Bordure et anneau de sélection explicites, avec cibles tactiles de 44 px et champ de couleur agrandi. Les curseurs de comparaison et de volume reçoivent la même hauteur de cible.
- P1 — Analyse rognée à 320 px : la taille minimale intrinsèque de la grille et des onglets dépassait le panneau, dont l’overflow caché masquait le défaut. Colonnes à minimum nul, enfants rétractables, atelier d’analyse empilé sur tablette et onglets en pile sur petits écrans. Aucun masquage ajouté pour cacher du contenu.

La navigation visuelle des carrousels préparation et galerie partage les mêmes styles. Le nouveau contrôleur photo ne tourne pas au repos et utilise le défilement natif ; pas de lecture automatique. Sans JavaScript, le défilement natif reste disponible.

## Diagnostic initial

À 320 px, un panneau d’analyse s’étendait jusqu’à 339,94 px alors que le document ne déclarait aucun débordement. Les autres largeurs testées : 375, 390, 600, 768, 820, 821, 900, 1024 et 1440 px.

Axe, règles WCAG A/AA, WCAG 2.1 AA et bonnes pratiques : zéro violation automatique aux largeurs 1440/768/390/320, dans les états fermé et ouvert. Des vérifications manuelles restent nécessaires pour les contrastes des SVG et certaines associations ARIA signalées comme indéterminées ; ce résultat ne vaut pas certification d’accessibilité.

## Validation

Les résultats de la recette et de la confirmation visuelle sont consignés ci-dessous.

### Résultat final

- Trois défauts visuels/fonctionnels corrigés, avec ajustement des cibles tactiles. Relecture supplémentaire des résultats Axe : trois groupes nommés sans rôle sémantique explicite ; ajout de `role="group"` aux encres, à la piste de préparation et aux paliers de remise pour que leurs noms soient reconnus.
- 29 tests Python ciblés réussis après correction ARIA ; le test des groupes nommés couvre explicitement les cas avec et sans grille tarifaire configurée dans la base de test. Quatre tests JavaScript durables couvrent la galerie (nombre impair, bornes, clavier, redimensionnement, navigation rapide, défilement manuel et préférence de mouvement) ; 17 tests JS au total réussis.
- Recette Chrome réelle : cinq vues de galerie atteignables, bornes correctes, clavier début/fin/gauche/droite, toucher, changement de préférence et fonctionnement natif sans JavaScript. La préparation, les menus, la FAQ, les captures de commande et les quatre couches Hairline passent aussi leurs recettes.
- Dix largeurs de 320 à 1440 px : aucun débordement du document ni rognage des enfants du panneau d’analyse ; pastilles et curseurs mesurés à 44 px.
- Contrôle Axe après correction visuelle, y compris textile blanc et panneau ouvert : aucune violation automatique à 1440/768/390/320 px. La revue manuelle des contrastes indéterminés concerne le marqueur du titre, des libellés SVG sur image/gradient, des symboles décoratifs masqués et les vues hors champ du carrousel. Ces signalements ne sont pas masqués.
- Huit vues de confirmation de la galerie et de l’analyse examinées, plus la sélection textile sur mobile. Aucune nouvelle identité ou affirmation commerciale. Aucune suppression de règle Impeccable ; détecteur sans finding. Pas de nouvelle photo fictive.

Preuves locales non versionnées : `output/playwright/impeccable-fix/audit-before.json`, `report-after.json`, `manual-review.json` et captures adjacentes ; `output/playwright/hyperframes/regressions.json`. Les captures ont été regroupées avant/après ; aucune nouvelle boucle de refonte.


### Clôture après reprise

Le dernier test supposait à tort la présence d’un catalogue DTF dans tous les cas. Le scénario configure maintenant explicitement la base de test : les groupes des encres et de la préparation existent toujours ; celui des remises existe uniquement lorsque le simulateur est disponible. Aucune donnée locale réelle n’a été modifiée.

Contrôle navigateur final des corrections sémantiques : trois groupes nommés reconnus, aucune violation automatique et aucun signalement `aria-prohibited-attr` restant. Seules les vérifications manuelles de contraste sur les illustrations et éléments hors champ restent indéterminées pour Axe ; elles sont documentées ci-dessus. Preuve : `output/playwright/impeccable-fix/semantics-final.json`. Les autres vérifications visuelles et fonctionnelles déjà réalisées restent valides ; pas de nouvelle modification visuelle lors de la reprise.
