# Hero commercial et conversion professionnelle — 25 octobre 2026

## Demande et direction retenue

Appliquer le plan issu du benchmark Sherpa avec un hero plus commercial : qualité du DTF, soin du fichier, cible professionnelle et figure Hairline immédiatement visible.

Skills appliqués : Impeccable pour la rédaction et la composition responsive, Taste pour la lecture visuelle et les contrôles, IDS Hub Dev Core et Frontend Stack pour l’intégration. L’entrée HyperFrames a été consultée : la figure web existante est conservée, sans création de film ni nouvelle composition.

La marque existante reste la référence : crème, corail, titres Caveat et texte DM Sans. Cette passe affine le monde visuel existant ; aucune nouvelle direction aléatoire ni image de production n’a été créée.

## Wording livré

> **Votre DTF. Notre exigence.**
>
> Des transferts 8 couleurs pour les professionnels. Vos fichiers contrôlés et préparés pour une impression nette, jusque dans les détails.

Le CTA public devient **« Demander mon accès pro »**, suivi dans le hero de **« Présentez votre entreprise. Commandez après validation de votre compte. »** Le lien secondaire reste **« Simuler mon tarif »**, ou **« Voir les tarifs »** sans grille disponible.

Le texte exprime la qualité par le résultat et le soin prépresse. Il ne promet ni réparation de tout fichier, ni correction gratuite, ni délai ou performance non confirmés. Les frais éventuels de 6 € HT pour les fichiers non conformes restent dans la section tarifaire.

## Composition et parcours

- Desktop et tablette dès 601 px : offre à gauche, figure Hairline à droite, prix et actions regroupés sous le texte.
- Téléphone : titre et bénéfice, figure et commandes matière, puis prix, actions et précision sur l’accès. L’ordre du DOM suit cette lecture ; la figure reste unique.
- La réserve du bouton « Refermer » est repliée au repos et réapparaît à l’ouverture. Les infobulles mobiles restent dans le flux.
- Les contrôles des matières restent accessibles, avec une hauteur minimale de 44 px sur téléphone. « Film PET » tient sur une ligne aux largeurs mobiles usuelles.
- La flèche de prix est conservée ; elle disparaît sous 360 px et sur tablette pour éviter les collisions.
- Les sections suivent désormais : hero → résultats → commande → tarifs → couleurs → préparation → atelier → FAQ → accès.
- Le simulateur donne directement accès au parcours adapté au visiteur, avec un lien distinct pour comparer les modes de commande. Les comptes connectés conservent la destination existante vers leur espace.

Le tarif de base, sa largeur de référence, la dégressivité et les exclusions proviennent toujours du contexte public existant. Aucun calcul ou tarif n’a été modifié. La géométrie Hairline, le moteur, les motifs et les scripts de mouvement sont inchangés.

## Sources modifiées

- `backend/templates/shop/partials/dtf/hero.html` : argument commercial, structure et microcopy.
- `backend/templates/shop/partials/dtf/cta.html` : libellé public cohérent sur la landing.
- `backend/templates/shop/partials/dtf/pricing.html` : action directe après simulation.
- `backend/templates/shop/home.html` : ordre du récit, titre Open Graph et version de la feuille de style.
- `backend/static_src/css/components/dtf-taste.css` : grille, espacement et adaptation du hero.
- Tests UI concernés : récit, marque, accès, contenu marketing et page publique de commande. Aucun changement backend de traitement, de permission ou de données.

## Validation

- **40 tests Python réussis**, couvrant contenu, routes d’accès, ordre des sections et offre publique, dont les montants dynamiques et l’absence de prix négociés dans la page publique.
- **17 tests JavaScript réussis**, couvrant le mouvement, les scènes, la galerie et les calculs de simulation existants.
- Ruff ciblé et `git diff --check` réussis.
- Dix largeurs contrôlées : **320, 375, 390, 600, 601, 768, 820, 821, 1024 et 1440 px** ; aucun débordement global.
- À 390 × 844 px, la figure est entre environ **346 et 546 px**, les commandes matière entre **546 et 590 px**, le CTA entre **714 et 762 px**. À 375 px, le CTA finit vers **759 px** ; à 768 × 900 px, il finit vers **568 px**. Les éléments visés restent visibles dans le premier écran au repos.
- Les quatre couches ont été ouvertes au clavier : Film PET, Couleur, Blanc et Poudre. Sélection et infobulle concordent ; Échap referme la figure.
- Un contexte mobile tactile a ouvert Blanc puis utilisé « Refermer » avec de vrais taps.
- Sans JavaScript, le transfert statique, son explication et le lien d’accès restent disponibles ; aucun débordement à 390 px.
- En mouvement réduit, la sélection d’une couche reste fonctionnelle.
- Le lien vers le simulateur fonctionne ; à 10 m, la grille locale observée affiche 20 % de remise, 11,00 € HT/m et 110,00 € HT. Le CTA de simulation mène directement à la demande d’accès pour un visiteur anonyme.
- Aucune erreur JavaScript relevée pendant les interactions exercées. Les six services Docker sont sains et `/healthz/` répond `ok`.
- Statiques collectés et service web local redémarré. Feuille `dtf-taste.css` versionnée `20261025t` pour éviter la conservation d’un ancien rendu par le cache.

### Contrôles visuels et réserves

Deux passes de composition ont été réalisées : construction puis correction groupée de l’alignement mobile, de la tablette et des commandes matière. Un rechargement avec nouvelle version de CSS a été nécessaire pour vérifier le dernier état.

Le lint source Taste ne relève aucun FAIL ni WARN. Le détecteur Impeccable ne relève pas d’anomalie déterministe dans les sources passées ; il ne résout pas les liens Django `{% static %}` et ne remplace donc pas la recette du rendu.

L’inspection de page entière conserve **2 FAIL et 8 WARN** : un bandeau de fabrication interprété comme surtitre, le manque de photos, les conventions de palette et de polices, la diversité de tailles, l’absence de vidéo, les carrousels et leurs éléments hors champ. Le bandeau, la marque et les carrousels préexistants sont conservés. Le manque de photos est une réserve réelle avant publication ; ces résultats ne sont pas présentés comme une validation automatique complète du premium ou de l’accessibilité.

La doc Impeccable signale aussi une sidecar de design antérieure à `DESIGN.md`. Elle n’a pas été régénérée dans cette passe, conformément à la consigne du skill de ne pas réparer la dérive en effet de bord.

### Critique du rendu final

ROUND 2

Seen in one second: la promesse de soin, puis le transfert imprimé, le prix et l’action corail.

Idea (one sentence): rapprocher le fichier, le transfert et le budget pour rendre le soin de production compréhensible dès le premier écran.

Live thing: exploration des quatre couches Hairline et simulation du volume mensuel.

Layout words by section: hero=grille / résultats=carrousel / commande=onglets / tarifs=simulateur / couleurs=deux colonnes / préparation=carrousel / atelier=deux colonnes / FAQ=accordéons / accès=centré.

Scores: design 6,5 · usability 8 · creativity 7 · content 5 → calcul 6,95 ; score Taste plafonné à 6,0/10 par les FAIL de page entière. Il s’agit d’une note de cette grille, pas d’une mesure de conversion.

Caps applied: photos de production manquantes et placeholders encore présents. Palette, titres et animation sont des contraintes de marque et de demande conservées.

Top three problems (most visible first), each with the screenshot it shows in and the fix:

1. Les réservations photo restent visibles après le hero — planches de page de `dtf-premium-final-inspection` : intégrer les médias de production prévus avant publication.
2. La figure compacte conserve de l’air nécessaire à son ouverture — `dtf-premium-hero-final-390.png` : compromis assumé pour conserver l’ouverture complète de l’animation, les boutons et le CTA dans le premier écran.
3. Délais et éventuel minimum ne sont pas documentés commercialement — FAQ dans les planches de page : compléter seulement à partir de conditions validées.

## Captures locales

Dans `output/playwright/` :

- `dtf-premium-hero-final-1440.png`
- `dtf-premium-hero-final-768.png`
- `dtf-premium-hero-final-390.png`
- `dtf-premium-hairline-open-desktop.png`
- `dtf-premium-hairline-open-mobile.png`
- `dtf-premium-final-inspection/report.json` et planches associées.

Les photos de production restent à fournir. Aucun déploiement distant n’est effectué.
