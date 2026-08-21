# Audit Impeccable — portail Atelier Prenium DTF

**Date :** 21 août 2026

**Périmètre :** toutes les vues staff Atelier, les panneaux HTMX de commande et les réglages accessibles depuis le shell staff.

**Mode Impeccable :** `Operate`, avec le playbook `Distill`.
**Contrainte :** services métier, permissions et isolation restent les autorités ; la nouvelle
console ne duplique aucune règle de transition ou d'expédition.

## Verdict

Le portail Atelier possédait déjà une identité forte « papier / encre / acide » et des flux métier
fiables. Son principal défaut était une densité inégale : raccourcis déjà présents dans la
navigation, statuts répétés entre en-tête et panneaux, formulaires secondaires toujours ouverts et
quelques vues historiques trop génériques.

Le lot conserve toutes les fonctions mais rend l'intention de chaque écran visible en quelques
secondes : traiter la prochaine commande, contrôler un dossier, exploiter une machine, valider un
accès ou modifier un réglage.

| Axe Impeccable | Avant | Après | Résultat |
|---|---:|---:|---|
| Accessibilité | 4 / 4 | **4 / 4** | Ordre DOM et ordre visuel alignés, détails natifs, focus et cibles tactiles conservés. |
| Performance | 2 / 4 | **2 / 4** | Aucune dépendance ajoutée ; la dette du bundle CSS reste hors lot. |
| Responsive | 3 / 4 | **4 / 4** | KPI tablette 2×2, listes adaptatives, actions progressives et onglets de commande maîtrisés. |
| Theming | 3 / 4 | **4 / 4** | Un seul langage visuel existant, aucun gradient, glass ou composant générique concurrent. |
| Implementation Integrity | 2 / 4 | **4 / 4** | Redondances retirées, cache CSS invalidé et contrats Django/HTMX préservés. |
| **Total** | **14 / 20** | **18 / 20** | **Interface opérationnelle professionnelle, sans P1 UI restant.** |

## Couverture de l'audit

| Surface | Décision UI/UX |
|---|---|
| File Atelier | Suppression des raccourcis dupliqués et du kicker ; une action primaire de lot, options rapides repliées. |
| Liste des commandes | Structure table/cartes et filtres conservés : aucune redondance bloquante. |
| Fiche commande | En-tête réduit à l’OF, la commande, le client, le total et l’unique action suivante ; date, états normaux et retour dupliqué retirés. |
| Contrôle fichiers | Compteurs à zéro, carte de priorité et confirmation globale retirés ; une phrase dynamique précède les fichiers. |
| Incident Drive | Panneau d'exception conservé, sans données décoratives. |
| Production | Référence, opérateur et frise redondants retirés ; machine masquée quand aucune action ni trace n’existe ; métrage et historiques repliés. |
| Pilotage Atelier | Scan/recherche autofocus, files par intention, transitions et Sendcloud directement sur chaque ligne. |
| Fiche commande — Scan | Onglet retiré ; l'ancienne route redirige vers le Pilotage avec l'OF recherché. |
| Expédition | État prêt/transporteur affiché une fois ; bloc de prérequis supprimé lorsque l’envoi existe ou peut être créé. |
| Facturation | Total prioritaire ; détail du prix replié ; encours RCA fusionné ; fichiers déjà présents dans Contrôle retirés. |
| Projets B2B — liste | File responsive conservée. |
| Projets B2B — détail | Remplacement de la table legacy et du texte de sprint par une fiche de contrôle ligne par ligne. |
| Comptes — liste | Recherche et table/cartes jugées cohérentes. |
| Compte — détail | Disclosure progressif existant conservé pour compte, tarification, remises, relevés et accès. |
| Parc machines | Registre avant création ; ajout d'imprimante replié et rouvert automatiquement en erreur. |
| Demandes d'accès — liste | Compteur de résultats dupliqué supprimé. |
| Demande d'accès — détail | Validation primaire ; refus sensible replié, tout en restant accessible et explicite. |
| Modèles d'e-mails | Lien retour dupliqué supprimé dans l'éditeur ; sauvegarde et aperçu conservent leur hiérarchie. |
| Remises par défaut | Ajout de palier replié ; grille de référence prioritaire. |
| Réglages Gang Sheet | En-tête partagé, disparition du kicker et du badge redondant « Atelier uniquement ». |
| Profil et équipe Atelier | Shell, permissions, formulaires et confirmations existants vérifiés sans changement nécessaire. |

## Principes appliqués

1. Une action primaire clairement identifiable par vue.
2. Un état affiché au niveau où il aide réellement la décision.
3. Les actions rares ou sensibles passent par un disclosure natif, jamais par une modale décorative.
4. Les historiques restent visibles lorsque leur valeur est la traçabilité, même si l'état courant
   apparaît ailleurs.
5. Les informations métier spécialisées ne sont pas simplifiées au point de perdre leur utilité.
6. Le vocabulaire staff devient français et orienté tâche : `File Atelier`, `Commandes`, `Comptes`,
   `Machines DTF`, `Outils`.

## Distillation de la fiche commande ciblée

La recette a été conduite sur la commande
`ac5811bb-19e3-4adc-ac36-9e50cb7516aa`, avec ses données réelles, ses quatre panneaux HTMX
essentiels et le panneau Incident Drive conditionnel.

| Information | Propriétaire unique après distillation |
|---|---|
| Identité OF, référence commande, client, total | Synthèse de la fiche |
| État ou blocage demandant une décision | Action suivante ou panneau concerné |
| Validation d’un fichier | Ligne du fichier dans Contrôle |
| Machine et preuve d’impression | Production, uniquement si actionnable ou historisée |
| État Sendcloud et suivi | Expédition |
| Mode d’encaissement et justificatif | Facturation |
| Dates, acteurs et motifs | Disclosures d’historique |

Les numéros et sous-titres des onglets ont été supprimés : les quatre noms de domaine suffisent. Le
nombre de colonnes est dérivé du nombre réel d’onglets, y compris lorsque l’onglet d’incident Drive
apparaît, sans cellule vide sur desktop ou mobile.

## Validation attendue

- build des bundles CSS et collecte des assets ;
- contrôle Django, migrations et Ruff ;
- tests UI, portail, production, projets B2B et suite globale : **769 réussis, 1 ignoré** ;
- recette réelle authentifiée à 1440 px et 768 px ;
- vérification des disclosures machine, remise et refus ;
- détection Impeccable finale exécutée une seule fois ;
- graphe Graphify rafraîchi.

## Dette non bloquante

- scinder le bundle portail staff/client pour réduire son coût de maintenance ;
- consolider progressivement les couches CSS historiques dans des fichiers par domaine ;
- ajouter des filtres serveur avancés à la liste Commandes si la volumétrie Atelier augmente ;
- instrumenter le temps « arrivée commande → prise en charge » avant toute nouvelle densification du dashboard.
