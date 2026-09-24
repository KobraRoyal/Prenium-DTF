---
type: "query"
date: "2026-09-08T09:26:10.510762+00:00"
question: "Planifier un système de notification Atelier en direct pour les nouvelles commandes, avec notification native macOS"
contributor: "graphify"
outcome: "useful"
source_nodes: ["OrderService", "Event", "Redis", "AtelierDashboardService", "notifications/tasks.py", "atelier-dashboard-batch.js"]
---

# Q: Planifier un système de notification Atelier en direct pour les nouvelles commandes, avec notification native macOS

## Answer

Expanded from original query via graph vocab: [atelier, workshop, commande, order, orders, notification, event, webhook, celery, redis, production, job]. Le dépôt dispose déjà du hook métier de soumission commande, de Celery, Redis, d'une app notifications e-mail et d'un dashboard Atelier HTMX. Il n'a ni Push API/service worker, ni WebSocket/SSE, et la production sert Django sous Gunicorn WSGI. Recommandation: événement Atelier persistant et idempotent à la soumission, fan-out Celery Web Push par abonnement staff autorisé, service worker pour notification macOS et message aux onglets ouverts, rafraîchissement HTMX ciblé, polling léger de secours. Garder WebSocket/ASGI hors MVP sauf besoin ultérieur de flux temps réel bidirectionnel.

## Outcome

- Signal: useful

## Source Nodes

- OrderService
- Event
- Redis
- AtelierDashboardService
- notifications/tasks.py
- atelier-dashboard-batch.js