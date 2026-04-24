# Sprint 09 — Frontend produit : espace client + backoffice staff moderne

## Objectif
Livrer une vraie surface UI Django templates + HTMX, moderne, sobre et responsive,
en conservant la securite backend existante et sans endpoint monolithique riche.

## Perimetre livre

### Surface client
- [x] dashboard client simple
- [x] liste commandes
- [x] detail commande lisible
- [x] bloc uploads
- [x] bloc inspection
- [x] bloc production (niveau client, sans details staff sensibles)
- [x] bloc shipping (niveau client scope)

### Surface staff
- [x] dashboard staff simple
- [x] fiche commande consolidee
- [x] panneau production
- [x] panneau uploads / inspections
- [x] panneau Drive sync
- [x] panneau shipping
- [x] panneau scan atelier

## Choix d'implementation
- nouvelle app UI dediee `apps.portal`
- separation stricte des routes:
  - client: `/client/...`
  - staff: `/staff/...`
- detail commande staff compose par panneaux HTMX, pas de mega-vue backend
- reutilisation des services existants (`orders`, `uploads`, `production`, `shipping`)
- aucun transfert de logique de permissions vers le front

## Hors perimetre confirme
- PayPal / facturation
- redesign marketing global
- refonte architecture front
- nouvel agregat backend metier

## Validations executees
- [x] tests UI portail client/staff et separation de scope
- [x] non-regression permissions client/staff sur routes portail
- [x] etats vides/pages chargees verifies sur ecrans principaux
- [x] stabilisation shipping API testee (contrat aligne, tests verts)
- [x] commande seed recette manuelle disponible

## Stabilisation post-livraison
- correction minimale dans `tests/shipping/test_shipment_api.py` pour aligner:
  - payload create shipment
  - fake gateway
  - assertions sur le schema JSON shipping actuel
- resultat: plus d'echec residuel shipping sur la suite ciblee

## Micro-lot final UX/auth portail (pre-paiement)
- ajout d'une entree de connexion portail dediee: `/login/`
- redirection anonyme des routes client/staff vers login portail (au lieu de `/admin/login/`)
- redirection post-login basee sur le scope utilisateur:
  - staff autorise -> dashboard staff
  - utilisateur client -> dashboard client
- P1 UX appliques:
  - formulaire creation expedition masque si shipment deja `created`
  - message bloc production client clarifie
  - indicateur de chargement HTMX global plus visible

## Seed data recette
- commande: `python manage.py seed_sprint09_recipe`
- reset complet seed: `python manage.py seed_sprint09_recipe --reset`
- mot de passe de tous les comptes seed: `pass1234`
- comptes crees:
  - `admin@prenium.local`
  - `staff.ops@prenium.local`
  - `staff.limited@prenium.local`
  - `client.a.owner@prenium.local`
  - `client.a.member@prenium.local`
  - `client.b.owner@prenium.local`
  - `hybrid.ops.client@prenium.local`

## Checklist de cloture
- [x] code implemente
- [x] tests ajoutes
- [x] permissions verifiees
- [x] docs mises a jour
