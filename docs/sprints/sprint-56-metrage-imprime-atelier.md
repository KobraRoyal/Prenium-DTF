# Sprint 56 — Pilotage du métrage imprimé Atelier

## Objectif

Donner à l’Atelier un suivi opérationnel de la consommation de film DTF, sans exposer les données de chiffre d’affaires aux collaborateurs.

## Livré

- Chaque confirmation d’impression fige son métrage linéaire dans la preuve d’impression.
- La valeur provient du métrage explicitement défini sur la commande ou, à défaut, de ses lignes DTF.
- Les réimpressions sont volontairement incluses : elles représentent une consommation réelle.
- Le tableau de bord affiche un rail de trois jauges demi-lune : cumul sept jours, métrage du jour et moyenne par impression.
- Les indicateurs restent disponibles aux utilisateurs Atelier ayant accès à la file de travail.

## Données historiques

Les preuves d’impression créées avant cette évolution ne possèdent pas de métrage figé. Elles ne sont donc pas rétro-calculées et n’apparaissent pas dans la courbe : cela évite de présenter une estimation comme une consommation réelle.

## Validation

- Migration appliquée sans modification des preuves historiques.
- Tests du suivi d’impression, du dashboard Atelier et du rendu responsive.
- Contrôles Django, style, migrations et tests globaux avant livraison.
