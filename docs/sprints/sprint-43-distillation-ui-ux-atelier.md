# Sprint 43 — Distillation UI/UX du portail Atelier

## Objectif

Revoir toutes les surfaces Atelier avec Impeccable afin de réduire la charge cognitive, supprimer
les répétitions d'information et donner une action principale évidente à chaque vue, sans modifier
les règles métier ni les permissions.

## Livré

- navigation staff renommée `File Atelier` et cohérente avec le titre de la vue ;
- dashboard recentré sur la prochaine commande et l'impression d'OF ;
- actions d'impression secondaires placées dans un disclosure progressif ;
- fiche commande et panneaux Production, Expédition et Facturation distillés ;
- seconde passe de distillation sur une commande réelle : synthèse compacte, quatre onglets sans
  sous-titres, Contrôle sans compteurs nuls, historiques et métrage repliés ;
- scan et transitions rapides déplacés vers la console dédiée `Pilotage Atelier` ;
- fiche projet B2B reconstruite pour le contrôle opérationnel ;
- création de machine et de palier de remise repliées ;
- refus d'accès rendu secondaire, explicite et accessible ;
- réglages Gang Sheet alignés sur le `page_head` partagé ;
- cachebuster CSS mis à jour pour garantir le rendu après déploiement ;
- documentation de couverture complète dans
  [AUDIT_ATELIER_UI_UX_IMPECCABLE_2026-08-21.md](../product-design/AUDIT_ATELIER_UI_UX_IMPECCABLE_2026-08-21.md).

## Contrats préservés

- les permissions et règles d'isolation existantes restent la source de vérité ;
- l'ancienne route Scan reste compatible par redirection vers le pilotage ;
- aucun POST, token CSRF ou cible HTMX retiré ;
- toutes les actions métier existantes restent atteignables ;
- les historiques de production et d'impression restent visibles ;
- les variantes desktop, tablette et mobile conservent le même ordre sémantique.

## Checklist

- [x] audit statique de toutes les vues Atelier et panneaux HTMX
- [x] direction Impeccable `Operate / Distill`
- [x] composants et templates modifiés sans logique métier dans les vues
- [x] tests de cohérence UI mis à jour
- [x] cache CSS invalidé
- [x] build et collecte des assets finaux
- [x] recette navigateur à 1440, 768 et 375 px, sans overflow ni erreur console
- [x] contrôles Django, migrations et Ruff ; 113 tests ciblés puis 757 tests globaux réussis, 1 ignoré
- [x] détecteur Impeccable final exécuté une fois ; grille signalée conservée uniquement sur le vrai canvas Gang Sheet et fond décoratif Production retiré
- [x] graphe Graphify rafraîchi
