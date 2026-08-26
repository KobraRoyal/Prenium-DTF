# Sprint 37 — Remise dégressive sur volume mensuel

## Objectif

Permettre à l’Atelier de définir, pour chaque client en encours, des paliers de volume mensuel en
mètres linéaires et un pourcentage de remise. Le meilleur palier atteint applique son taux à
**tout le DTF éligible du mois civil**, et pas seulement à la tranche supérieure.

## Règles livrées

- [x] grille propre à chaque client, accessible avec `customers.manage_customer_pricing` ;
- [x] seuil en mètres linéaires et remise en pourcentage, avec activation/désactivation ;
- [x] seuils uniques et remises strictement croissantes avec le volume ;
- [x] configuration des paliers pour les comptes `deferred` (le sprint 41 l’ouvre aussi au comptant) ;
- [x] calcul du volume équivalent linéaire : somme des m² DTF / laize configurée ;
- [x] meilleur palier tel que `seuil <= volume mensuel` ;
- [x] remise rétroactive sur toutes les commandes `deferred`, `priced`, `submitted`, non relevées,
  du même client et du même mois civil ;
- [x] préparation fichier, port et commandes comptant exclus de la remise encours (sprint 41 : les
  commandes comptant d’un **compte** comptant ont un palier prospectif séparé) ;
- [x] commande rattachée à un `BillingStatement` figée et exclue du recalcul ;
- [x] recalcul du mois lors d’une nouvelle tarification, d’une invalidation de métrage, d’une
  annulation Atelier ou d’une modification de palier ;
- [x] verrou transactionnel par client pour sérialiser deux tarifications concurrentes ;
- [x] snapshot sur chaque commande : mois, volume, seuil, taux, remise et prix DTF brut ;
- [x] audit de la création/modification de palier et de chaque recalcul financier ;
- [x] résumé de la remise visible dans les panneaux Facturation Atelier et client.
- [x] fiche client Atelier enrichie avec volume du mois, remise atteinte, économie HT et distance
  jusqu’au prochain palier.
- [x] grille globale Atelier de paliers par défaut, sans taux financier codé en dur ;
- [x] copie des paliers actifs lors de l’approbation d’un nouveau client en encours ;
- [x] notification e-mail au meilleur nouveau palier atteint, idempotente par client, mois et seuil ;
- [x] adresses des contacts cloisonnées dans des messages distincts et claim avant SMTP pour éviter
  tout doublon automatique après une panne ambiguë ;
- [x] objet et contenu de l’e-mail modifiables dans le catalogue de modèles Atelier ;
- [x] dashboard client enrichi avec volume, palier actuel et progression vers le suivant ;
- [x] tests de permission Atelier et d’isolation des données affichées au client.

## Fichiers principaux

- `backend/apps/customers/models.py` — `CustomerVolumeDiscountTier`
- `backend/apps/customers/services/volume_discounts.py` — configuration, invariants et recalcul
- `backend/apps/orders/services/pricing.py` — agrégation mensuelle et application rétroactive
- `backend/apps/portal/views_staff_customers.py` — endpoints Atelier scopés par UUID client/palier
- `backend/apps/notifications/services/transactional.py` — planification et livraison idempotentes
- `backend/templates/portal/staff/customers/detail.html` — fiche client, synthèse du mois
- `backend/templates/portal/staff/customers/_volume_discount_tier_register.html` — table/cartes + modales CRUD
- `backend/templates/portal/staff/customers/default_volume_discounts.html` — grille globale
- `backend/templates/portal/client/dashboard.html` — progression du client scopé
- `tests/orders/test_monthly_volume_discounts.py` — règles financières et isolation
- `tests/customers/test_volume_discount_tiers.py` — permissions, scope et validation de grille
- `tests/notifications/test_volume_discount_tier_notifications.py` — e-mail et idempotence

## Hypothèses explicites

- Le mois est le mois civil de `Order.created_at` dans le fuseau Django actif.
- Le volume linéaire est un équivalent sur la laize `DTF_LAIZE_CM` : `m² / laize_m`.
- Les relevés déjà constitués ne sont jamais rétroactivement modifiés.
- La remise de 100 % est techniquement autorisée ; elle produit une ligne DTF à zéro mais laisse
  les frais de préparation et de livraison dus.
- Une grille par défaut vide n’attribue aucun palier ; les valeurs financières sont toujours saisies
  par l’Atelier.
- Si une commande franchit plusieurs seuils à la fois, seul le meilleur palier atteint est notifié.

## Validation

- [x] `python backend/manage.py check`
- [x] `python backend/manage.py makemigrations --check --dry-run`
- [x] Ruff check et format
- [x] tests ciblés pricing, administration client, notifications, UI et annulation Atelier
- [x] suite complète du projet : 677 tests passés sous `config.settings.test`
- [x] revue sécurité indépendante : aucun P0–P2 restant
- [x] migrations appliquées sur PostgreSQL local et services Docker relancés sains
- [x] `graphify update .`

## Amélioration UI/UX Atelier — Impeccable

- [x] synthèse client unifiée : volume du mois, remise appliquée, économie HT et prochain objectif ;
- [x] barre de progression accessible vers le prochain palier ;
- [x] paliers présentés comme une grille ordonnée avec états `franchi`, `atteint`, `prochain objectif`
  et `désactivé` ;
- [x] édition et ajout dans une modale CRUD, liste table/cartes alignée commandes
  (grille globale **et** fiche client) ;
- [x] réglages par défaut séparant clairement la grille de référence, l’e-mail client et la création ;
- [x] contrôle visuel local desktop et 375 px, sans débordement horizontal ni erreur console ;
- [x] scan Impeccable exécuté : aucun défaut propre aux composants ajoutés ; les avertissements
  restants concernent la police et deux accents historiques du design system global, conservés pour
  rester alignés avec `DESIGN.md`.

Le sprint 41 ajoute la politique **prospective** pour les comptes comptant, sans modifier le moteur
rétroactif ci-dessus.
