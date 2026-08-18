---
type: "query"
date: "2026-08-11T12:04:21.460794+00:00"
question: "POURQUOI SERVICE DOCKER BEAT 1 BUG"
contributor: "graphify"
outcome: "useful"
source_nodes: ["beat-entrypoint.sh", "celery.py", "Redis"]
---

# Q: POURQUOI SERVICE DOCKER BEAT 1 BUG

## Answer

Expanded from original query via graph vocab: [beat, celery, docker, compose, entrypoint, redis, schedule, task, worker, health, migration]. Le conteneur Beat boucle avec le code 73 parce que /tmp/celerybeat.pid survit au redémarrage du même conteneur et contient PID 1. L'entrypoint réutilise ce pidfile sans supprimer un fichier obsolète, tandis que restart unless-stopped relance le conteneur. Ce défaut concerne le planificateur périodique, pas l'exécution immédiate des webhooks par worker.

## Outcome

- Signal: useful

## Source Nodes

- beat-entrypoint.sh
- celery.py
- Redis