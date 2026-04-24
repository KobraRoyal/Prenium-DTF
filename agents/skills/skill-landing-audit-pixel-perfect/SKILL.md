---
name: skill-landing-audit-pixel-perfect
description: Auditer une landing premium (conversion + UI) avec score /100, grilles d’audit et backlog P1–P3 réutilisable pour Codex.
---

# Skill — Audit landing premium (conversion + pixel-perfect)

## Quand utiliser ce skill
- Avant ou après une refonte de la home, d’une page services ou d’une landing marketing.
- Pour une revue systématique « premium ou non » sans ouvrir le périmètre métier (commandes, fichiers, prod, logistique, facturation).
- Pour produire un livrable standardisé : score, forces, faiblesses, corrections prioritaires, verdict.

## Étapes obligatoires
1. **Cadrage** : objectif de la page, audience, action principale attendue (une seule priorité).
2. **Passage complet** : parcourir la page du hero au footer (ou équivalent) sur desktop puis mobile.
3. **Audits thématiques** : exécuter les grilles ci-dessous (au minimum hero, CTA, crédibilité, différenciation, rythme visuel, mobile, conversion globale).
4. **Score /100** : attribuer une note par axe puis une note globale pondérée (voir critères de réussite).
5. **Backlog** : classer les actions en P1 (bloquant confiance ou conversion), P2 (impact fort), P3 (polish).
6. **Verdict** : décider si la landing est « premium » ou non, avec justification courte et réversible si P1 traités.

## Grille d’audit

### Landing globale (/100)
| Critère | Poids indicatif | Questions clés |
|--------|-----------------|----------------|
| Clarté immédiate | 20 % | Comprend-on l’offre en 5 s ? |
| Structure & flux | 15 % | Ordre des sections logique, pas de dispersion |
| Crédibilité | 20 % | Preuves, process, sobriété des promesses |
| Différenciation | 15 % | Pourquoi vous vs générique ? |
| Conversion (CTA) | 20 % | Libellés, placement, friction |
| Cohérence visuelle & mobile | 10 % | Rythme, spacing, responsive |

### Hero
- Message unique, bénéfice orienté client, pas jargon creux.
- Hiérarchie titre > sous-titre > CTA ; pas de concurrence entre trois messages égaux.
- CTA primaire évident ; secondaire seulement si utile.

### CTA
- Un objectif principal par viewport critique (au-dessus de la ligne de flottaison).
- Libellés verbes + résultat (pas « Envoyer » seul si on peut préciser).
- Répétition utile en bas de page sans spam.

### Crédibilité
- Preuves tangibles (process, délais, traçabilité, références sobres) alignées produit.
- Pas de promesse de sécurité ou de donnée qui relèverait du backend sans être vraie côté système.

### Différenciation
- Au moins un angle clair (qualité DTF, workflow, accompagnement pro, etc.).
- Éviter les listes d’adjectifs sans fait.

### Rythme visuel
- Spacing régulier, sections identifiables, pas de murs de texte.
- Hiérarchie typographique cohérente avec le design system.

### Mobile
- Lisibilité sans zoom, CTA accessibles, pas de chevauchement tap.
- Performance perçue : pas d’images hero disproportionnées sans lazy/gestion.

### Conversion (synthèse)
- Moins de sorties qu’entrées : un fil conducteur vers l’action.
- Réassurance au bon moment (avant décision, pas seulement en bas).

## Critères de réussite
- **Score global** : transparent (sous-scores + pondération ou justification qualitative si non chiffrée partout).
- **P1** : aucune contradiction grave avec l’offre ; pas de sur-promesse manifeste ; CTA et message hero compréhensibles mobile.
- **Verdict « premium »** : score global ≥ 75 **et** aucun P1 ouvert sur crédibilité ou clarté du hero.
- **Verdict « non premium »** : score < 60 **ou** P1 sur promesse trompeuse / confusion totale du hero / CTA invisibles mobile.

## Backlog de sortie (P1 / P2 / P3)
- **P1** : bloque la confiance ou la compréhension (hero flou, CTA manquant, contradiction forte, mobile cassé sur l’action principale).
- **P2** : amélioration forte (structure de sections, preuves, microcopy CTA, hiérarchie visuelle).
- **P3** : polish (espacements mineurs, illustrations, finesse typographique, animations discrètes utiles).

## Sortie finale obligatoire
1. **Score global** /100 (avec détail des axes ou sous-scores).
2. **Points forts** (3 à 5 bullets).
3. **Points faibles** (3 à 5 bullets).
4. **Corrections prioritaires** (P1 puis P2 ; P3 séparé).
5. **Verdict** : « landing premium » ou « non premium », une phrase de synthèse.

## Pièges à éviter
- Confondre « beau » et « crédible » : le premium tient aussi à la sobriété et aux faits.
- Optimiser le copy sans regarder le mobile : la conversion se joue souvent sur petit écran.
- Ajouter des garanties marketing non couvertes par le produit (risque décision DECISIONS_LOG / réputation).
- Déplacer des sujets sécurité ou permission vers le front pour « rassurer ».
- Refonte totale quand 3 à 5 corrections P1/P2 suffisent.

## Coordination agents
- Pour le fond conversion et messaging : invoquer **landing-conversion-agent**.
- Pour l’exécution visuelle et composants : invoquer **pixel-perfect-ui-agent** (et **frontend-agent** à l’implémentation).
