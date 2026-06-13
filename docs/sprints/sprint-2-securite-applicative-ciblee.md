# Sprint 2 — Sécurité applicative ciblée

## Ticket SPRINT-2.1 — Durcir validation des uploads

## Objectif

Réduire la confiance accordée au `content_type` déclaré par le navigateur en vérifiant la signature réelle des fichiers acceptés et en refusant explicitement les SVG.

## Fichiers modifiés

- `backend/apps/uploads/services/validation.py`
- `backend/config/settings/base.py`
- `tests/uploads/mime_fixtures.py`
- `tests/uploads/test_upload_service.py`
- `tests/uploads/test_upload_api.py`
- `docs/sprints/sprint-2-securite-applicative-ciblee.md`

## Résumé technique

Le service de validation inspecte désormais les premiers octets du fichier avant l’enregistrement :

- PDF : signature `%PDF-`
- PNG : signature PNG
- JPEG : signature `FF D8 FF`
- TIFF : signatures little-endian / big-endian
- PSD : signature `8BPS`
- AI : signatures PostScript ou PDF compatibles Illustrator

Les fichiers `application/octet-stream` ne sont plus tolérés que pour `.ai`, `.psd`, `.tif` et `.tiff`, puis recatégorisés vers un MIME canonique avant contrôle de signature.

Les fichiers SVG sont refusés explicitement, même si le navigateur les annonce comme `image/svg+xml` ou si l’extension est `.svg`.

Les refus sont journalisés côté backend avec un motif explicite.

## Commandes Docker de validation

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/uploads'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/uploads tests/uploads'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/uploads tests/uploads'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail http://localhost:8080/healthz/
```

## Résultat attendu

- Un fichier dont le contenu ne correspond pas au type déclaré est refusé.
- Les SVG sont refusés.
- Les formats binaires métier légitimes PDF/PNG/JPEG/TIFF/PSD/AI restent acceptés si leur signature est valide.
- Les routes uploads API continuent de répondre en `400` avec un message explicite sur les cas rejetés.

## Résultats de validation observés

- `docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/uploads'` : OK, 50 tests passants.
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/uploads tests/uploads'` : OK.
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/uploads tests/uploads'` : OK.
- `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` : OK.
- `curl --fail http://localhost:8080/healthz/` : OK.

## Risques restants

- Certains exports Illustrator atypiques peuvent nécessiter un ajustement si leur signature diffère des cas actuellement couverts.
- Le refus des SVG peut nécessiter une communication produit si des clients en utilisaient déjà.
- La journalisation backend existe, mais aucun tableau de bord dédié aux refus upload n’est encore en place.

## Éléments reportés

- Stratégie alternative “stocker SVG en attachment seulement, jamais inline”.
- Durcissement du endpoint PayPal interne.
- Clarification IP proxy / rate-limit login.

## Message de commit recommandé

```text
security: validate upload signatures and reject svg
```

## Ticket SPRINT-2.2 — Durcir endpoint PayPal interne

## Objectif

Réduire le risque d’appel frauduleux sur l’endpoint interne de confirmation PayPal avec une comparaison constante du jeton, une limitation des refus et une journalisation explicite.

## Fichiers modifiés

- `backend/apps/billing/views.py`
- `backend/config/settings/base.py`
- `tests/billing/test_billing_api.py`
- `docs/sprints/sprint-2-securite-applicative-ciblee.md`

## Résumé technique

L’endpoint `api/backend/paypal/capture/` est durci sur trois axes :

- comparaison du header `X-Internal-Token` avec `secrets.compare_digest`
- journalisation des refus de jeton avec adresse IP auditée et motif (`missing_provided_token`, `invalid_token`, `missing_expected_token`)
- limitation par IP des tentatives invalides via le cache Django

Le calcul de l’IP privilégie `X-Real-IP` ou `REMOTE_ADDR`, et ne fait confiance à `X-Forwarded-For` que si la configuration l’autorise explicitement.

## Commandes Docker de validation

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/billing'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/billing tests/billing'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/billing tests/billing'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail http://localhost:8080/healthz/
```

## Résultat attendu

- Un token absent ou invalide est refusé.
- Les refus sont tracés en audit avec un motif exploitable.
- Les tentatives invalides répétées aboutissent à une réponse `429`.
- Le flux de capture valide reste inchangé.

## Résultats de validation observés

- `docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/billing'` : OK, 15 tests passants.
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/billing tests/billing'` : OK.
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/billing tests/billing'` : OK.
- `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` : OK.
- `curl --fail http://localhost:8080/healthz/` : OK.

## Risques restants

- Ce durcissement repose toujours sur un secret partagé statique ; une signature HMAC ou un webhook PayPal natif serait plus robuste.
- La limitation est locale au cache applicatif courant et dépend donc de la stratégie Redis/cache en production.
- L’allowlist réseau ou proxy dédié n’est pas encore traitée.

## Éléments reportés

- Clarification IP proxy / rate-limit login.
- Évolution vers un webhook PayPal signé.

## Message de commit recommandé

```text
security: harden internal paypal capture endpoint
```

## Ticket SPRINT-2.3 — Clarifier IP proxy et rate-limit login

## Objectif

Supprimer la confiance implicite dans `X-Forwarded-For` pour le rate-limit login et documenter le modèle de confiance proxy.

## Fichiers modifiés

- `backend/apps/accounts/middleware.py`
- `backend/config/settings/base.py`
- `.env.example`
- `tests/accounts/test_login_rate_limit.py`
- `docs/sprints/sprint-2-securite-applicative-ciblee.md`

## Résumé technique

Le middleware de rate-limit login ne fait plus confiance à `X-Forwarded-For` par défaut.

Le calcul de l’IP suit désormais cet ordre :

- `X-Forwarded-For` uniquement si `LOGIN_RATE_LIMIT_TRUST_X_FORWARDED_FOR=True`
- sinon `X-Real-IP`
- sinon `REMOTE_ADDR`

Cette règle est cohérente avec la configuration Nginx du projet, qui transmet déjà `X-Real-IP`.

## Commandes Docker de validation

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/accounts/test_login_rate_limit.py'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/accounts tests/accounts/test_login_rate_limit.py'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/accounts tests/accounts/test_login_rate_limit.py'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail http://localhost:8080/healthz/
```

## Résultat attendu

- Le rate-limit login reste actif.
- Un header `X-Forwarded-For` forgé n’influence pas le rate-limit tant que le réglage dédié n’est pas activé.
- Le comportement derrière un proxy de confiance peut être activé explicitement par configuration.

## Résultats de validation observés

- `docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/accounts/test_login_rate_limit.py'` : OK, 4 tests passants.
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/accounts tests/accounts/test_login_rate_limit.py'` : OK.
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/accounts tests/accounts/test_login_rate_limit.py'` : OK.
- `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` : OK.
- `curl --fail http://localhost:8080/healthz/` : OK.

## Risques restants

- En présence de plusieurs proxies, une stratégie `X-Forwarded-For` plus avancée peut être nécessaire.
- Cette PR documente la confiance proxy côté application, mais ne met pas encore en place d’allowlist réseau ou de `real_ip` Nginx avancé.

## Éléments reportés

- Durcissement Nginx / `real_ip` avancé.
- Documentation ops plus détaillée pour les déploiements multi-proxy.

## Message de commit recommandé

```text
security: harden login client ip handling
```
