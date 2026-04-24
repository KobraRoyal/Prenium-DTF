# Stratégie subagents

## Agents recommandés
- `project-manager`
- `architect`
- `backend`
- `frontend`
- `security`
- `qa`
- `ui-ux`

## Règle simple
- 1 orchestrateur
- 2 à 4 subagents en parallèle max
- ne pas lancer 7 agents pour une petite tâche

## Répartition recommandée
### Sprints métier
- architect
- backend
- security
- qa
- docs via orchestrateur

### Sprints UI/UX
- ui-ux
- frontend
- security
- qa

### Release prep
- project-manager
- security
- qa
- ui-ux
