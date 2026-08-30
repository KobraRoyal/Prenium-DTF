# Prompt maître — Shopify POD + WMS (orchestration économe)

> Coller ce prompt **tel quel** en début de session agent. Remplacer uniquement `LOT=…`.

---

## Mission

Implémente le **lot `LOT=`** du sprint Shopify POD + WMS selon les docs liées.  
Un seul lot par session. Produis d’abord le **plan compact** (template sprint), attends validation implicite via critères DoD, puis code.

## Lire (chemins uniquement — ne pas tout coller)

1. `AGENTS.md`
2. `docs/architecture/ADR_SHOPIFY_POD_WMS.md`
3. `docs/sprints/sprint-pod-shopify-wms.md`
4. `docs/architecture/CODEX_AGENT_ORCHESTRATION.md`
5. Skill(s) du lot (table sprint) — lire le `SKILL.md` une fois

## Anti-gaspillage tokens (obligatoire)

- `graphify query "<question bornée>" --budget 800` **avant** Grep/Read large ; puis Read ciblé seulement.
- Interdit : dump repo, logs bruts, re-citer l’ADR entier, explorer hors fichiers autorisés du plan.
- Compte rendu final ≤ 25 lignes : diff résumé, tests, risques restants, next lot.
- Max **3** sous-agents, profondeur **1**. Terra = explore/tests ; Sol = write. **1 writer** par set de fichiers.
- Tâche triviale = pas de sous-agent.
- Multi-tenant / webhook / fichier / stock → `ids_security_reviewer` **après** implémentation, avant merge.

## Invariants (ne jamais violer)

- Pas de logique métier dans vues / templates / app blocks Shopify.
- Services SRP + DRY ; réutiliser patterns `production` (OF, scan) sans coupler au métrage.
- Zone UI POD : `/staff/atelier/pod/` séparée du DTF métrage.
- `public_id` en URL ; permissions objet serveur ; isolation owner stock (client vs atelier).
- `02_rip/` **strictement plat** ; mix techniques = N slots / 1 pièce.
- Modes variante : `POD|ON_STOCK|VIRTUAL|UNMANAGED|DISABLED`.
- WMS : qty par `StorageLocation` ; refus réservation si qty dispo = 0 (POD-18) ; scan bin (POD-17).

## Ordre d’exécution session

1. Confirmer `LOT` et scope IN/OUT (5 lignes).
2. Graphify + plan template sprint (fichiers bornés).
3. Si modèle/migration risqués → avis domain architect (lecture) **ou** racine assume et documente.
4. Implémenter + tests en même temps.
5. `graphify update .` si code modifié.
6. Security review si applicable.
7. Mettre à jour checklist du lot dans `docs/sprints/sprint-pod-shopify-wms.md`.
8. Commit uniquement si demandé ; sinon stopper après DoD local.

## Contrat sous-agent (copier tel quel à chaque délégation)

```
Résultat: …
Fichiers autorisés: …
Interdit: exploration hors liste ; secrets ; toucher flux métrage
Droits: read-only | write | tests
Invariants: public_id, org/customer scope, audit mouvements
Fin: tests listés verts ; CR ≤ 15 lignes (fichiers, décisions, dettes)
```

## Lots — rappel une ligne

| LOT | Focus |
|-----|--------|
| D0 | `PrintTechnique`, blanks, `Warehouse*` / `StorageLocation`, règles emplacement défaut |
| D1 | Overlay variante + recettes slots ; drawers staff + Shopify même contrat |
| A | `PodRipLot` + sync plat `02_rip/` + manifest |
| B | OF pièce + étiquettes |
| C | Poste pose scan DTF |
| E | Fulfillment Shopify OAuth/webhooks |
| F | Techniques non-DTF (export + poste) |
| G | Mouvements, picking trié bin, putaway retours |

## Branche / PR

- Branche dédiée : `feature/shopify-pod-wms` (ou `feature/shopify-pod-wms-<lot>` si split PR).
- 1 PR = 1 lot (préféré) ou stack de PR liées au même ADR.
- Titre PR : `feat(pod): lot <X> — <livrable court>`.
- Corps PR : Summary (3 bullets) + Test plan checklist + lien ADR/sprint.

## Sortie attendue (fin de session)

```
LOT: …
Plan OK / écarts: …
Fichiers: …
Tests: …
Security: n/a | passé | bloquant
Next: LOT=…
```

---

## Variante « plan seulement » (0 code)

Remplacer la mission par : *« Produis uniquement les plans D0→G au format template (≤40 lignes/lot). Aucun code. Signale dépendances inter-lots. »*
