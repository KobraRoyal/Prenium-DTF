---
type: "query"
date: "2026-09-04T13:45:33.915482+00:00"
question: "IDENTIFICATION D' un client me remonte une information qu'il ne eut pas passer une commande de plus de 200 en quantité pour une commande au fichier regarde cela et identifie le probleme sans rein coder"
contributor: "graphify"
outcome: "useful"
source_nodes: ["OrderUpload", "OrderUploadService"]
---

# Q: IDENTIFICATION D' un client me remonte une information qu'il ne eut pas passer une commande de plus de 200 en quantité pour une commande au fichier regarde cela et identifie le probleme sans rein coder

## Answer

Expanded from graph vocabulary: [orderupload, inspection, quantity, quantities, limit, max, fichier]. Verification of the active B2B file-order UI found max=200 in portal/client/partials/order_project_item_quantity_field.html:3. The domain service only rejects quantities below 1 (services/projects.py:588-598), and the B2B model has only a positive quantity constraint (models.py:237,262). Thus the 200 cap is a client-side HTML constraint, not a server or database constraint. The legacy checkout upload form and OrderUploadService also accept values above 200, subject only to quantity >= 1.

## Outcome

- Signal: useful

## Source Nodes

- OrderUpload
- OrderUploadService