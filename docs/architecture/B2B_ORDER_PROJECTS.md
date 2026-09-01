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

Le parcours projet avant commande est le **flux standard** pour tous les clients actifs.

Condition unique côté plateforme :

- `B2B_DTF_ORDER_PROJECT_ENABLED=True` (défaut applicatif : activé).

Le champ historique `Customer.b2b_order_projects_enabled` est conservé pour compatibilité de
schéma uniquement ; il ne masque plus le parcours et n’est plus exposé dans l’admin Atelier.
Le flag global reste le coupe-circuit pour désactiver la feature pour tous les clients
(repli éventuel vers le checkout classique).

Le checkout classique fichier → commande n’est plus le parcours retenu.

## UX création client (premier visuel)

Sur `/client/.../order-projects/new/`, le CTA « Ajouter mes visuels » ouvre le sélecteur de
fichier dans le même geste utilisateur, puis crée le projet avec le premier fichier en
`multipart/form-data`. La redirection détail inclut `?validate=<item_public_id>` pour ouvrir
immédiatement la modale de validation technique, sans étape intermédiaire sur une fiche vide.

La création sans fichier reste acceptée côté serveur (POST sans `file`) pour compatibilité et
tests ; le parcours UI standard exige la sélection d’un fichier.

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
- Tant que le projet est éditable, la quantité d'une ligne peut être ajustée directement depuis
  la liste des visuels ; cette action réutilise `B2BOrderProjectService.update_item` et ses
  validations. Le PDF HD d'une Gang Sheet déjà verrouillée pour la production reste en lecture seule.
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

## Numérotation projet

Format unique pour tous les modes (`individual_designs`, `ready_gang_sheet`, `reorder`) :

```text
CMD-{année}-{séquence 6 chiffres}
```

Service : `B2BOrderProjectNumberService` (`services/numbering.py`). Séquence annuelle partagée.

Voir [ORDER_REFERENCE_DISPLAY.md](ORDER_REFERENCE_DISPLAY.md) pour les règles d’affichage client /
Atelier une fois le projet converti en `Order`.
