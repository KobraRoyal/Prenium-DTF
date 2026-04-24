# Sessions, projets et continuité

## Sessions
Une session Goose conserve le contexte et l'historique de travail. Utilise :
- une session par sprint,
- ou une session par lot cohérent.

## Projects
La doc Goose explique que les **projects** suivent automatiquement les répertoires de travail avec :
- chemin absolu,
- dernière instruction,
- dernier accès,
- session associée.

### Commandes utiles
- `goose project` : reprendre le dernier projet
- `goose projects` : lister les projets

## Convention recommandée
### Nommage sessions
- `sprint-11-ux-polish`
- `sprint-12-release-prep`
- `billing-refactor-b2b`
- `ui-audit-landing-v2`

### Quand forker / repartir à neuf
Créer une nouvelle session quand :
- tu changes de sprint,
- tu changes de domaine métier,
- tu fais une review sécurité séparée,
- tu fais une recette finale.
