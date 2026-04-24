# Stratégie subagents / agents spécialisés

## Agents recommandés
### 1. architecture-agent
Responsable :
- structure repo
- frontières de domaines
- services / apps Django
- décisions techniques

### 2. security-agent
Responsable :
- permissions objet
- accès fichiers
- secrets
- revues sécurité
- tests d’accès croisé

### 3. backend-agent
Responsable :
- modèles
- services métier
- APIs
- tâches Celery
- intégrations

### 4. frontend-agent
Responsable :
- design system
- pages front-office
- composants backoffice
- responsive et états UI

### 5. qa-agent
Responsable :
- tests unitaires
- tests intégration
- tests e2e
- checklists qualité

### 6. landing-conversion-agent (Codex)
Fichier : `.agents/subagents/landing-conversion-agent.md`  
Responsable : audit conversion landing (hero, promesse, structure, réassurance, différenciation, CTA), hors métier backend.

### 7. pixel-perfect-ui-agent (Codex)
Fichier : `.agents/subagents/pixel-perfect-ui-agent.md`  
Responsable : exigence UI/UX (spacing, hiérarchie, responsive, états, cohérence CTA), sans logique métier ni permissions front.

## Règles
- chaque agent travaille dans son périmètre
- toute décision transverse remonte dans les docs d’architecture
- toute feature sensible passe par relecture du security-agent
