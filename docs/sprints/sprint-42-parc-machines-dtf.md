# Sprint 42 — Parc de machines DTF et historique d'impression

## Objectif

Donner à l'Atelier une vue opérationnelle du parc DTF, permettre l'affectation d'un dossier à une
imprimante et conserver une preuve fiable de la machine réellement utilisée, sans régression du
workflow de production ni exposition au portail client.

## Décisions de domaine

| Sujet | Règle retenue |
|---|---|
| Portée | Parc global Atelier, sans rattachement artificiel à un client. |
| Identité front | UUID public uniquement ; le code machine est stable et unique sans tenir compte de la casse. |
| Affectation | Une projection courante sur le job et un historique append-only. |
| Impression | Action explicite et horodatée, distincte de l'affectation. Plusieurs confirmations représentent les réimpressions. |
| Conservation | Machines retirées plutôt que supprimées ; relations historiques `PROTECT` et snapshots code/nom. |
| Compatibilité | Les jobs historiques non affectés continuent de suivre le workflow existant ; aucun faux backfill. |

Voir [ADR_DTF_MACHINE_FLEET.md](../architecture/ADR_DTF_MACHINE_FLEET.md).

## Tranches livrées

### T1 — Domaine, migration et services

- `ProductionMachine` avec états actif, maintenance et retiré ;
- machine courante sur `ProductionJob` ;
- historique `ProductionJobMachineAssignment` append-only ;
- preuve réelle `ProductionPrintRecord` append-only et idempotente ;
- services atomiques de parc, d'affectation et de confirmation ;
- audit des créations, modifications, refus, affectations, réaffectations et impressions ;
- démarrage machine enregistré lors du passage du job en production lorsqu'une machine est
  affectée, sans modifier la matrice de transitions historique.

### T2 — Permissions et durcissement

| Action | Permissions requises |
|---|---|
| Voir le parc | `accounts.access_staff_portal` + `production.view_productionmachine` |
| Gérer le parc | accès staff + `production.manage_productionmachine` |
| Affecter un dossier | accès staff + `orders.view_order` + `production.view_productionjob` + `production.assign_productionmachine` |
| Confirmer l'impression | accès staff + `orders.view_order` + `production.view_productionjob` + `production.confirm_productionprint` |

Les permissions précèdent les lookups objet. Les services les réappliquent, refusent les jobs
annulés ou terminaux, les machines non actives, les réaffectations sans motif et les réimpressions
sans note. Les historiques production sont non supprimables dans l'admin technique.

### T3 — Interface Atelier moderne

- route parc : `/staff/machines/` ;
- création et édition HTMX avec feedback toast ;
- synthèse parc actif / maintenance / charge / impressions ;
- registre machines avec charge courante et journal récent ;
- signal machine directement dans la file du dashboard Atelier ;
- station machine dans le panneau Production d'une commande ;
- affectation ou réaffectation contextualisée ;
- confirmation d'impression et réimpression explicites ;
- historiques lisibles des affectations et impressions.

La direction Impeccable conserve le langage visuel existant « papier / encre / acide » : hiérarchie
nette, contrôles tactiles, informations opérationnelles d'abord, responsive sans overflow à
375 px, 768 px et 1024 px. Aucun nouveau système visuel concurrent n'est introduit.

## Contrat de sécurité

- aucune route client de parc, d'affectation ou d'impression ;
- aucun code, nom ou UUID machine dans le panneau ou la timeline client ;
- POST + CSRF pour toutes les mutations ; GET retourne 405 sur les routes d'action ;
- recherche par UUID public après validation de toutes les permissions ;
- verrous transactionnels pour les affectations et confirmations concurrentes ;
- snapshot historique indépendant des renommages futurs ;
- aucune donnée sensible de machine dans les audits ;
- suppression métier absente et suppression admin des historiques interdite.

## Tests et recette

- services : création, code insensible à la casse, audit, état machine et retrait sous charge ;
- affectation : création, idempotence, réaffectation avec motif, machine inactive, statut terminal ;
- impression : token idempotent, réimpression avec note, token forgé entre commandes ;
- historique : snapshots après renommage et protection contre suppression ;
- permissions : anonyme, client, staff lecture seule, gestion parc seule, affectation et
  confirmation séparées, UUID valide/invalide indistinguables sans droit ;
- isolation : aucune identité machine dans les vues client ;
- HTTP : mutations GET refusées et CSRF vérifié ;
- recette navigateur réelle : création DTF-01, affectation d'un OF, confirmation d'impression,
  feedback HTMX, console sans erreur et contrôles responsive multi-écrans ;
- base PostgreSQL réelle : correction du verrou `FOR UPDATE` pour éviter tout verrou sur le côté
  nullable d'une jointure externe.

## Checklist de validation

- [x] migration additive et `makemigrations --check` sans dérive
- [x] permissions serveur et services applicatifs indépendants
- [x] audits succès et refus sans métadonnées sensibles
- [x] vues Atelier Impeccable et parcours HTMX opérationnels
- [x] recette navigateur desktop, tablette et mobile sans overflow
- [x] tests ciblés backend, portail et workflow
- [x] suite globale sans régression — 755 tests passés, 1 ignoré
- [x] build CSS final, Ruff, contrôles Django et migrations sans dérive
- [x] smoke Docker final — web, worker et nginx sains ; base et cache disponibles
- [x] graphe Graphify rafraîchi

## Hors périmètre

- pilotage du RIP, profils ICC, couche de blanc ou réglages d'impression ;
- télémétrie, niveaux d'encre, compteur matériel et maintenance prédictive ;
- ordonnancement automatique multi-machines ;
- disponibilité par créneau ou réservation de capacité ;
- exposition du parc ou de l'historique interne aux clients.
