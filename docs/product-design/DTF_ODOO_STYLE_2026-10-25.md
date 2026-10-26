# Composition inspirée d’Odoo — 25 octobre 2026

## Direction

La demande porte sur le style de https://www.odoo.com/fr_FR en préservant les couleurs actuelles. La page française et Chrome ont renvoyé une erreur d’accès ; le HTML public de la racine anglaise a pu être lu, ainsi qu’une capture publique de la page d’accueil. Référence observée : grande typographie manuscrite, accroche centrée, mise en valeur ponctuelle, deux actions simples, sections aérées et médias lisibles.

La landing adopte cette composition avec son fond crème, son corail et ses tons existants. Le surlignage corail dans le titre reprend l’intention de la référence explicitement demandée. Aucun dessin, logo, texte commercial ou actif Odoo n’est incorporé.

La police Caveat variable, sous licence SIL OFL, est hébergée localement et réservée aux h1/h2. Les textes, contrôles et sous-titres restent en DM Sans ; le logo conserve sa typographie de marque. Les deux fichiers latin/latin étendu et leur licence sont dans `backend/static_src/fonts/caveat/`. Source de la police : Google Fonts (fonts.googleapis.com / fonts.gstatic.com), licence issue du dépôt officiel google/fonts/ofl/caveat.

## Composition et parcours

Le hero devient vertical : titre, promesse, actions, transfert interactif centré. Le fond de l’animation reste transparent, son contenu et sa géométrie Hairline restent inchangés. Les introductions des sections sont centrées au-dessus de leurs contenus. Les sections de couleur, de préparation et d’atelier conservent des compositions avec visuels pour varier la lecture.

Les cadres photo et médias ont des angles doux. La commande présente deux sélecteurs compacts au-dessus des captures réelles. La FAQ se lit dans une seule colonne. Les tarifs conservent les données et règles existantes. Aucun petit texte supprimé au lot précédent n’est réintroduit.

Les animations, leur pause hors écran, le mode réduit, les commandes accessibles et les emplacements photo explicites sont conservés.

## Validation

Résultats à compléter après la recette et le contrôle visuel borné.

### Résultat du contrôle

- 31 tests Python ciblés réussis : contenu, marque, accès, checkout public et offre tarifaire.
- Recette navigateur finale réussie : quatre couches Hairline à la souris, au clavier et au toucher ; carrousel de préparation ; gamut, pause/reprise, interruption hors écran ; menu mobile ; captures agrandies et zoom ; FAQ native ; mouvement réduit et consultation sans JavaScript.
- Les panneaux de commande gardent une hauteur stable lors des changements de mode (224 px sur la largeur mobile de recette).
- Aucun débordement à 375, 390, 768, 1024 et 1440 px. Huit h2 visibles tenant au maximum sur deux lignes. Police Caveat chargée localement.
- Couleurs avant/après identiques : #f4f0e6 / #fbf6ee / #fffdf8 / #FF8775 / #FFEAE3 / #1a1815. Le hero passe de deux colonnes à une colonne centrée ; l’animation reste en aval des actions dans l’ordre de lecture et de focus.
- Un lot d’inspection desktop/tablette/mobile, correction de la galerie pour présenter des photos entières, puis confirmation : dix captures finales examinées, zéro FAIL Taste. Scan Impeccable layout vide, aucune règle masquée.
- Avertissements conservés avec explication : crème demandé par l’utilisateur ; trois polices en comptant le logo et les repères techniques Space Grotesk préservés ; échelle de taille incluant contrôles, données de prix et SVG ; absence de vidéo réelle ; deux défilements horizontaux fonctionnels ; petit texte interne au SVG ; mesures d’alignement/centre incluant des diapositives hors champ. Les seules exceptions d’inspection restent `few-pictures` et `eyebrow`, déjà documentées pour les photos indisponibles et le bandeau demandé.
- Les images en attente restent explicitement réservées, sans fausse photo de production. Les petites notes supprimées ne sont pas revenues. Aucune modification de permission, de donnée, de prix ou de destination de commande.

Preuves locales non versionnées : `.taste-skill/odoo-style-final/report.json` et dix vues ; `output/playwright/odoo-style/before.json`, `proof.json` ; `output/playwright/hyperframes/regressions.json`. Le script de recette sans JavaScript vérifie désormais le CTA du hero à la place de la note B2B supprimée à la demande précédente.

Sources de référence : [accueil Odoo](https://www.odoo.com/), [capture publique de l’accueil consultée](https://www.toolworthy.ai/tool/odoo-accounting), [police et licence Caveat](https://github.com/google/fonts/tree/main/ofl/caveat). La capture est utilisée seulement pour l’étude visuelle et n’est pas intégrée au site.
