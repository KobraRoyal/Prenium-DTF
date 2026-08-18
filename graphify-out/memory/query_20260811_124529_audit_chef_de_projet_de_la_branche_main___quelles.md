---
type: "audit"
date: "2026-08-11T12:45:29.993315+00:00"
question: "Audit chef de projet de la branche main : quelles améliorations prioriser ?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["Sprint 1 — Stabilisation Docker, migrations et qualité", "SECURITY_BASELINE.md", "HealthcheckService", "test_sendcloud_webhook.py", "ShipmentService", "GangSheetService", "ProductionWorkflowService"]
---

# Q: Audit chef de projet de la branche main : quelles améliorations prioriser ?

## Answer

Verdict: socle fonctionnel et richement testé, mais non prêt pour une release fiable. P0: rotation des secrets locaux exposés et sortie du fichier .env du dossier Dropbox; remettre GitHub Actions au vert et protéger main (16/16 exécutions distantes en échec malgré 617 tests locaux verts sur SQLite et PostgreSQL 16); rendre le Compose production immuable et supprimer les bind mounts qui masquent le contenu des images, notamment le dossier statique absent; corriger le PID Celery Beat persistant et valider les redémarrages. P1: sauvegarde/restauration avec RPO-RTO, durabilité des tâches Redis, observabilité et alertes, check --deploy sans warning, scans secrets/SAST/image, dépendances et images reproductibles. P2: refactorer les services de plus de 700-1200 lignes, séparer les files Celery, mesurer couverture et KPIs produit, consolider roadmap et statut. Forces: 617 tests, Ruff, migrations, pip-audit et npm audit verts, isolation tenant et services métier bien présents.

## Outcome

- Signal: useful

## Source Nodes

- Sprint 1 — Stabilisation Docker, migrations et qualité
- SECURITY_BASELINE.md
- HealthcheckService
- test_sendcloud_webhook.py
- ShipmentService
- GangSheetService
- ProductionWorkflowService