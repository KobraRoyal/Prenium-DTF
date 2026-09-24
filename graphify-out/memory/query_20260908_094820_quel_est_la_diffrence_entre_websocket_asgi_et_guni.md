---
type: "query"
date: "2026-09-08T09:48:20.373930+00:00"
question: "quel est la diffrence entre WebSocket/ASGI et Gunicorn/WSGI"
contributor: "graphify"
outcome: "useful"
source_nodes: ["asgi.py", "wsgi.py", "web-entrypoint.sh", "Redis"]
---

# Q: quel est la diffrence entre WebSocket/ASGI et Gunicorn/WSGI

## Answer

Expanded from original query via graph vocab: [asgi, wsgi, gunicorn, server, http, request, channel, redis]. WSGI est une interface requete-reponse HTTP synchrone; Gunicorn est ici le serveur qui charge config.wsgi. ASGI est une interface asynchrone qui supporte HTTP et les connexions longues; WebSocket est un protocole bidirectionnel persistant généralement servi via ASGI. Le projet utilise actuellement Nginx vers Gunicorn/WSGI. Web Push et polling HTMX peuvent être ajoutés sans migration ASGI; WebSocket nécessiterait un serveur ASGI, le routage et Redis/Channels.

## Outcome

- Signal: useful

## Source Nodes

- asgi.py
- wsgi.py
- web-entrypoint.sh
- Redis