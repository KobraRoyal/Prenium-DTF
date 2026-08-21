# ADR — Parc de machines DTF et traçabilité d'impression

## Statut

Accepté le 21 août 2026 pour le Sprint 42.

## Contexte

L'Atelier doit savoir quelle imprimante DTF prend en charge un dossier de production et
retrouver, dans le temps, sur quelle machine ce dossier a réellement été imprimé. Le workflow
existant sait piloter le statut d'un `ProductionJob`, mais ne modélise ni le parc, ni
l'affectation courante, ni la preuve d'impression.

Une affectation seule ne suffit pas comme preuve : un dossier peut être réaffecté avant son
passage machine, ou réimprimé plusieurs fois. La traçabilité doit également survivre aux
renommages et retraits du parc sans exposer d'information interne dans le portail client.

## Décision

Le parc est une ressource **globale Atelier**. Une machine n'appartient pas à un client : le
tenant reste porté par la commande et n'est jamais recopié sur `ProductionMachine`.

Le domaine sépare trois responsabilités :

- `ProductionMachine` décrit une imprimante identifiée par un code stable et un UUID public ;
- `ProductionJob.assigned_machine` est la projection de l'affectation courante ;
- `ProductionJobMachineAssignment` conserve l'historique append-only des affectations ;
- `ProductionPrintRecord` constitue la preuve explicite, horodatée et append-only d'une
  impression réelle.

Une machine peut être active, en maintenance ou retirée. Elle n'est jamais supprimée depuis
l'interface métier. Les relations historiques utilisent `PROTECT`, tandis que chaque événement
conserve aussi un snapshot du code et du nom de machine. Un renommage ou un retrait ne réécrit
donc pas le passé.

Une seule affectation reste ouverte par job. Une réaffectation ferme l'affectation précédente et
exige un motif. Un job peut posséder plusieurs confirmations d'impression afin de représenter
les réimpressions ; toute confirmation supplémentaire exige une note. Les tokens de confirmation
sont idempotents afin qu'un double envoi HTMX ne crée pas de doublon.

Le workflow historique reste compatible : un job sans machine peut encore progresser. Le
dashboard signale l'absence d'affectation sans bloquer les commandes existantes ni inventer un
backfill. Lorsqu'un job affecté entre en production, l'affectation mémorise le début d'impression,
mais seule l'action explicite « Confirmer l'impression » crée une preuve réelle.

## Sécurité et permissions

- toutes les routes sont réservées au portail staff et utilisent exclusivement les UUID publics ;
- consulter le parc exige `production.view_productionmachine` ;
- créer ou modifier une machine exige `production.manage_productionmachine` ;
- affecter un job exige `orders.view_order`, `production.view_productionjob` et
  `production.assign_productionmachine` ;
- confirmer une impression exige `orders.view_order`, `production.view_productionjob` et
  `production.confirm_productionprint` ;
- les permissions sont vérifiées avant tout lookup d'ordre ou de machine, puis vérifiées à
  nouveau dans les services applicatifs ;
- aucune machine, affectation ou preuve d'impression n'est ajoutée au contexte des vues client ;
- les mutations sont exclusivement en POST avec CSRF ; les historiques n'ont ni route d'édition
  ni de suppression et restent non supprimables dans l'admin technique.

Les services verrouillent les jobs et les machines avec `select_for_update`, valident l'état de
la machine et du job, puis écrivent l'état métier et l'audit dans la même transaction. Les audits
ne contiennent ni numéro de série, ni notes techniques, ni texte libre.

## Conséquences

- le parc et la file Atelier disposent d'une source de vérité commune ;
- l'historique distingue clairement « prévu sur » et « réellement imprimé sur » ;
- aucune donnée de parc n'est visible par un client, même en accès croisé ou via un UUID forgé ;
- la migration est additive et ne fabrique aucun faux historique pour les jobs antérieurs ;
- la maintenance prédictive, la télémétrie RIP, les niveaux d'encre et la planification de
  maintenance restent hors périmètre.
