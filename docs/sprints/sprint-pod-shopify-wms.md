# Sprint POD — Shopify + atelier + WMS

**Branche** : `feature/shopify-pod-wms`  
**ADR** : `docs/architecture/ADR_SHOPIFY_POD_WMS.md`  
**Prompt maître** : `docs/prompts/PROMPT_SHOPIFY_POD_ORCHESTRATION.md`  
**Statut** : kickoff docs — code feature à venir lot par lot

## Objectif
Livrer l’app Shopify POD (mapping, RIP plat, pose, fulfillment) et le WMS emplacements, **sans** mélanger avec le flux DTF métrage existant.

## Règles transverses (tous lots)
- SRP / DRY : services applicatifs ; pas de logique dans vues / serializers / templates.
- Isolation : `Customer` / org scope serveur ; `public_id` ; jamais ID incrémental en URL.
- Audit : mouvements stock, écritures mapping, accept/reject fulfillment.
- UI : Tailwind + DaisyUI (`dui-`) + HTMX + Alpine ; shell atelier existant.
- Tests : service + permissions + accès croisé ; checklist sprint mise à jour.
- Graphify avant exploration large ; `graphify update .` après code.
- Orchestration : max 3 sous-agents, profondeur 1 ; Terra lecture / Sol écriture ; 1 writer par set de fichiers.

## Lots (ordre strict)

| Lot | Livrable | Apps / domaines | Vues clés | Skills |
|-----|----------|-----------------|-----------|--------|
| **D0** | Techniques + blanks + entrepôt (zones/bins) | `pod`/`catalog`/`inventory` | `/staff/atelier/pod/techniques/`, blanks, plan entrepôt | domain-db, inventory-wms, ui-ux |
| **D1** | `IdsVariantConfig` + drawers staff + Shopify (même contrat) | overlay variante, templates recettes | catalogue, drawer variante, app block | pim-oms, shopify, ui-ux, security |
| **A** | `PodRipLot` DTF : `02_rip/` plat + manifest | rip sync Drive/NAS | lot impression onglet DTF | pod-workflow |
| **B** | OF + étiquette par pièce / technique | PDF, labels | lot, postes | pod-workflow |
| **C** | Poste scan pose DTF | scan service | `/staff/atelier/pod/pose/dtf/` | pod-workflow, ui-ux |
| **E** | Fulfillment Shopify + webhooks | OAuth, HMAC, idempotence | boutiques, NEEDS_CONFIG | shopify, security |
| **F** | Broderie / subli (technique 2+) | export formats | `02_embroidery/`, poste broderie | pod-workflow |
| **G** | WMS ops : mouvements, picking, putaway retours | stock services | stocks, picking, putaway | inventory-wms, security |

## Template plan par lot (sortie agent — max ~40 lignes)

```markdown
## Lot X — plan
### Scope IN / OUT
### Entités & services (nouveaux | réutilisés)
### Fichiers autorisés (liste bornée)
### Migrations
### URLs / HTMX
### Tests (fichiers + cas min)
### Risques POD-xx
### DoD checklist
### Délégation (agents + fichiers exclusifs)
```

## DoD global d’un lot
- [ ] Code + migrations
- [ ] Tests verts ciblés
- [ ] Permissions / isolation vérifiées
- [ ] Audit si mutation sensible
- [ ] Doc sprint + ADR si décision ouverte tranchée
- [ ] `graphify update .`
- [ ] Security review si multi-tenant / webhook / fichier / stock

## Hors scope (ne pas toucher)
- Pricing B2B métrage, gang sheets, Sendcloud (sauf lien expédition POD plus tard)
- Refonte pilotage DTF métrage
- Décisions ouvertes ADR sans validation produit
