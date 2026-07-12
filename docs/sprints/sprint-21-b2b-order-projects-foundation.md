# Sprint 21 — Fondation projets de commande B2B

## Objectif

Insérer une phase de projet client avant la commande et le workflow de production existants.

## Livré

- [x] app `b2b_order_projects` dédiée ;
- [x] projet, lignes, contraintes, index et numérotation annuelle verrouillée ;
- [x] statuts et transitions centralisés ;
- [x] activation globale, initialement complétée par un flag client désormais déprécié ;
- [x] permissions member / owner / OPS ;
- [x] API CRUD, lignes, duplication, réorganisation, soumission et annulation ;
- [x] liste, création, détail, autosave HTMX et édition des lignes ;
- [x] file OPS read-only ;
- [x] audit des actions et rejets ;
- [x] pagination et tests inter-tenant ;
- [x] aucun changement du workflow `Order -> ProductionJob` ;
- [x] baseline emails asynchrones stabilisée.
- [x] recette navigateur client → transmission → file OPS, sans erreur console.

## Hors périmètre

- upload et versioning ;
- analyse DPI/transparence ;
- estimation et nesting ;
- contrôle OPS actif ;
- notifications de projet ;
- conversion en commande.

## Configuration

```env
B2B_DTF_ORDER_PROJECT_ENABLED=True
B2B_ORDER_PROJECT_LIST_PAGE_SIZE=20
STAFF_B2B_ORDER_PROJECT_LIST_PAGE_SIZE=25
```

Quand le flag global est actif, le parcours est disponible pour tout client actif disposant d'un
membership actif. `b2b_order_projects_enabled` est conservé uniquement pour compatibilité.

## Validation

```bash
make check
make migrations-plan
make test-b2b
make lint
make format
make test
```

## Gate Sprint 2

- [x] ADR `Asset` générique approuvé ;
- [x] migration additive sans déplacement des données ;
- [x] plan de rollback documenté ;
- [x] suite complète verte avant rattachement des fichiers.
