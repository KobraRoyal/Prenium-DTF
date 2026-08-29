# Sprint 52 — Soulignement animé des actions simples

## Objectif

Harmoniser les actions ghost/tertiaires, les liens d’action contextuels, les contrôles du header, les filtres, les onglets et les navigations de section avec le langage du fil d’Ariane : un trait fin dans la couleur primaire apparaît de gauche à droite au survol et au focus clavier, puis reste visible pour l’état actif, sans modifier les polices ni la hiérarchie des CTA.

Le lot est strictement visuel. Il ne change aucune route, permission, donnée, isolation multi-tenant ou logique métier.

## Livré

- [x] Contrat partagé dans `components/buttons.css` pour `ui-btn-ghost` et son alias Daisy `dui-btn-ghost`.
- [x] Trait basé sur `var(--brand)` afin de suivre l’identité Atelier configurée à l’exécution.
- [x] Actions danger conservées avec un trait `var(--danger)`.
- [x] Header : navigation principale, menus Réglages et Mon compte alignés sur le même mouvement.
- [x] Hiérarchie Atelier simplifiée : « Machines DTF » devient « Parc machine » dans le menu Réglages, tandis que l’entrée inachevée « Identité visuelle » n’est plus exposée dans la navigation.
- [x] Menus flottants « Mon compte » Client/Atelier et « Créer une commande » réunis sous la primitive DRY `product-floating-menu` : même panneau, même rythme, mêmes actions et même réponse clavier/mobile.
- [x] Hiérarchie des popovers affinée sans changer les polices : identité compacte, aide de création explicite, icônes partagées et sortie danger isolée.
- [x] Famille d’icônes « Mon compte » redessinée en SVG ligne arrondie de 20 px : édition du profil, équipe, atelier et déconnexion utilisent la même géométrie et des teintes sémantiques issues du thème.
- [x] Entrée courte du panneau et micro-mouvement des actions neutralisés par `prefers-reduced-motion`.
- [x] Primitive DRY `ui-selection-control` / `ui-selection-rail--horizontal` pour les filtres, onglets et navigations de section Client/Atelier, avec cible tactile horizontale commune de 44 px.
- [x] États actifs indiqués par un trait primaire persistant et un texte renforcé, sans fond rempli ni forme pill.
- [x] Filtres de listes, onglets de fiches commande, rubriques de compte, étapes Atelier et navigation mobile du studio migrés.
- [x] Audit Atelier étendu : pilotage des opérations, onglets des remises par défaut et rails des fiches client débarrassés de leurs anciens fonds actifs et traits locaux.
- [x] Surface Pilotage Atelier contrainte en `minmax(0, 1fr)` : les rails internes restent défilables sans provoquer de débordement horizontal de page sur mobile.
- [x] Rail HTMX des fiches Commande Client/Atelier unifié par `ui-order-tab-list` : même hauteur, même police, même ligne d’assise et défilement horizontal mobile, sans grille encadrée ni fond actif.
- [x] État actif des rails Commande resynchronisé sans rechargement après chaque swap HTMX et restauration d’historique : classe, ARIA, ordre de tabulation et libellé du panneau suivent le bouton déclencheur dans les deux portails.
- [x] Ancienne règle Atelier qui masquait le pseudo-élément des onglets Commande supprimée ; le trait actif et animé reste visible dans les deux portails.
- [x] Primitive DRY `ui-inline-action` pour les liens contextuels des fiches détail, avec variante `ui-inline-action--control` garantissant une cible tactile de 44 px.
- [x] Primitive DRY `ui-destructive-action` appliquée aux déclencheurs « Supprimer » Client/Atelier : texte danger, fond transparent, cible tactile de 44 px et soulignement danger animé.
- [x] Confirmations destructives conservées en `ui-btn-danger` plein dans les dialogues afin de distinguer le déclencheur réversible de l’engagement final.
- [x] Boutons historiques « Fiche », « Ouvrir » et « Contrôler » préservés dans les listes Commandes/Projets Client et Atelier.
- [x] Liens secondaires des fiches Commandes Client et Atelier — suivi, justificatif, fichiers, OF, Drive et navigation interne — alignés sur le même mouvement, sans appliquer ce traitement aux aperçus média.
- [x] CTA primaires, secondaires et toggles métier inchangés.
- [x] Focus clavier visible et mouvement supprimé avec `prefers-reduced-motion: reduce` sans supprimer le feedback coloré.
- [x] Tests de contrat CSS ajoutés.

## Recette

- Survoler une action `ui-btn-ghost` dans une vue Client puis Atelier : le trait part de la gauche, sans déplacement du texte.
- Naviguer au clavier : le focus reste visible et le trait apparaît sur `:focus-visible`.
- Survoler les liens du header, Réglages et Mon compte : même langage, avec conservation de l’état actif.
- Vérifier le header Atelier : « Parc machine » apparaît uniquement dans Réglages, son état actif reste visible et « Identité visuelle » n’est plus listée.
- Ouvrir « Mon compte » côté Client puis Atelier : vérifier le même panneau, l’identité tronquée proprement, les actions lisibles, la sortie danger et la fermeture par Échap/clic extérieur.
- Vérifier les pictogrammes « Mon compte » côté Client puis Atelier : tracé homogène, sens explicite, teintes adaptées au thème et aucun changement des libellés ou permissions.
- Ouvrir « Créer une commande » côté Client : vérifier l’introduction, les deux parcours, l’alignement des icônes et l’absence de débordement.
- Sur `/staff/orders/`, vérifier que les filtres n’ont plus de fond arrondi : le survol anime le trait et « Toutes » conserve le trait actif.
- Sur `/staff/atelier/pilotage/`, vérifier que les étapes Contrôle, Production, Expédition et Facturation utilisent le même rail plat, restent sur une ligne et défilent horizontalement si nécessaire.
- Sur les réglages de remises par défaut Atelier et une fiche client staff, vérifier que les onglets/rubriques n’affichent plus aucun fond actif ni ancien trait en `box-shadow`.
- Vérifier une fiche commande Client et Atelier : même rail horizontal sur les onglets HTMX, sans fond actif, sans cadre interne, sans déplacement ni perte de focus.
- Cliquer successivement sur deux onglets d’une fiche commande Client puis Atelier : le contenu, l’URL, le soulignement actif, `aria-selected`, `tabindex` et `aria-labelledby` changent ensemble sans actualiser la page.
- Utiliser Précédent/Suivant après ces clics : l’onglet actif se recale sur le paramètre `panel` restauré par HTMX.
- Dans les listes Commandes et Projets Client/Atelier, vérifier que « Fiche », « Ouvrir » et « Contrôler » conservent leur ancien rendu de bouton secondaire.
- Dans une fiche commande Client, vérifier les liens Télécharger, justificatif et suivi secondaire : aucun fond arrondi, cible tactile conservée et trait primaire animé.
- Dans une fiche commande Atelier, vérifier les liens Client, Dossier Drive, fichiers, OF PDF, PDF HD, suivi et navigation interne : même animation et aucune police substituée.
- Vérifier les rubriques de compte et les onglets mobiles du studio : état actif lisible sans fond pill.
- Vérifier les déclencheurs « Supprimer » d’une commande Atelier, d’un projet Client, d’un visuel et d’une planche DTF : même rendu plat, même police et même trait danger.
- Ouvrir une confirmation de suppression : le bouton final reste rouge plein et l’action « Annuler » reste secondaire.
- Activer la réduction des animations du système : le trait apparaît sans transition spatiale.
- Vérifier 375 px et 1440 px : aucune variation de largeur, aucun débordement.
- À 375 px, ouvrir successivement le menu du portail, « Créer une commande » et « Mon compte » : les panneaux restent contenus, défilables si nécessaire et les cibles conservent au moins 44 px.

## Checklist

- [x] Code source
- [x] Tests de contrat
- [x] Permissions et isolation inchangées
- [x] Documentation du lot
- [x] Rebuild CSS
- [x] Pytest ciblé
- [x] QA visuelle desktop/mobile
- [x] Graphify actualisé

## Validation

- Header flottant : `npm run build:css` et `collectstatic` OK ; 60 tests de cohérence UI réussis, `manage.py check` et Ruff sans erreur.
- Playwright Client/Atelier, 1440 × 900 : panneaux partagés de 352–368 px, rayon 16 px, actions 60 px, police DM Sans/Space Grotesk préservée et aucun débordement horizontal.
- Playwright Client/Atelier, 375 × 812 : panneaux contenus dans le viewport (`documentWidth = 375`), surfaces à bordure fine sans ombre et cibles tactiles supérieures à 44 px.
- Playwright « Mon compte » Client/Atelier : famille SVG 20 px au trait arrondi `1.8`, puits d’icône de `35,76 px`, teintes Profil/Équipe/Déconnexion issues des tokens de thème et attributs `aria-hidden` / `focusable` vérifiés.
- Playwright « Mon compte » à 1440 × 900 et 375 × 812 : panneaux de `352 px` / `337,41 px`, cibles de `56,55 px`, aucune barre de défilement horizontale et zéro erreur console dans les deux portails.
- Playwright clavier : ouverture par Entrée, focus visible `3px`, fermeture par Échap et focus restauré sur « Mon compte ».
- Playwright contenu long et accessibilité : ellipsis vérifié (`263/611px`), contraste du texte secondaire `5,25:1`, zéro erreur console et animation/transitions à `0s` avec réduction de mouvement.
- Détecteur Impeccable : aucun signalement en mode regex dégradé (parseurs HTML/CSS indisponibles), complété par les styles calculés et la QA visuelle desktop/mobile.
- `npm run build:css` : OK.
- Pytest Docker ciblé UI/portail : **140 tests réussis**.
- `python manage.py check` dans le conteneur : aucun problème.
- Ruff sur le test modifié : OK.
- Détecteur Impeccable sur les fichiers Atelier modifiés : aucun signalement en mode regex dégradé (parseurs HTML/CSS indisponibles), complété par la QA des styles calculés.
- Playwright Chromium, 1440 × 900 : trait calculé de `scaleX(0)` à `scaleX(1)`, hauteur 2 px, couleur primaire live, police inchangée.
- Playwright Chromium, réduction de mouvement : durée calculée `0s`.
- Playwright Chromium, 375 × 812 : menu ouvert, `aria-expanded="true"`, largeur document/client `375/375`.
- Playwright Chromium, liens Commandes Client/Atelier : fond transparent, rayon `0px`, cible `44px`, police DM Sans héritée et trait primaire de `scaleX(0)` à `scaleX(1)`.
- Playwright Chromium, rails Commande Client/Atelier : même hauteur `44px`, même police Space Grotesk, fond transparent, rayon `0px` et indicateur primaire `2px`.
- Playwright Chromium, 375 × 812 : rail en `flex nowrap`, défilement horizontal interne (`277/474px`) et largeur document/viewport `375/375` dans les deux portails.
- Playwright Chromium, déclencheurs « Supprimer » Client/Atelier : cible `44px`, fond transparent, rayon `0px`, police Space Grotesk et trait danger de `scaleX(0)` à `scaleX(1)` ; confirmation ouverte sans soumission.
- Playwright Chromium, focus clavier réel : `:focus-visible` actif, contour `3px`, offset `3px` et trait danger visible.
- Playwright Chromium, vues Atelier `/staff/orders/`, `/staff/atelier/pilotage/`, réglages de remises et fiche client : contrôles à fond transparent, rayon `0px`, sans `box-shadow`, indicateur primaire `2px` et hauteur tactile `44px` pour les rails horizontaux.
- Playwright Chromium, fiche Commande Atelier : pseudo-élément des quatre onglets affiché ; onglet actif à `scaleX(1)`, onglets inactifs à `scaleX(0)` et déclencheur Supprimer avec indicateur danger.
- Playwright Chromium, rails Commande Client/Atelier : après clic HTMX, l’URL, le panneau, `is-active`, `aria-selected`, `tabindex` et `aria-labelledby` pointent immédiatement vers le même onglet, sans rechargement.
- Playwright Chromium, navigation clavier Atelier et historique HTMX Client : ArrowRight et Précédent resynchronisent le rail avec le paramètre `panel` restauré.
- Playwright Chromium, Pilotage Atelier à 375 px : largeur document/viewport `375/375`, rail interne `245/395px` défilable, aucun débordement de page.
- Playwright Chromium, hiérarchie Atelier à 1440 × 900 et 375 × 812 : « Parc machine » est uniquement présent dans « Réglages », son déclencheur et son lien portent l’état actif, « Identité visuelle » est absente et le panneau mobile reste contenu sur `343 px` dans un viewport de `375 px`.
- Console Chromium sur les parcours Atelier vérifiés : **0 erreur, 0 avertissement**.
- Graphify : graphe incrémental actualisé à **6 499 nœuds / 15 235 arêtes**.
