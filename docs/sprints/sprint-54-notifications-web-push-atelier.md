# Sprint 54 — Notifications Web Push Atelier

## Objectif

Notifier en direct les membres Atelier autorisés lorsqu'une commande entre dans
l'état `submitted`, y compris dans le centre de notifications de macOS, sans
application native et sans migration de la stack WSGI vers ASGI/WebSocket.

## Architecture retenue

- WSGI/Gunicorn reste le serveur HTTP de l'application.
- Django persiste un événement idempotent `workshop.order_submitted` dans la
  transaction métier et programme le fan-out après commit.
- Celery distribue les livraisons Web Push en ne transportant que des UUID
  publics.
- Le navigateur s'abonne explicitement via un Service Worker servi à la racine.
- Un polling HTMX de secours toutes les 20 secondes maintient la file Atelier à
  jour lorsque le Push est indisponible ; il s'arrête quand l'onglet est caché.

## Livré

- [x] Événement unique lors de la création standard et de la transmission B2B.
- [x] Protection contre une double transition concurrente `draft → submitted`.
- [x] Abonnements staff chiffrés avec clé dédiée versionnée.
- [x] Validation HTTPS, allowlist fournisseur et contrôle des IP publiques pour
      réduire le risque SSRF.
- [x] Revalidation des permissions Atelier lors du fan-out et de la livraison.
- [x] Quota configurable de cinq appareils actifs par membre par défaut.
- [x] Révocation et effacement immédiat des secrets à la déconnexion et à
      l'offboarding d'un membre Atelier.
- [x] Livraisons idempotentes, reprise des claims, retries et expiration des
      abonnements invalides.
- [x] Payload générique sans nom client, montant, note ou fichier.
- [x] Activation/désactivation depuis le dashboard Atelier, réduite à un seul
      bouton sur la ligne du fil d'Ariane (sans carte dédiée).
- [x] Notification système macOS et navigation vers `/staff/` au clic.
- [x] Rafraîchissement HTMX ciblé sans recréer le graphique Chart.js.
- [x] Feature flag désactivé par défaut et secrets VAPID uniquement via
      variables d'environnement.
- [x] Migration additive `notifications/0011_workshop_web_push.py`.

## Configuration de production

Renseigner une paire VAPID et une clé Fernet dédiées, puis activer le feature
flag. Les valeurs attendues sont documentées dans `.env.example`. Le site doit
être servi en HTTPS ; une recette réelle Safari/Chrome doit être faite sur le
domaine de production avant ouverture aux opérateurs.

La défense applicative refuse les redirections, les proxys d'environnement,
les IP non publiques et les changements de résolution détectés. En production,
elle doit être complétée par une règle réseau egress qui interdit les réseaux
privés, link-local et les endpoints de métadonnées : la bibliothèque HTTP peut
encore refaire une résolution DNS entre le dernier contrôle et l'ouverture du
socket.

## Validation

- [x] Suite globale : 1152 tests réussis, 3 ignorés après les correctifs
      sécurité.
- [x] Ciblage Web Push + architecture Portal : 63 tests réussis après la
      simplification de l'interface.
- [x] Ruff, syntaxe JavaScript et `manage.py check` conformes.
- [x] `makemigrations --check --dry-run` sans divergence.
- [x] Recette Playwright desktop 1440 px et mobile 375 px sans erreur console ni
      débordement.
- [x] Graphe Graphify actualisé.
- [ ] Recette Web Push réelle Safari/Chrome sur HTTPS avec les clés VAPID de
      production.

## Exploitation et limites

- Les événements et livraisons techniques sont conservés 90 jours.
- Le Push est distribué en *at-least-once* ; le tag UUID du navigateur assure la
  déduplication visible.
- Seules les nouvelles soumissions après activation produisent un événement ;
  aucun backfill n'est prévu.
- Le design actuel suppose un Atelier interne unique. Une organisation Atelier
  explicite devra être ajoutée avant toute exploitation multi-atelier.
