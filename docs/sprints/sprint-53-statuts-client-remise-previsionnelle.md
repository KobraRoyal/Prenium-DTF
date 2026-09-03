# Sprint 53 — Statuts client et remise prévisionnelle

## Objectif

Rendre le suivi client cohérent entre la liste, la fiche commande et les panneaux
de production/expédition pour les deux parcours généraux : retrait atelier et
expédition transporteur. Ajouter une date prévisionnelle de remise visible par
le client et modifiable par l’Atelier avec une trace d’audit.

## Livré

- [x] Projection de statut client centralisée : paiement/tarif, production,
      remise au transporteur, livraison et retrait.
- [x] Distinction client entre « Prête au retrait », « Prête à expédier »,
      « Expédiée » et « Livrée ».
- [x] Libellés de remise adaptés au mode choisi : « Retrait prévu » ou
      « Livraison prévue ».
- [x] Date prévisionnelle affichée dans la liste et la fiche commande client,
      avec « À confirmer » si elle n’est pas encore renseignée.
- [x] Date prévisionnelle éditable par un membre Atelier autorisé depuis le
      panneau Production.
- [x] Modification et effacement de la date tracés dans l’audit métier.
- [x] Sélecteur de date partagé entre le portail client et l’Atelier, aligné sur
      les tokens Atelier clair et sans contrôle natif divergent.
- [x] Navigation du calendrier conservée au clavier avec icônes SVG accessibles
      et états focus/sélection cohérents.
- [x] Timeline client alignée sur les mêmes statuts que le badge de commande.
- [x] Cas général priorisé ; aucun contournement métier ajouté pour un mode de
      retrait utilisé exceptionnellement comme livraison interne.

## Validation

- [x] Migration Django vérifiée sans changement manquant.
- [x] 74 tests portail, production et expédition réussis.
- [x] Tests ciblés de projection client, ETA, permissions et audit réussis.
- [x] Suite complète : 193 tests réussis.
- [x] Ruff et formatage Python conformes.
- [x] Recette visuelle authentifiée Atelier : champ, calendrier ouvert et date
      sélectionnée contrôlés dans Chrome.
- [x] Graphe Graphify actualisé après intégration.
