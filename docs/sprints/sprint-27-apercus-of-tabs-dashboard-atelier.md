# Sprint 27 - Aperçus visuels dans les OF et onglets Atelier

## Objectif

Rendre l'ordre de fabrication immédiatement exploitable grâce aux aperçus des visuels client, puis simplifier la file Atelier avec des onglets textuels sans icônes et sans dupliquer les KPI.

## Audit avant évolution

- l'OF listait les noms de fichiers sans permettre leur reconnaissance visuelle ;
- un fichier non prévisualisable pouvait nécessiter un aller-retour vers la fiche commande ;
- la file mélangeait contrôles, OF prêts et productions lancées dans une liste unique ;
- le texte d'introduction répétait des informations déjà portées par le dashboard.

## Parcours livré

- aperçu miniaturisé de chaque visuel dans la table `Fichiers de production` de l'OF ;
- normalisation en PNG sur fond blanc pour une impression fiable ;
- fallback `Aperçu indisponible` sans bloquer la génération du document ;
- quatre onglets sans icônes : `À traiter`, `Prêts à imprimer`, `En production`, `Tous` ;
- compteur par onglet et état actif accessible ;
- paramètre d'URL `queue` partageable et fallback serveur vers `À traiter` ;
- KPI globaux inchangés lors du filtrage ;
- actions d'impression en lot conservées au même endroit.

## Règles métier et sécurité

- le PDF réutilise le moteur de prévisualisation sécurisé des assets ;
- les miniatures sont redimensionnées en mémoire et aucune URL ni chemin de stockage n'est exposé ;
- un aperçu corrompu ou non pris en charge ne bloque jamais l'OF ;
- les onglets filtrent une seule file limitée aux douze dernières commandes soumises ;
- aucune permission ni route publique supplémentaire ;
- les contrôles existants `orders.view_order` et `production.view_productionjob` restent obligatoires.

## Fichiers principaux

- `backend/apps/production/services/manufacturing_order_previews.py`
- `backend/apps/production/services/manufacturing_order_pdf.py`
- `backend/apps/production/services/dashboard.py`
- `backend/apps/portal/views_staff_dashboard.py`
- `backend/templates/portal/staff/dashboard.html`
- `backend/static_src/css/components/product-shell.css`
- `tests/production/test_workflow_api.py`
- `tests/production/test_dashboard_and_batch.py`

## Checklist

- [x] logique d'aperçu isolée dans un service ;
- [x] conversion existante réutilisée et fallback testé ;
- [x] filtres et compteurs centralisés côté service ;
- [x] onglets accessibles, persistés dans l'URL et sans icônes ;
- [x] permissions existantes vérifiées ;
- [x] contrôle visuel PDF, desktop et mobile ;
- [x] Ruff, Django, migrations et suite globale : 386 tests réussis.

## Hors périmètre

- édition ou recadrage du visuel depuis le PDF ;
- persistance de nouveaux fichiers miniatures dédiés aux OF ;
- pagination au-delà des douze dernières commandes ;
- modification des règles de validation Atelier ou d'impression en lot.
