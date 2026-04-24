# Sprint 03 — Catalogue, pricing, commandes

> Ce lot correspond au Sprint 02 du cadrage courant après le mini Sprint 01.1, tout en conservant la numérotation documentaire historique du plan directeur.

## Objectif
Livrer le premier vertical slice métier du projet après le socle comptes / rôles / sécurité:
catalogue de services, pricing initial simple et création de commande minimale rattachée à `Customer`.

## Périmètre
- catalogue de services DTF au mètre
- service préparation de fichier
- pricing unitaire simple, sans moteur tarifaire complexe
- création de commande minimale
- rattachement explicite à `Customer`
- accès client scoped et accès staff séparé

## Hors périmètre
- paiement PayPal
- facturation automatique
- upload fichiers
- workflow production
- Google Drive
- Sendcloud
- builder avancé
- promotions complexes
- abonnement B2B

## Tâches
- [x] modèles catalogue minimal et commande minimale
- [x] services métier pour catalogue, pricing et création de commande
- [x] endpoints client scoped pour consulter le catalogue et créer une commande
- [x] endpoints staff séparés pour lecture opérationnelle
- [x] admin minimal pour les nouvelles entités
- [x] audit minimal sur création de commande
- [x] historique minimal via snapshot des lignes de commande

## Validations
- [x] chaque objet métier client est rattaché à `Customer`
- [x] aucun accès croisé entre clients
- [x] les routes client filtrent systématiquement par scope serveur
- [x] les routes staff restent séparées des routes client
- [x] aucune logique métier critique dans les vues
- [x] aucun contrôle de sécurité uniquement côté front

## Tests
- [x] calcul prix simple
- [x] création de commande minimale
- [x] validation de commande avec rattachement `Customer`
- [x] refus d’accès à une commande d’un autre client
- [x] refus d’accès staff/client croisé
- [x] non-régression des routes et permissions du socle Sprint 01.1

## Livré
- app `catalog` avec `CatalogService`, endpoints client scoped et endpoint staff séparé
- app `orders` avec `Order`, `OrderLine`, services métier et admin minimal
- pricing initial simple centralisé dans `PricingService`
- création transactionnelle de commande avec snapshot du service, de l’unité et du prix sur chaque ligne
- audit `order.created` branché au moment de la création de commande

## Checklist de clôture
- [x] code implémenté
- [x] tests ajoutés
- [x] permissions vérifiées
- [x] audit minimal ajouté
- [x] documentation mise à jour
- [x] checklist du sprint mise à jour

## Mini Sprint 02.1 — Hardening sécurité ciblé
### Objectif
Corriger les trois angles morts identifiés par la revue sécurité avant d’attaquer un domaine métier plus sensible.

### Tâches
- [x] `OrderService.create_order` auto-protecteur sur le tenant
- [x] permissions staff lecture catalogue et lecture commandes par domaine
- [x] test explicite d’injection malveillante de prix

### Validation
- [x] le service d’écriture refuse un acteur hors scope même s’il est appelé hors vue HTTP
- [x] le service d’écriture refuse aussi un `customer_membership` incohérent
- [x] les routes staff catalogue et commandes ne reposent plus uniquement sur `accounts.access_staff_portal`
- [x] le backend ignore `unit_price`, `line_total` et `total_amount` envoyés par le client
- [x] aucune dérive vers uploads, paiements, facturation ou workflow
