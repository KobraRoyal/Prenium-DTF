# Références commande — numérotation et affichage

Document de référence pour la numérotation métier des projets B2B / commandes et les règles
d’affichage côté client, staff et Atelier.

## Numérotation métier

### Format unique

Tous les projets de commande B2B (`B2BOrderProject`), quel que soit le mode, partagent le même
format :

```text
CMD-{ANNÉE}-{SÉQUENCE}
```

Exemples : `CMD-2026-000104`, `CMD-2026-100001`.

- **Préfixe** : `CMD` (commande), jamais `GANG-SHEET` ni autre variante.
- **Séquence** : entier sur 6 chiffres, incrémenté par année civile (`B2BOrderProjectNumberSequence`).
- **Unicité** : contrainte `unique=True` sur `project_number` ; une seule file d’attente par année
  pour les modes `individual_designs`, `ready_gang_sheet` et `reorder`.

### Implémentation

| Fichier | Rôle |
|---------|------|
| `backend/apps/b2b_order_projects/services/numbering.py` | Génération `next_number()` |
| `backend/apps/b2b_order_projects/services/projects.py` | Attribution à la création |
| `backend/apps/b2b_order_projects/migrations/0011_unify_project_number_cmd_prefix.py` | Renommage rétroactif `GANG-SHEET-*` → `CMD-*` pour les projets `ready_gang_sheet` |

### Note de commande à la conversion

Lors du checkout projet → commande, la note client (`Order.customer_note`) inclut toujours :

```text
Commande CMD-2026-000104
```

Le libellé « Gang Sheet » n’est plus préfixé au numéro métier ; le **type** de parcours reste
identifiable via `order_mode` et l’UI studio planches (`Gang Sheet …` = contexte produit, pas le n°).

## Helpers d’affichage (couche `orders`)

Module : `backend/apps/orders/references.py`

| Helper | Description | Exemple |
|--------|-------------|---------|
| `order_business_number(order)` | N° métier `CMD-…` depuis le projet source lié | `CMD-2026-000104` |
| `order_uuid_short(order)` | 12 derniers caractères du `public_id` (Atelier) | `a1b2c3d4e5f6` |
| `order_client_reference(order)` | Libellé client : nom projet, réf. client, ou 1re ligne de note | `Collection été` |
| `project_client_reference(project)` | Idem pour un projet non converti | `Ma série print` |

Tags template portail : `order_business_ref`, `order_uuid_ref` (`portal_tags.py`).

## Règles d’affichage par surface

### Principe

| Surface | UUID court | N° `CMD-…` | Réf. client |
|---------|:----------:|:----------:|:-----------:|
| **Client** (listes, fiche, breadcrumb) | Non | Oui | Oui (si renseignée) |
| **Staff OPS** (listes, fiche) | Oui | Oui | Oui |
| **Atelier / production** | Oui | Oui | Oui (+ client, OF, etc.) |

L’UUID (`public_id`) reste l’identifiant technique d’URL et d’API ; il n’est **pas** exposé dans
l’UI client.

### Templates concernés

- Listes : `components/tables/orders_table.html`, `atelier_worklist_table.html`
- Fiches : `portal/client/order_detail.html`, `portal/staff/order_detail.html`
- Breadcrumbs / en-têtes : `components/portal/client_refs.html`, partials `page_head_leads/*`
- Présentation client : `portal/client_order_presentation.py` (`identity.reference` = n° métier)
- Focus dashboard Atelier : `production/services/dashboard.py`

### Projets B2B (avant conversion)

Le `project_number` (`CMD-…`) s’affiche tel quel dans les listes et fiches projet. Le libellé
« Gang Sheet » dans le studio planches DTF qualifie le **type de planche**, pas le numéro.

## Sécurité

- Accès objet toujours scopé par `Customer` + `public_id` UUID.
- Les helpers ne contournent pas les permissions ; ils ne font que formater des champs déjà autorisés.
- Ne jamais utiliser l’ID incrémental Django en front.

## Tests de non-régression

| Suite | Couverture |
|-------|------------|
| `tests/orders/test_references.py` | Helpers métier |
| `tests/b2b_order_projects/test_models_and_services.py` | Numérotation `CMD-` tous modes |
| `backend/apps/portal/tests/test_client_order_presentation.py` | Identité fiche client |
| `backend/apps/portal/tests/test_ui_coherence.py` | Tags template staff/client |
| `tests/ui/test_portal_ui.py` | Rendu HTML listes |

## Historique

| Date | Changement |
|------|------------|
| Migration `0006` | Préfixe historique `GANG-SHEET-` sur tous les projets |
| Migration `0009` | Séparation temporaire : fichiers → `CMD-`, gang-sheet → `GANG-SHEET-` |
| Août 2026 (Sprint 48) | Unification `CMD-` + règles d’affichage client / Atelier documentées ici |

## Liens

- [B2B_ORDER_PROJECTS.md](B2B_ORDER_PROJECTS.md) — agrégat projet avant commande
- [Sprint 48 — shell clair](../sprints/sprint-48-shell-clair-homogene-impeccable.md) — micro-lots UI
