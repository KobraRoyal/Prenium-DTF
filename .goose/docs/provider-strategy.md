# Stratégie providers / modèles

## Recommandation principale
Utiliser **ACP providers** quand possible. La doc Goose indique que les anciens CLI providers (`claude-code`, `codex`, `gemini-cli`) sont **dépréciés** au profit des **ACP providers**, qui sont la “recommended replacement” et permettent aussi le passage des extensions Goose vers l’agent.

## Mix recommandé pour ce projet

### 1. Orchestration / planification
**Provider recommandé** : `codex-acp`  
**Modèle recommandé** : le meilleur modèle disponible dans ton environnement Goose pour la planification lourde.

Recommandation pragmatique selon tes options visibles :
- `gpt-5.4` : planification, arbitrages, cadrage, refonte métier
- fallback si indisponible côté ACP/Codex : `gpt-5.2-codex`

### 2. Implémentation complexe
**Provider recommandé** : `codex-acp`
- `gpt-5.4` ou `gpt-5.3-codex` si accessibles dans ton environnement
- sinon `gpt-5.2-codex`

### 3. Tâches simples / répétitives / non critiques
- `gpt-5.1-codex-mini`
- ou **Local Inference** (`unsloth/gemma-4-26B-A4B-it-GGUF:Q4_K_M`) pour
  - reformats,
  - copies,
  - résumés,
  - rédaction de docs simples,
  - triage mineur.

### 4. QA / review ciblée
- `gpt-5.4` pour security review et release review
- `gpt-5.1-codex-max` pour review approfondie si tu veux un agent dédié “reviewer”
- `gpt-5.1-codex-mini` pour lint / checklist / relectures courtes

## Règle de routage conseillée
- **Complexité haute** : `gpt-5.4`
- **Complexité moyenne** : `gpt-5.3-codex` ou `gpt-5.2-codex`
- **Complexité basse / massifiée** : `gpt-5.1-codex-mini`
- **Très bas coût / hors sécurité / hors métier** : modèle local

## Quand éviter le modèle local
Ne pas utiliser le modèle local pour :
- sécurité,
- permissions,
- logique métier sensible,
- migrations de données,
- architecture profonde,
- revue finale avant prod.

## Notes doc Goose
La doc Goose expose notamment :
- `GOOSE_PROVIDER`, `GOOSE_MODEL`,
- `GOOSE_PLANNER_PROVIDER`, `GOOSE_PLANNER_MODEL`,
- et recommande ACP providers (`codex-acp`, `claude-acp`, etc.) comme remplacement des CLI providers dépréciés.
