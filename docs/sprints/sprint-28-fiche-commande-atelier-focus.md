# Sprint 28 - Fiche commande Atelier orientée action

## Objectif

Transformer la fiche commande staff en écran de décision : comprendre l’état réel, identifier la prochaine action et accéder directement au bon panneau, sans répéter les informations déjà disponibles ailleurs.

## Audit avant évolution

- la commande, le client et les statuts étaient répétés entre l’en-tête et la barre de commande ;
- la carte `Client & références` affichait principalement des champs vides ou non actionnables ;
- la prochaine action était isolée dans une carte supplémentaire ;
- `Fichiers` répétait les visuels et leurs contrôles déjà présents dans `Contrôle` ;
- les groupes d’onglets et leurs icônes alourdissaient une navigation déjà explicite ;
- Drive occupait un onglet permanent même lorsque toutes les synchronisations étaient correctes.

## Parcours livré

- un bandeau unique regroupe client, référence commande, OF, états utiles et tarification ;
- une seule prochaine action métier est calculée côté service et affichée avec son explication ;
- le panneau recommandé s’ouvre automatiquement en l’absence de paramètre `panel` ;
- cinq onglets textuels sans icône : `Contrôle`, `Production`, `Scan atelier`, `Expédition`, `Facturation` ;
- `Fichiers` est retiré de la navigation, sa route reste disponible pour compatibilité ;
- `Incident Drive` apparaît uniquement si un fichier n’est pas synchronisé ou porte une erreur ;
- les accès directs au calcul du prix et au dossier Drive restent disponibles dans le bandeau ;
- mise en page responsive : synthèse compacte sur desktop, actions pleine largeur sur mobile.

## Architecture, sécurité et traçabilité

- `AtelierDashboardService.build_order_focus()` centralise la lecture de l’état et la prochaine action ;
- `OrderService.get_staff_order()` précharge revues Atelier et synchronisations Drive pour éviter les requêtes répétées ;
- aucune transition métier n’est déclenchée par la nouvelle synthèse ;
- les permissions objet et permissions de panneau existantes restent appliquées côté serveur ;
- aucune donnée client supplémentaire n’est exposée et aucune route publique n’est ajoutée ;
- aucun nouvel audit n’est requis : ce lot modifie uniquement la présentation et la navigation en lecture.

## Fichiers principaux

- `backend/apps/production/services/dashboard.py`
- `backend/apps/orders/services/orders.py`
- `backend/apps/portal/views_staff.py`
- `backend/apps/portal/templatetags/order_tags.py`
- `backend/templates/portal/staff/order_detail.html`
- `backend/templates/components/order/order_tabs.html`
- `backend/static_src/css/components/workflow.css`
- `backend/static_src/css/components/product-shell.css`
- `tests/production/test_dashboard_and_batch.py`
- `tests/ui/test_portal_ui.py`

## Checklist

- [x] état et prochaine action centralisés dans un service ;
- [x] composants et contenus redondants retirés de la fiche ;
- [x] boutons et onglets sans icônes ;
- [x] onglet recommandé ouvert par défaut ;
- [x] incident Drive affiché uniquement si nécessaire ;
- [x] permissions existantes conservées et accès croisé inchangé ;
- [x] tests service, structure UI et intégration ajoutés ;
- [x] contrôle visuel desktop et mobile ;
- [x] Ruff, Django, migrations et suite globale : 388 tests réussis.

## Hors périmètre

- suppression des anciennes routes de panneaux ;
- modification des transitions de production, d’expédition ou de facturation ;
- modification des données client ou du modèle de commande.
