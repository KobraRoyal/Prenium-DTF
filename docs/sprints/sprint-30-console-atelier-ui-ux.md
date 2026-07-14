# Sprint 30 — Console Atelier UI/UX

## Objectif

Rendre la fiche commande staff immédiatement exploitable sur un poste Atelier : progression lisible, actions possibles sans ambiguïté, scan rapide, expédition conditionnée par le workflow et clôture comptable synthétique.

## Périmètre livré

- Fiche commande : synthèse enrichie, retour à la file et parcours métier numéroté conservant les onglets HTMX et les permissions.
- Production : progression de l’OF, références opérateur, transitions strictement limitées par le service central et historique récent.
- Scan Atelier : champ principal autofocus, raccourci vers l’OF courant, mode consultation seule selon les permissions et résultat ouvrant la commande reconnue.
- Expédition : état de préparation explicite, formulaire visible uniquement lorsque l’OF est prêt et l’opérateur autorisé, préremplissage depuis la fiche client, regroupement progressif des paramètres Sendcloud.
- Facturation : synthèse montant/mode/paiement/facture, action de rapprochement du virement et pièces secondaires repliables.
- Responsive : vues vérifiées sans débordement horizontal à 375 px ; animations neutralisées avec `prefers-reduced-motion`.

## Sécurité et traçabilité

- Aucun nouvel accès objet ni identifiant incrémental exposé.
- Les routes et contrôles de permission existants restent la source d’autorité.
- La création d’expédition n’est plus présentée aux rôles sans `shipping.create_shipment`.
- Les transitions proposées sont issues de `ProductionWorkflowService.allowed_transitions` ; le service conserve la validation et l’audit.
- Aucun lien direct vers les fichiers privés de facture ou d’étiquette n’a été ajouté.

## Fichiers principaux

- `backend/templates/portal/staff/order_detail.html`
- `backend/templates/components/order/order_tabs.html`
- `backend/templates/portal/staff/panels/{production,scan,shipping,billing}.html`
- `backend/static_src/css/components/workflow.css`
- `backend/apps/portal/views_staff_{production,shipping}.py`
- `backend/apps/production/services/workflow.py`
- `tests/ui/test_portal_ui.py`
- `tests/production/test_workflow_service.py`

## Checklist de validation

- [x] Les permissions restent vérifiées côté serveur.
- [x] Les transitions UI correspondent au workflow central.
- [x] Le rôle lecture seule ne voit pas une action d’expédition impossible.
- [x] Les valeurs saisies dans le formulaire d’expédition sont conservées après erreur.
- [x] Les champs d’expédition connus sont préremplis sans exposer d’autre client.
- [x] Build CSS et tests ciblés.
- [x] QA navigateur desktop et mobile 375 px.
- [x] Vérification des interactions HTMX et du focus scan.

## Hypothèses

- L’identité visuelle brutaliste claire reste la direction de marque du portail ; le lot la modernise sans introduire un thème sombre isolé.
- Le code de service Sendcloud reste une donnée opérateur tant qu’un catalogue de méthodes d’expédition n’est pas disponible côté backend.
