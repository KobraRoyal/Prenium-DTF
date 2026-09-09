# Sprint 57 — Pilotage de production Atelier

## Objectif

Donner au responsable de production une lecture compacte, actionnable et fiable de la santé de l’Atelier, sans exposer le chiffre d’affaires aux collaborateurs.

## Livré

- Le rail « Production imprimée » conserve les jauges Chart.js de métrage et rassemble désormais l’activité par statut : en traitement, en production, prête à remettre et terminée aujourd’hui.
- Le bloc « Pilotage production » met en évidence les OF bloquées, les retards de remise et les encours sans progression depuis plus de 24 heures.
- Deux mesures de qualité de flux complètent les alertes : taux de réimpression et délai moyen des OF terminés, calculés sur sept jours calendaires.
- Une nouvelle commande signalée par Web Push rafraîchit aussi ces priorités et compteurs, sans recréer les graphiques Chart.js ni interrompre le travail en cours.
- Le CA reste conditionné au rôle owner/admin existant ; les KPI de production restent accessibles aux collaborateurs disposant des permissions Commandes et Production.

## Convention de données

- Une réimpression est une preuve d’impression ayant une preuve antérieure pour le même OF. Elle compte volontairement dans le taux : elle mesure le coût qualité réel du flux.
- Le délai moyen ne retient que les OF terminés avec dates de démarrage et de fin cohérentes. Les OF incomplets ou historiquement non datés ne déforment pas la moyenne.

## Validation

- 164 tests ciblés portail, dashboard, production et notifications réussis.
- Contrôles Django, migrations, Ruff, build CSS, collecte des assets et détection Impeccable réussis.
- Aucune migration ni donnée historique modifiée.
