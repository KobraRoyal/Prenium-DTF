# Sprint 33 — Navigation SaaS client et Atelier

## Objectif

Rendre la navigation principale des portails client et Atelier plus intuitive, plus sobre et plus proche des usages SaaS, sans modifier les routes, les permissions objet ni les règles métier.

## Périmètre livré

- shell commun conservé dans `components/nav/portal_header.html` ;
- navigation client et navigation Atelier extraites dans deux partials dédiés ;
- espace actif explicite : `Espace client` ou `Atelier` ;
- libellé commun `Dashboard` et état courant via `aria-current="page"` ;
- action client `Créer une commande` séparée de la navigation de consultation ;
- fonctions Atelier secondaires regroupées sous `Outils` ;
- menu profil partagé avec déclencheur compact `initiale + Mon compte`, identité détaillée dans le panneau, raccourcis contextuels et déconnexion isolée ;
- raccourci `Gérer l’équipe` limité aux propriétaires/managers et bascule `Ouvrir l’Atelier` limitée aux comptes hybrides autorisés ;
- contexte du header unifié pour rendre `Gérer l’équipe` stable sur dashboard, listes, projets, Gang Sheets et fiches commande ;
- menu `Créer une commande` à deux parcours : import de fichiers ou génération d’une Gang Sheet pour les clients éligibles ;
- entrée `Mes informations` dans le menu du compte, avec modification sécurisée du prénom et du nom ;
- e-mail de connexion présenté en lecture seule et mise à jour du profil tracée sans donnée personnelle dans les métadonnées d’audit ;
- page `Mon compte` recomposée en centre de compte : identité et raccourcis contextuels dans un rail, formulaire unique, détection des modifications et confirmation par toast ;
- menu mobile pleine largeur, cibles tactiles de 44 px minimum et fermeture clavier ;
- aucun lien autonome `Planches DTF` dans le header : le parcours Gang Sheet reste disponible depuis `Créer une commande` quand le client est éligible ;
- suppression du raccourci sans utilité `Voir le site` dans le menu du compte.
- bibliothèque `Mes Gang Sheets` orientée reprise de tâche, avec création en dialogue, filtres locaux, recherche, cartes visuelles et action adaptée au statut ;
- aperçu de planche affiché via la route backend déjà scopée, en disposition inline privée et sans exposition directe du stockage ;
- suppression déplacée dans un menu secondaire, avec la confirmation et les refus métier existants conservés.
- studio Gang Sheet transformé en surface de travail pleine largeur : en-tête compact, métriques condensées, canevas prioritaire et panneaux latéraux indépendants ;
- progression rendue dynamique selon le statut réel, avec état d’enregistrement local, alerte avant sortie et commandes de zoom de `50 %` à `150 %` ;
- navigation mobile du studio en trois sections `Fichiers`, `Composition` et `Réglages`, sans empiler l’ensemble des outils dans une page interminable ;
- hauteur du studio bornée au viewport : le rouleau long défile dans le plan de travail tandis que la bibliothèque et le contrôle restent accessibles ;
- vocabulaire de validation clarifié et cibles interactives maintenues à `44 px` minimum.
- visuels du studio recentrés dans leur boîte transformée afin que le cadre de sélection reste ajusté aux rotations `0°`, `90°`, `180°` et `270°`.
- largeur extérieure du studio réalignée sur le conteneur portail commun de `1120 px`, avec adaptation automatique du canevas à l’espace disponible.
- aperçu immédiat des fichiers Illustrator `.ai` compatibles PDF grâce à la détection de signature `%PDF-`, avec rasterisation serveur conservée pour les AI natifs.

## Invariants sécurité

- une route authentifiée `/account/profile/` est ajoutée sans modifier les permissions objet existantes ;
- les conditions d’affichage restent une aide UX, jamais une autorité d’accès ;
- les vues staff et les mixins de scope client continuent d’appliquer les refus côté serveur ;
- aucune donnée d’un autre client n’est introduite dans le contexte du header.

## Checklist de validation

- [x] Compilation Tailwind et syntaxe JavaScript.
- [x] Tests ciblés navigation, profil, Gang Sheets, rôles, accès et éligibilité : 80 réussis.
- [x] `ruff check`, format des fichiers du lot, `manage.py check` et migrations à sec.
- [x] Contrats des six agents Codex validés.
- [x] Recette client et Atelier authentifiée à 375, 768, 1280 et 1512 px.
- [x] Menu `Outils` testé au clic et au clavier avec restitution du focus sur `Escape`.
- [x] Menu profil testé au clic, au clavier, hors-clic et avec fermeture mutuelle des menus.
- [x] Raccourcis profil testés pour les rôles client, Atelier et hybride.
- [x] Présence Owner/Admin testée sur quatre familles de vues et recettée sur une fiche commande réelle.
- [x] Menu de création testé au clavier, au clic extérieur et en fermeture mutuelle avec le profil.
- [x] Stack Docker relancée et `/healthz/` valide avec base et cache disponibles.
- [x] Suite complète de non-régression : 494 tests réussis.
- [x] Recette navigateur des deux vues à `1512 × 828` et `375 × 812`, sans débordement horizontal et avec cibles tactiles d’au moins `44 px`.
- [x] Contrats du studio : progression, zoom, état non enregistré, protection avant sortie et panneaux mobiles couverts par 60 tests ciblés.
- [x] Alignement du visuel et du cadre de sélection couvert pour les quatre rotations autorisées.
- [x] Cohérence de largeur entre le studio Gang Sheet et les autres vues du portail couverte par contrat CSS.
- [x] Aperçu pré-import des AI compatibles PDF et fallback sécurisé des AI natifs couverts par contrat JavaScript.

## Risques résiduels

- le débordement historique de certaines cartes du dashboard Atelier à 375 px reste hors du shell de navigation et doit être traité dans un lot dédié ;
- le détecteur Impeccable conserve un avertissement préexistant sur une bordure latérale du workflow, hors périmètre navigation.
- les alertes Impeccable restantes concernent la police et des bordures latérales historiques du design global, pas les nouvelles compositions `Mon compte` et `Mes Gang Sheets`.
