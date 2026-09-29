# Brancher une boutique Shopify de test (POD)

L’atelier local (`/staff/atelier/pod/`) peut maintenant installer une boutique réelle :
OAuth app Partners **ou** token Admin API d’une app custom. Le token est chiffré en base
(jamais loggé, suffixe 4 caractères seulement en UI).

## 1. App Shopify Partners

1. Créez une **Custom app** (ou app dev) dans [Partners](https://partners.shopify.com/).
2. Scopes par défaut pour une nouvelle connexion : `read_products`, `read_orders`. Cette app pilote la production POD ; le connecteur direct Shopify ↔ Sendcloud prend en charge l’expédition et le fulfillment. Une boutique déjà autorisée peut garder d’anciens scopes fulfillment jusqu’à une réautorisation contrôlée : inspecter `oauth_scopes`, sans forcer de reconnexion en masse.
3. **Allowed redirection URL(s)** :
   `{PUBLIC_BASE_URL}/integrations/shopify/pod/oauth/callback/`
   En local Docker, `PUBLIC_BASE_URL` vient de `DJANGO_DEV_PUBLIC_BASE_URL`.
   OAuth exige une URL HTTPS publique : tunnel (ngrok, Cloudflare) vers `localhost:8080`.
4. Webhooks (enregistrés automatiquement à l’install) :
   `{PUBLIC_BASE_URL}/webhooks/shopify/pod/fulfillment/`
   Topics : `orders/create`, `orders/updated`, `orders/cancelled`.
   - **create / updated** : upsert file RIP (qty sync, plancher = étiquettes picking déjà émises).
   - **cancelled** : retire les lignes encore `QUEUED` ; si déjà en lot, gèle les pièces (`ISSUE`), même déjà posées ou validées QC, sans supprimer l’OF ni l’historique.

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

Compte : `staff.ops@prenium.local` (perm. `pod.manage_pod_catalog` + `pod.operate_pod_production`).

Seed local Drive HD / parcours atelier :

```
docker compose exec web sh -lc 'cd /app/backend && python manage.py migrate pod'
docker compose exec web sh -lc 'cd /app/backend && python manage.py seed_pod_wms'
```

La commande lit le fichier unique du dossier `GOOGLE_DRIVE_POD_HD_SOURCE_FOLDER_ID`,
l’importe en `READY`, mappe `TEE-BLK-M` (toutes zones autorisées), puis crée :
`SO-SEED-QUEUE` (À produire), `SO-SEED-PICK` (session réservée),
`SO-SEED-POSE` (lot RIP + waiting_press), `SO-SEED-QC` (pressed pour QC).
Idempotente : un second `seed_pod_wms` réutilise les mêmes commandes.

Checklist manuelle après seed :

1. Hub → `SO-SEED-QUEUE` visible « À produire » ; PDF picking / étiquettes.
2. Confirmer le prélèvement de `SO-SEED-PICK` (scan pièce + bin `A-01-01-A`).
3. Lots RIP → préparer / vérifier export DTF issu du PDF Drive.
4. Pose → scan `SO-SEED-POSE` (waiting_press) → marquer pressé.
5. QC → pièce `SO-SEED-QC` déjà pressed → conforme / refus avec motif.
6. Stocks → mouvements blanks + finis démo (`TEE-WHT-M-FIN`).
7. Catalogue → drawer mapping `TEE-BLK-M` lié au fichier Drive HD unique.

1. Hub atelier → menu **POD** → **Boutiques**.
2. Saisir le nom de la boutique (`ma-boutique`) puis **Continuer sur Shopify**.
   Le marchand approuve les accès. Au retour, le catalogue est importé et les webhooks
   `orders/create`, `orders/updated`, `orders/cancelled` sont enregistrés.
   **Sans OAuth** : ouvrir « J’ai déjà un token d’app custom » et coller le token Admin API.
3. Catalogue → mapper les SKU en **POD**.
4. Une commande test Shopify alimente **À produire**.
5. Générer picking + Zebra, puis **préparer le lot DTF** (impression HD) et **prélever le blank** dans l’ordre atelier qui convient (impression avant ou après prélèvement). La pose exige les deux : lot DTF lancé **et** sortie de stock confirmée. Ensuite confirmer la pose et contrôler chaque pièce dans **QC** (`/staff/atelier/pod/controle-qualite/`). Un refus requiert un motif ; la reprise après correction est explicite et auditée.
6. Après le dernier QC conforme de **toutes** les lignes POD d’une commande Shopify identifiée, vérifier l’avis « Production POD terminée » dans le poste QC et, si activées, les alertes navigateur de l’atelier interne. Un nouveau passage à QC complet après ajout d’une ligne produit un nouvel avis ; la liste n’affiche que le dernier avis courant par commande. Tester aussi commande partielle, refusée et annulée : aucune annonce prématurée. L’atelier ne crée ni colis ni étiquette ici.

HMAC : secret boutique **ou** `SHOPIFY_POD_API_SECRET` (apps OAuth). L’identifiant de livraison `X-Shopify-Webhook-Id` est obligatoire et dédupliqué globalement, indépendamment des headers boutique/topic. En production, la livraison validée est conservée dans `ShopifyWebhookReceipt` avant le `200`, puis le worker traite l’inbox. Celery Beat exécute `pod.recover_shopify_pod_inbox` toutes les 60 secondes (configurable par `POD_WEBHOOK_RECOVERY_INTERVAL_SECONDS`) ; `pending` et `failed` sont rejoués avec backoff plafonné à une heure. Surveiller le nombre de reçus `failed`, leur `last_error` et l’âge du plus ancien `pending`. Une variante inconnue n’est jamais acquittée comme traitée : synchroniser le catalogue puis laisser la reprise rejouer le reçu. Le corps brut est effacé du reçu dès que le traitement réussit. Le `200` signifie « persisté », pas « en production ».

Avant une mise en production d’une boutique existante, affecter explicitement son `Customer` depuis l’écran staff Boutiques et vérifier les versions HD `READY` dans le drawer. Aucun rattachement client n’est déduit du domaine Shopify. Auditer aussi les anciens `webhook_secret` en base : d’anciennes installations peuvent y contenir une copie en clair d’un précédent secret OAuth. Identifier les boutiques concernées, retirer cette valeur et réenregistrer/faire tourner leurs webhooks avec le secret actuel ; ne pas purger automatiquement une valeur dont la provenance est inconnue.

L’export RIP DTF automatique accepte les originaux PNG, PDF, AI, EPS et TIF/TIFF validés, sans conversion ; les autres techniques conservent leur politique PNG actuelle. Les webhooks Shopify avec `id` commande et `id` de chaque ligne permettent deux lignes POD de même variante ; sans ces IDs, le mode historique reste strict et refuse cette ambiguïté. Les anciens work items ne sont pas rattachés automatiquement à une commande identifiée.

Le flux applicatif POD s’arrête à la notification interne de fin de production après QC. Aucun colisage, étiquette Sendcloud POD, acceptation de fulfillment Shopify ou tracking ne doit être ajouté à ce parcours : ces étapes appartiennent à la connexion Shopify ↔ Sendcloud. La validation en staging avec une boutique réelle, PostgreSQL et NAS/Drive/RIP reste obligatoire avant production ; vérifier séparément la connexion Shopify ↔ Sendcloud dans son propre environnement.

Pour la recette des migrations sur une base PostgreSQL **jetable**, utiliser `PYTHONPATH=backend pytest --ds=config.settings.test_postgres` ; cette configuration conserve le comportement de test Celery synchrone. Ne pas forcer `pod.0016` sur une base ayant déjà une table `pod_shopifyorder` hors historique Django : inventorier le schéma et les données, puis choisir une réconciliation contrôlée. Un `migrate --fake` ou une suppression de table masquerait une divergence de modèle. Sur la base Docker locale du 25/09/2026, les anciennes tables vides ont été conservées dans le schéma `legacy_pod_reconcile_20260925` après sauvegarde complète ; la table ORM actuelle est `public.pod_podshopifyorder`. Ne pas supprimer ce schéma d'archive ni l'ancienne FK `pod_podripworkitem.order_line_id` sans migration et contrôle de données dédiés. Les détails et le checksum de la sauvegarde figurent dans `docs/sprints/sprint-pod-shopify-wms.md`.

## 4. Drive RIP (projection)

Le NAS `MEDIA_ROOT/pod_rip/<PICK-session>/<technique.rip_directory>/` plat reste la vérité RIP.
Exemple DTF : `pod_rip/PICK-260929-ABCD/02_rip/*.pdf` — uniquement les visuels HD.
Pas de `00_manifest/`, `03_of/` ni `04_labels/` : la liste picking A4 et les étiquettes Zebra
sont générées à la création de session picking et suivent la pièce jusqu’à pose/QC.

### Bibliothèque HD POD (source)

Le dossier Drive source est configuré par `GOOGLE_DRIVE_POD_HD_SOURCE_FOLDER_ID`. Le sélecteur du mapping est réservé aux responsables du catalogue POD et ne doit lire que les fichiers binaires de ce dossier exact, vérifié comme enfant de la racine du Drive partagé. Le navigateur ne choisit jamais un dossier ou une URL arbitraire. La recette conserve le lien Drive et une provenance contrôlée ; un fichier sélectionné n'est imprimable qu'après import d'une version locale immuable, liée explicitement au `Customer` de la boutique et analysée `READY`. Le fichier original Drive reste inchangé. Pour DTF, PNG, PDF, AI, EPS et TIF/TIFF mono-page sont acceptés après validation ; l'original est copié tel quel vers le RIP avec sa vraie extension. Les PDF/AI/EPS doivent obligatoirement provenir de cette bibliothèque Drive interne : un upload client, même READY, n'est pas sélectionnable pour ces formats et ne passe pas au RIP. Les autres techniques restent sur leur format autorisé, sans conversion implicite. Un avertissement qualité ou un document multipage bloque la production. Le drawer affiche `en cours`, `bloqué` ou `prêt` et peut réactualiser son état sans recharger la page. La liste du drawer est bornée à 1 000 fichiers ; au-delà, utiliser une recherche paginée dédiée avant d'ouvrir ce volume à l'atelier.

Celery Beat vérifie chaque minute les imports `PENDING` depuis plus de 2 minutes et les imports `IMPORTING` sans activité depuis plus de 16 minutes, uniquement s'ils sont encore liés à une recette. Une lease Redis de 30 minutes par source évite de republier en boucle si les workers sont arrêtés ; elle est libérée si la publication échoue. Cela couvre l'échec initial de publication Celery et la perte d'un worker ; l'import reste idempotent et les échecs de validation `FAILED` ne sont pas relancés en boucle.

Le dossier de production Drive distinct sera configuré par `GOOGLE_DRIVE_POD_PRODUCTION_FOLDER_ID` après décision de son emplacement. Tant qu'il n'est pas fourni et validé, **aucune copie/renommage de production Drive ne doit partir automatiquement**. Ne jamais substituer `Commandes/01_Production` (commandes métrage) ni déduire une commande POD d'un simple numéro texte.

```
GOOGLE_DRIVE_SYNC_ENABLED=true
GOOGLE_DRIVE_SHARED_DRIVE_ID=...
GOOGLE_DRIVE_ROOT_FOLDER_ID=...
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=...   # même compte de service que le métrage
GOOGLE_DRIVE_POD_HD_SOURCE_FOLDER_ID=...   # dossier bibliothèque HD POD, enfant direct de la racine partagée
GOOGLE_DRIVE_POD_PRODUCTION_FOLDER_ID=...  # à fournir avant activation des copies de production
POD_DRIVE_HD_MAX_BYTES=104857600         # limite d'import des originaux HD (100 Mio par défaut)
POD_DRIVE_HD_RECOVERY_INTERVAL_SECONDS=60 # reprise des imports bloqués
```

À la génération d’une session picking (`POD_AUTO_RIP_ON_PICK_SESSION=True` par défaut), le backend
prépare le lot DTF (NAS) puis pousse les visuels vers Drive (`pod.prepare_pick_session_rip_and_drive`).
Dossier opérateur : `POD_RIP/{session_picking}/02_rip/` sous la racine Drive — relance possible via
**Préparer lot DTF** ou **Synchroniser Drive** si besoin.

Le tableau **Suivi** (`/staff/atelier/pod/suivi/`) agrège l’avancement des sessions (prélèvement →
impression DTF → pose → QC) avec un CTA vers le poste concerné. Les écrans **Lots RIP** restent
disponibles en diagnostic (Réglages), hors nav production, pour limiter la charge inutile.

## Hors scope

App block / thème Shopify embarqué : pas requis pour brancher et tester une boutique.
