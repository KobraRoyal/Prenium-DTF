# Brancher une boutique Shopify de test (POD)

L’atelier local (`/staff/atelier/pod/`) peut maintenant installer une boutique réelle :
OAuth app Partners **ou** token Admin API d’une app custom. Le token est chiffré en base
(jamais loggé, suffixe 4 caractères seulement en UI).

## 1. App Shopify Partners

1. Créez une **Custom app** (ou app dev) dans [Partners](https://partners.shopify.com/).
2. Scopes : `read_products`, `read_orders` (ajoutez les fulfillments plus tard si besoin).
3. **Allowed redirection URL(s)** :
   `{PUBLIC_BASE_URL}/integrations/shopify/pod/oauth/callback/`
   En local Docker, `PUBLIC_BASE_URL` vient de `DJANGO_DEV_PUBLIC_BASE_URL`.
   OAuth exige une URL HTTPS publique : tunnel (ngrok, Cloudflare) vers `localhost:8080`.
4. Webhook fulfillment (enregistré automatiquement à l’install) :
   `{PUBLIC_BASE_URL}/webhooks/shopify/pod/fulfillment/` (topic `orders/create`).

## 2. Variables `.env` (jamais commitées)

```
SHOPIFY_POD_API_KEY=...
SHOPIFY_POD_API_SECRET=...
SHOPIFY_POD_SCOPES=read_products,read_orders
DJANGO_DEV_PUBLIC_BASE_URL=https://votre-tunnel.example
DJANGO_DEV_CSRF_TRUSTED_ORIGINS=https://votre-tunnel.example,http://localhost:8080
DJANGO_DEV_ALLOWED_HOSTS=localhost,127.0.0.1,votre-tunnel.example
```

Optionnel : `SHOPIFY_TOKEN_FERNET_KEY` (clé Fernet 32 octets url-safe). Sinon dérivée de `DJANGO_SECRET_KEY`.

Recréez / relancez `web` et `worker` après modification du `.env`.

## 3. Recette staff

Compte : `staff.ops@prenium.local` (perm. `pod.manage_pod_catalog`).

1. Hub atelier → **Boutiques**.
2. **OAuth** : domaine `xxx.myshopify.com` → installer → importer catalogue.
   **Sans tunnel** : collez un Admin API token (app custom de la boutique de test).
3. Catalogue → mapper les SKU en **POD** (recette + blank), sauf `staff_locked`.
4. Passez une commande test dans Shopify ; le webhook met la file RIP.
5. Lots → préparer DTF → OF / étiquette → pose / stocks.

HMAC : secret boutique **ou** `SHOPIFY_POD_API_SECRET` (apps OAuth).

## 4. Drive RIP (projection)

Le NAS `MEDIA_ROOT/pod_rip/.../02_rip/` plat reste la vérité RIP.

```
GOOGLE_DRIVE_SYNC_ENABLED=true
GOOGLE_DRIVE_SHARED_DRIVE_ID=...
GOOGLE_DRIVE_ROOT_FOLDER_ID=...
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=...   # même compte de service que le métrage
```

Après préparation de lot (si le flag est on) ou bouton **Synchroniser Drive** :
dossier `POD_RIP/{lot.code}/` sous la racine Drive (pas l’arbo commandes métrage).

## Hors scope

App block / thème Shopify embarqué : pas requis pour brancher et tester une boutique.
