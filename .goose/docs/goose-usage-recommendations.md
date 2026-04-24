# Recommandations d'usage Goose pour ce projet

## Pattern principal
Utiliser le pattern **RPI** recommandé par la doc Goose :
1. Research
2. Plan
3. Implement
4. Iterate si nécessaire

## Quand utiliser des subagents
Les subagents sont utiles pour :
- architecture,
- sécurité,
- frontend,
- backend,
- QA,
- UX/UI review.

## Quand utiliser des recipes
Utiliser des recipes pour :
- lancer un sprint,
- stabiliser un sprint,
- lancer une review sécurité,
- faire une recette navigateur,
- faire une release checklist.

## Quand utiliser headless
Utiliser `goose run` / headless pour :
- validations répétables,
- CI locale,
- exécution de recipe,
- checklists automatiques.

## Quand utiliser Playwright CLI skill
Pour :
- recette UI réelle,
- génération de tests browser,
- smoke tests de tunnel de commande.
