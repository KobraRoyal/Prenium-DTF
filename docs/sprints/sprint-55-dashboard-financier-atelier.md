# Sprint 55 — Pilotage financier du dashboard Atelier

## Objectif

Donner au responsable Atelier une lecture rapide du chiffre d'affaires sans
alourdir le tableau de bord opérationnel des collaborateurs.

## Livré

- [x] Courbe Chart.js des volumes Atelier maintenue sur une fenêtre de sept
      jours.
- [x] Second graphique Chart.js du **CA TTC** des commandes soumises et
      tarifées sur la même fenêtre.
- [x] Trois indicateurs complémentaires : CA des sept jours, CA du jour et
      panier moyen.
- [x] Composition en deux colonnes à partir de 1100 px, puis empilement mobile
      sans défilement horizontal.
- [x] Données financières calculées et rendues seulement pour les rôles
      `owner` et `admin` disposant déjà des permissions Commandes et
      Production.
- [x] Collaborateurs : aucune série financière dans le contexte de page, le
      HTML ou la réponse HTMX.

## Convention financière

Le bloc est explicitement libellé **CA TTC** : il additionne `Order.total_amount`
pour les commandes `submitted` avec un prix `priced`. Il ne représente pas les
encaissements ; ceux-ci restent un indicateur comptable distinct fondé sur les
paiements capturés.

## Validation

- [x] Tests de calcul de la série, exclusions des brouillons et moyenne panier.
- [x] Tests RBAC admin/collaborateur sur page complète et réponse HTMX.
- [x] Recette Playwright desktop et mobile sans erreur de console ni overflow.
