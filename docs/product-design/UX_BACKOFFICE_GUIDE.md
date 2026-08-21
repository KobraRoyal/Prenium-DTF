# Guide UX Backoffice

## Intentions
- rapidité
- lisibilité
- faible charge mentale
- usage atelier réel
- tablettes et desktop

## Règles
- actions majeures en 1 clic
- statuts très visibles
- scans rapides depuis la console de pilotage dédiée
- historique immédiat
- informations essentielles au-dessus de la ligne de flottaison

## Fiche commande staff (workflow GPAO)

Alignement **direction GPAO** × **design** :

- **Bandeau client + statuts** : reste la zone d’identification rapide (client, statut commande, mode facturation, tarif, encours, OF / Drive).
- **Synthèse atelier** (`workflow-summary`) : quatre blocs — **Commande**, **Tarification**, **Ordre de fab.**, **Prochaine action** — pour que l’opérateur sache *où en est la commande* et *quoi faire ensuite* sans ouvrir les panneaux.
- **Onglets essentiels** : **Contrôle**, **Production**, **Expédition**, **Facturation**. **Incident Drive** apparaît uniquement lorsqu'une synchronisation demande une intervention.
- **Pilotage séparé** : les scans et changements de statut en série vivent dans `/staff/atelier/pilotage/`, pas dans la fiche d'une commande.
- **Fiche réservée aux exceptions** : affectation machine, contrôle détaillé, résolution d'un prérequis et traces complètes restent accessibles sans dupliquer la file opérateur.

Fichiers : `templates/portal/staff/order_detail.html`, `components/portal/staff_order_workflow_summary.html`, `components/order/order_tabs.html`, `static_src/css/components/workflow.css`, `apps/portal/templatetags/order_tags.py`.

## Pilotage Atelier

- champ OF/client autofocus compatible douchette ;
- quatre files : à traiter, à expédier, terminés et tous ;
- transitions autorisées proposées directement sur chaque ligne ;
- prérequis paiement/tarif explicités avec lien de résolution ;
- déclaration et synchronisation Sendcloud sans quitter la file ;
- feedback visible et toast après chaque mutation, avec e-mails client conservés aux jalons métier prévus.
