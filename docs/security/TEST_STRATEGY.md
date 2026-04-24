# Stratégie de tests

## Pyramide
- tests unitaires : services métier, permissions, transitions
- tests intégration : API, DB, Celery, intégrations mockées
- tests e2e : parcours client et opérateur
- smoke tests : déploiement et santé app

## Règles
- toute feature métier inclut ses tests
- toute feature sécurité inclut des tests négatifs
- toute intégration externe est mockée en CI
- tout bug critique donne lieu à un test de non-régression
