# Projets de commande B2B

## Position dans le domaine

`B2BOrderProject` est un agrégat de préparation placé avant `Order`. Il décrit le besoin et les
lignes de visuels sans déclencher le workflow atelier.

```text
Customer -> B2BOrderProject -> B2BOrderProjectItem -> Asset -> AssetVersion
                                                        -> AssetAnalysis
                         conversion future
                              -> Order -> ProductionJob
```

Le tenant canonique est `Customer`. Le projet et chaque ligne portent ce tenant ; toutes les
lectures client combinent `customer` et `public_id` UUID.

## Activation

Deux conditions cumulatives sont requises :

- `B2B_DTF_ORDER_PROJECT_ENABLED=True` ;
- un `Customer` actif accessible par un membership actif.

Le champ historique `Customer.b2b_order_projects_enabled` est conservé pour compatibilité de
schéma mais ne masque plus le parcours. Le flag global coupe la feature pour tous les clients.

## Frontières après Sprint 22

- Le projet ne crée aucun `Order` ni `ProductionJob`.
- Les montants, statuts et références de conversion sont en lecture seule côté client.
- Les transitions et mutations passent par `B2BOrderProjectService`.
- Les actions sensibles sont tracées par `AuditLogEntry`.
- La file OPS est en lecture seule.
- Chaque ligne doit posséder une version analysée (`ready` ou `warning`) avant transmission.
- Chaque ligne doit aussi confirmer explicitement la version analysée courante. La confirmation
  stocke la version, l'utilisateur et l'horodatage ; une modification de largeur/hauteur ou un
  remplacement de fichier l'invalide automatiquement.
- La qualité de résolution est calculée à la taille demandée : objectif configurable à 300 DPI,
  avertissement entre 200 et 299 DPI et problème critique sous 200 DPI.
- Un remplacement crée une version immuable et remet le projet à l'état incomplet pendant
  l'analyse.
- Tous les téléchargements sont médiés et revalident le scope `Customer`.
- `OrderUpload` reste compatible et référence progressivement la couche partagée via un lien
  nullable.

## Décision Asset

L'ADR `ADR_B2B_SHARED_ASSET.md` est accepté et implémenté. La migration est additive et ne déplace
aucun fichier existant. `OrderUpload.order` reste obligatoire et aucun `ProjectUpload` parallèle
n'est introduit.

## API et sécurité

- `/api/client/customers/<customer_public_id>/order-projects/` et routes imbriquées ;
- `/api/staff/order-projects/` et détail read-only ;
- erreurs métier structurées avec `code`, `message` et `details` ;
- identifiants publics UUID uniquement ;
- annulation réservée au rôle `owner` ;
- confirmation technique possible par tout membre client actif, uniquement dans son tenant et
  après analyse de la version courante ;
- OPS : `accounts.access_staff_portal` + `view_b2borderproject` ;
- aucun prix ou statut arbitraire accepté en écriture client.
