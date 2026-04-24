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
- scans rapides
- historique immédiat
- informations essentielles au-dessus de la ligne de flottaison

## Fiche commande staff (workflow GPAO)

Alignement **direction GPAO** × **design** :

- **Bandeau client + statuts** : reste la zone d’identification rapide (client, statut commande, mode facturation, tarif, encours, OF / Drive).
- **Synthèse atelier** (`workflow-summary`) : quatre blocs — **Commande**, **Tarification**, **Ordre de fab.**, **Prochaine action** — pour que l’opérateur sache *où en est la commande* et *quoi faire ensuite* sans ouvrir les panneaux.
- **Onglets groupés** : trois familles **Préparation** (Fichiers, Contrôle, Drive), **Atelier** (Production, Scan atelier), **Clôture** (Expédition, Facturation). Les libellés de groupe reprennent le vocabulaire atelier plutôt qu’une simple liste plate.
- **Titre du bloc workflow** : « Workflow commande » + texte d’aide sur le déroulé (préparation → atelier → clôture).

Fichiers : `templates/portal/staff/order_detail.html`, `components/portal/staff_order_workflow_summary.html`, `components/order/order_tabs.html`, `static_src/css/components/workflow.css`, `apps/portal/templatetags/order_tags.py`.
