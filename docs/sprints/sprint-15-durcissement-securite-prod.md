# Sprint 15 — Durcissement sécurité production

## Objectif
Réduire les abus (brute-force login, scraping) et renforcer la traçabilité sans casser l’UX atelier.

## Périmètre (itérations)
- Rate limiting **POST `/login/`** par IP (cache Redis / LocMem selon settings).
- Paramètres : `LOGIN_RATE_LIMIT_MAX_ATTEMPTS`, `LOGIN_RATE_LIMIT_WINDOW_SECONDS`.
- Réponse HTTP **429** avec message sobre.
- Poursuite : revue permissions, audit renforcé sur mutations sensibles, headers sécurité (déjà partiels).

## Hors périmètre
- WAF cloud externe.
- MFA complète staff (préparation déjà en décision).

## Définition de done
- [x] Middleware `LoginRateLimitMiddleware` (POST `/login/`) + tests.
- [x] Checklist `docs/security/SECURITY_BASELINE.md` alignée sur le code (cookies, en-têtes, rate limit, audit login).
- [x] Test limite atteinte (HTTP 429).
- [x] Audit `security.login_rate_limited` + log warning sur dépassement (première entrée audit par fenêtre / IP).
