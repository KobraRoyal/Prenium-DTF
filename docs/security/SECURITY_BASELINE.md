# Baseline sécurité — Prenium DTF / IDS Hub

Document de revue pour chaque release. Cocher explicitement les points vérifiés pour l’environnement cible (recette / production).

## 1. Isolation multi-tenant et permissions
- [ ] Séparation routes client (`/client/`, `api/client/`) et staff (`/staff/`, `api/staff/`) respectée
- [ ] Aucun accès objet par simple ID sans contrôle serveur (préférence `public_id` / scoping `Customer`)
- [ ] Tests d’accès croisé maintenus pour les domaines sensibles (commandes, fichiers, production, expédition)

## 2. Fichiers et médias
- [ ] Fichiers commande servis uniquement via vues autorisées (pas d’URL directe publique vers le stockage)
- [ ] Validation MIME / taille côté serveur alignée avec `ORDER_UPLOAD_*`

## 3. Secrets et configuration
- [ ] Aucun secret dans le dépôt ; variables d’environnement documentées pour le déploiement
- [ ] `DJANGO_SECRET_KEY` et mots de passe base uniques par environnement

## 4. Transport et cookies (Django)
Réglages de référence : `backend/config/settings/base.py` ; durcissement prod : `backend/config/settings/prod.py`.

| Sujet | Détail |
|--------|--------|
| HTTPS | `SECURE_SSL_REDIRECT` activé en prod ; `SECURE_PROXY_SSL_HEADER` pour reverse proxy |
| Cookies session / CSRF | `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` à `True` en prod |
| En-têtes | `SecurityMiddleware`, `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_BROWSER_XSS_FILTER`, `X_FRAME_OPTIONS = DENY`, `SECURE_REFERRER_POLICY` |
| CSRF | `CsrfViewMiddleware` ; `DJANGO_CSRF_TRUSTED_ORIGINS` renseigné pour l’origine HTTPS réelle |

## 5. Authentification et abus — login
- [ ] **Rate limiting** : `LoginRateLimitMiddleware` sur les POST `/login/` (clé cache par IP)
- [ ] Variables : `LOGIN_RATE_LIMIT_MAX_ATTEMPTS`, `LOGIN_RATE_LIMIT_WINDOW_SECONDS` (voir `base.py`)
- [ ] Réponse **HTTP 429** avec message sobre si limite dépassée
- [ ] **Journalisation** : log applicatif `login_rate_limited` à chaque refus ; **audit** `security.login_rate_limited` (une fois par fenêtre et par IP au premier dépassement) dans `AuditLogEntry`

## 6. Audit métier
- [ ] Mutations sensibles couvertes par `apps.auditlog` (commandes, paiements, production, uploads, etc.) selon le périmètre livré
- [ ] Consultation des journaux d’audit staff / admin conforme aux rôles

## 6 bis. Demandes d’accès et invitations

- [ ] La soumission prospect ne crée ni utilisateur ni tenant actif
- [ ] La décision exige `prospects.review_prospectprofile`
- [ ] Les liens de vérification et d’invitation sont signés, versionnés et expirants
- [ ] Une invitation acceptée ou révoquée n’est plus réutilisable
- [ ] Un compte existant doit s’authentifier avec l’adresse invitée
- [ ] Les actions d’équipe sont rescopées par organisation et couvertes par des tests d’accès croisé
- [ ] `PUBLIC_BASE_URL` utilise l’origine HTTPS publique réelle

## 7. Exploitation
- [ ] Sauvegardes base et médias (runbook déploiement)
- [ ] Politique de rétention des logs et des données personnelles alignée avec le métier
- [ ] MFA staff : prévu hors périmètre actuel ; à réévaluer avant exposition large

## Scénarios de test récurrents
- Accès à la commande ou au fichier d’un autre client
- Contournement par URL directe ou requête API forgée
- Élévation de privilège (client → staff)
- Transition de statut ou mutation non autorisée
- Rafale de POST login → **429** puis stabilité du reste du site
- Invitation d’un tenant présentée sur la route équipe d’un autre tenant
- Réutilisation d’une invitation après acceptation ou révocation

## Références code
- Middleware login : `apps/accounts/middleware.py`
- Tests rate limit : `tests/accounts/test_login_rate_limit.py`
