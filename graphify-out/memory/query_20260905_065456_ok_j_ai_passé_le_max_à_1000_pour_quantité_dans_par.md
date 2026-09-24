---
type: "query"
date: "2026-09-05T06:54:56.217589+00:00"
question: "ok j'ai passé le max à 1000 pour quantité dans partial_project_item_quantity_fireld.html pour qu'il soit pris en compte dans docker il faut le relancer ?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["web-entrypoint.sh"]
---

# Q: ok j'ai passé le max à 1000 pour quantité dans partial_project_item_quantity_fireld.html pour qu'il soit pris en compte dans docker il faut le relancer ?

## Answer

Expanded graph tokens: [docker, compose, build, reload, template, volume, web]. The local compose file bind-mounts the repository into /app and enables GUNICORN_RELOAD, so the template change appears without a container restart; refresh the browser. The production compose file does not mount the app source and the Dockerfile copies templates into the image, so rebuild and recreate only web with docker compose -f docker-compose.prod.yml up -d --build web (or docker compose up -d --build web when that file is deployed as docker-compose.yml). No collectstatic or nginx restart is required for this HTML-only template change.

## Outcome

- Signal: useful

## Source Nodes

- web-entrypoint.sh