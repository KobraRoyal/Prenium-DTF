# Commandes par lien et commandes manuelles Atelier

## Parcours

- Client en encours : dans « Nouvelle commande », le champ « Votre fichier dépasse 20 Mo ? »
  est intégré à la carte « Informations de commande ». Le nom et le commentaire sont
  partagés avec le dépôt normal ; la date souhaitée est conservée dans les consignes Atelier.
  Le bouton « Transmettre la commande par lien » crée une commande soumise, sans fichier,
  avec tarif et métrage en attente. Aucune seconde saisie du nom ou des consignes. Le nom ouvre la note de commande,
  conformément au format existant, afin de rester le titre client et Atelier ; date et
  commentaire restent dans les informations transmises.
  Un lien renseigné désactive le dépôt local, y compris après une sélection trop lourde.
  Effacer le lien réactive le dépôt habituel et ses limites. Les erreurs conservent les
  informations saisies dans la même carte. Le serveur conserve la validation HTTP(S) et
  l’isolation client avant création ; aucun projet ou asset n’est créé pour le lien.
- Atelier : dans « Commandes », « Créer une commande manuelle » permet de sélectionner
  un client actif, son lien, le nombre de visuels distincts et un métrage total en mètres
  linéaires sur la laize configurée.
  Le service applique immédiatement le tarif habituel, les frais de préparation, les remises,
  le transport et la TVA existants. Une erreur de tarification annule toute la création.
- Le compte client conserve son mode de règlement. Les comptes comptant restent sur le
  parcours Gang Sheet côté client ; l'Atelier peut créer leur commande manuelle mais
  le paiement reste obligatoire avant production.
- Après émission de l'OF, le contrôle manuel reste nécessaire. Pour les commandes par lien,
  le passage en production et la confirmation d'impression exigent métrage positif, tarif
  calculé et contrôle approuvé. La saisie ultérieure du métrage client utilise les actions
  Atelier existantes.

Un lien représente une ligne de commande (un lot de visuels), avec quantité 1 et métrage
global toutes copies comprises. La préparation est facturée par visuel distinct :
`external_visual_count × tarif de préparation`. Le nombre est un entier de 1 à 10 000,
initialisé à 1 pour les commandes client et historiques. L’Atelier peut le renseigner
à la création ou le corriger avec le métrage dans la fiche Production et la console Atelier.
Dans le pilotage, l’étape 1 « Contrôle fichiers » présente le lien et le champ
« Nombre de fichiers dans le lien », avec un enregistrement indépendant. Le métrage
reste exclusivement dans l’étape Métrage, après contrôle et sélection de la machine.
Le nombre de fichiers peut être enregistré sans métrage, sans tarifer ni faire avancer
le workflow. L’endpoint ignore tout métrage transmis dans cette action. Si un tarif
existait déjà, une correction du nombre conserve le métrage et recalcule la préparation.
Le champ compte les fichiers contenus dans le lien, et non le nombre de liens.
Le client ne peut pas modifier ce nombre. Par exemple, 3 visuels et 2,5 m donnent
3 préparations et 2,5 m au total ; le métrage n’est pas multiplié par 3. Aucun téléchargement, analyse ou stockage automatique du visuel externe.
La disponibilité et la durée de validité du lien sont à vérifier par l'Atelier.

## Modèle et sécurité

`OrderUpload.external_url` distingue une source externe. Une contrainte interdit de lui
associer un fichier local, un asset ou une taille non nulle. Les uploads historiques conservent
leurs données et leur fonctionnement. La migration est additive.

`ExternalOrderService` valide les permissions avant mutation. Une création client vérifie
sa membership active ; la création staff exige accès Atelier et permissions `orders.add_order`,
`orders.view_order`, `orders.change_order`. L'auteur reste l'opérateur réel.
Les rôles Atelier propriétaire et administrateur reçoivent `add_order`, y compris les
memberships actives existantes via la migration accounts. Les autres rôles ne la reçoivent pas.

Les liens rejettent schémas non HTTP(S), identifiants intégrés, noms locaux et IP privées.
Aucune résolution DNS ni requête vers le lien n'est effectuée. Les liens sont ouverts par
une redirection médiée : membership client ou droits staff fichier + commande, identifiants
publics, réponse non cachable et politique sans referrer. L'événement
`order_upload.external_link_opened` n'enregistre jamais l'URL ou son éventuel jeton.
La création journalise `order.external_created` avec le métrage, le nombre de visuels et l’acteur.
Les corrections journalisent `order.external_visual_count_updated` (ancien/nouveau nombre).
Le recalcul et les corrections sont atomiques : une erreur conserve le tarif antérieur.
Le recalcul mensuel conserve le nombre de préparations.
Pour les comptes comptant, toute tentative de paiement lancée fige métrage et nombre
(y compris une tentative annulée ou échouée, dont le lien externe pourrait encore être actif).
L’initiation du paiement et la correction utilisent les mêmes verrous client puis commande.

Le PDF OF et l'API Production ne divulguent pas l'URL : ils identifient la source externe
et renvoient vers l'onglet Fichiers. Les aperçus et téléchargements locaux renvoient 404.
Les sources externes sont ignorées par l'inspection et Drive (y compris réparation et tâche
obsolète), et ne sont pas présentées comme incidents Drive. La recommande automatique exige
un fichier local ; son bouton est masqué pour ces commandes et le service refuse explicitement.

## Déploiement et validation

Appliquer `accounts.0006_staff_manual_order_permission` et
`uploads.0021_orderupload_external_url`, puis `uploads.0022_external_visual_count`
avec `python manage.py migrate` avant de démarrer
le code applicatif. Une fois des commandes par lien créées, un retour au code antérieur exige
un traitement préalable de ces commandes : ce code supposait toujours un fichier local.

Recette :

1. Client en encours : transmettre un lien, retrouver la commande sans aperçu manquant.
2. Atelier administrateur : créer pour un client un lien + 2,5 m + 3 visuels ; contrôler les 3 frais de préparation.
   Modifier à 5 visuels : seuls les frais de préparation changent, le métrage reste 2,5 m.
3. Tester métrage invalide, client inactif et URL invalide : aucune commande partielle.
4. Refuser accès croisé client et accès aux liens pour un rôle sans lecture fichiers.
5. Émettre l'OF, contrôler le visuel, saisir/tarifer puis lancer le flux Atelier habituel.
6. Vérifier upload classique, projets B2B, tarification et paiement immédiat.

Tests : `tests/portal/test_external_order_portal.py`, `tests/orders/test_external_orders.py`,
`tests/uploads/test_external_uploads.py`, puis suites orders/uploads/production/billing/portal/B2B.

## Détail de facturation client et Atelier

Les deux panneaux utilisent le composant `order_billing_breakdown.html` et le
présentateur en lecture seule `portal/services/billing_breakdown.py`. Les quantités,
prix unitaires et montants proviennent des lignes enregistrées de la commande,
jamais des tarifs actuels du catalogue. Pour les commandes Atelier, les quantités
DTF sont stockées en m² ; le métrage linéaire est également affiché (surcharge
enregistrée, sinon conversion avec la laize configurée).

Le nombre de fichiers facturés provient de la ligne de préparation, y compris
lorsqu’un seul lien contient plusieurs fichiers. La remise enregistrée est
réintégrée dans le montant DTF avant d’être présentée séparément ; le sous-total,
le port, la TVA et le total TTC restent les valeurs persistées. Sur les anciens
instantanés sans prix avant remise, celle-ci est explicitement indiquée comme
déjà incluse, sans seconde soustraction.

Le détail reste visible après paiement. Avant tarification, aucun détail de prix
provisoire n’est présenté. L’inclusion reçoit uniquement la commande autorisée par
les vues existantes ; aucune nouvelle route ni mutation métier n’est introduite.
