# Mission Codex — Nouvelle feature de prise de commande B2B Premium DTF

Tu travailles sur le projet existant **Premium DTF d’IDS Supply**.

## Contexte technique

Stack actuelle :

- Django 5
- Django REST Framework
- PostgreSQL
- Redis
- Celery
- Docker
- Nginx
- Tailwind CSS
- HTMX
- Alpine.js

Le projet possède déjà :

- une architecture multi-tenant ;
- des modèles `Organization` et `Membership` ;
- une authentification B2B ;
- des rôles et permissions ;
- un catalogue ;
- une grille tarifaire B2B ;
- des commandes ;
- des lignes de commande ;
- un système d’upload de fichiers ;
- des assets persistants ;
- un workflow atelier ;
- des tâches Celery ;
- un espace client ;
- un espace OPS ;
- des tests automatisés.

## Objectif de la feature

Développer une nouvelle fonctionnalité de prise de commande réservée exclusivement aux clients B2B approuvés.

Cette fonctionnalité doit modifier le workflow actuel en ajoutant une étape de **projet de commande B2B** avant la création de la commande définitive.

Nouveau parcours cible :

```text
Projet brouillon
→ Ajout des fichiers
→ Saisie des dimensions et quantités
→ Analyse des fichiers
→ Estimation du métrage
→ Estimation du prix B2B
→ Transmission à IDS Supply
→ Contrôle OPS
→ Modification éventuelle demandée au client
→ Confirmation du métrage et du prix
→ Acceptation client si nécessaire
→ Conversion en commande existante
→ Workflow de production actuel
```

La nouvelle fonctionnalité ne doit pas remplacer le workflow de production existant.

Elle doit s’insérer avant la création de la commande définitive.

## Contraintes essentielles

- Fonctionnalité accessible uniquement aux clients B2B approuvés.
- Isolation multi-tenant stricte.
- Un client ne peut accéder qu’aux projets de son organisation.
- Réutiliser au maximum les modèles, services et conventions existants.
- Ne pas recréer les fonctionnalités déjà présentes.
- Ne pas casser les commandes actuelles.
- Ne pas modifier inutilement le workflow atelier existant.
- Les prix doivent toujours être calculés côté serveur.
- Les fichiers originaux doivent être conservés.
- Les remplacements de fichiers doivent être versionnés.
- La conversion projet-vers-commande devra être atomique et idempotente dans un sprint ultérieur.
- Toutes les actions importantes doivent être auditées.
- La feature doit être activable avec un feature flag.
- Ajouter des tests pour chaque règle métier importante.

## Feature flag

Créer ou réutiliser un feature flag global :

```env
B2B_DTF_ORDER_PROJECT_ENABLED=true
```

Prévoir également une activation par organisation si le projet possède déjà un mécanisme de features.

Exemple conceptuel :

```python
organization.features["b2b_dtf_order_project"] = True
```

Ne crée pas un nouveau système de feature flags si un système existe déjà.

# Étape 1 obligatoire — Audit du dépôt

Avant toute modification, audite le dépôt.

Identifie précisément :

1. le modèle `Organization` ;
2. le modèle `Membership` ;
3. les rôles B2B existants ;
4. le modèle `Asset` ;
5. le système d’upload ;
6. les modèles `Order` et `OrderItem` ;
7. le service de tarification ;
8. les statuts de commande ;
9. les vues et URLs du portail B2B ;
10. les vues et URLs OPS ;
11. les tâches Celery ;
12. le système de notifications ;
13. le système d’audit ;
14. les feature flags existants ;
15. les conventions de code ;
16. les tests existants réutilisables.

Présente ensuite :

- l’architecture actuelle utile à la feature ;
- les éléments existants à réutiliser ;
- les éventuels conflits ;
- les migrations nécessaires ;
- les risques de régression ;
- la liste exacte des fichiers à créer ou modifier.

Après cet audit, implémente directement le Sprint 1 sans demander de confirmation intermédiaire.

# Architecture attendue

Créer un module métier dédié aux projets de commande B2B.

Nom recommandé de l’application Django :

```text
b2b_order_projects
```

Si une application existante couvre déjà ce périmètre, intégrer la fonctionnalité dedans plutôt que créer une nouvelle application.

## Modèle principal : B2BOrderProject

Créer un modèle représentant un projet de commande avant conversion en commande.

Champs minimums :

```python
id
organization
created_by
project_number
name
customer_reference
end_customer_reference
order_mode
status
requested_date
delivery_method
shipping_address
customer_comment
internal_comment
estimated_length_mm
confirmed_length_mm
estimated_subtotal
estimated_tax
estimated_total
confirmed_subtotal
confirmed_tax
confirmed_total
price_confirmation_required
submitted_at
review_started_at
confirmed_at
converted_at
converted_order
created_at
updated_at
```

Utiliser les types et conventions du projet existant.

Le champ `converted_order` doit être nullable et unique lorsqu’il est renseigné.

Le numéro du projet doit être unique.

Format recommandé :

```text
DTF-B2B-2026-000001
```

Utiliser un générateur sûr contre les collisions et les accès concurrents.

## Modèle : B2BOrderProjectItem

Chaque ligne représente un visuel ou un fichier de la commande.

Champs minimums :

```python
id
project
asset
name
customer_reference
placement
width_mm
height_mm
quantity
rotation_allowed
individual_cutting
customer_comment
status
sort_order
created_at
updated_at
```

Contraintes :

- largeur supérieure à zéro ;
- hauteur supérieure à zéro ;
- quantité supérieure à zéro ;
- dimensions cohérentes avec la largeur maximale ;
- ordre stable ;
- asset appartenant à la même organisation que le projet.

## Modes de commande

Prévoir les valeurs suivantes :

```text
INDIVIDUAL_DESIGNS
READY_GANG_SHEET
REORDER
```

# Statuts du projet

Créer un enum ou `TextChoices` cohérent avec le projet.

Statuts minimums :

```text
DRAFT
INCOMPLETE
ANALYZING
ACTION_REQUIRED
READY_TO_SUBMIT
SUBMITTED
UNDER_REVIEW
CHANGES_REQUESTED
PRICE_CONFIRMATION_REQUIRED
CONFIRMED
CONVERTED
CANCELLED
BLOCKED
```

## Transitions autorisées

Implémenter explicitement les transitions.

Exemples :

```text
DRAFT → INCOMPLETE
DRAFT → READY_TO_SUBMIT
INCOMPLETE → READY_TO_SUBMIT
READY_TO_SUBMIT → SUBMITTED
SUBMITTED → UNDER_REVIEW
UNDER_REVIEW → CHANGES_REQUESTED
CHANGES_REQUESTED → READY_TO_SUBMIT
UNDER_REVIEW → PRICE_CONFIRMATION_REQUIRED
UNDER_REVIEW → CONFIRMED
PRICE_CONFIRMATION_REQUIRED → CONFIRMED
CONFIRMED → CONVERTED
DRAFT → CANCELLED
INCOMPLETE → CANCELLED
CHANGES_REQUESTED → CANCELLED
```

Les transitions non autorisées doivent lever une erreur métier claire.

Ne pas autoriser de modification libre lorsque le projet est :

- `SUBMITTED` ;
- `UNDER_REVIEW` ;
- `CONFIRMED` ;
- `CONVERTED` ;
- `CANCELLED`.

# Permissions

Réutiliser les rôles existants.

## Client B2B membre

Peut :

- créer un projet ;
- voir les projets de son organisation ;
- modifier un brouillon ;
- ajouter des lignes ;
- ajouter ou remplacer des fichiers ;
- transmettre le projet ;
- répondre à une demande de correction.

## Client B2B administrateur

Peut également :

- voir tous les projets de son organisation ;
- annuler un projet ;
- valider un ajustement tarifaire ;
- créer un projet depuis une ancienne commande.

## IDS OPS

Peut :

- voir les projets transmis ;
- commencer le contrôle ;
- demander une modification ;
- ajuster le métrage ;
- ajuster le prix ;
- confirmer le projet ;
- convertir le projet en commande lors d’un sprint ultérieur.

## IDS ADMIN

Peut :

- forcer certains statuts ;
- corriger un projet ;
- consulter les audits ;
- accéder aux données de toutes les organisations.

Chaque endpoint doit vérifier :

- authentification ;
- rôle ;
- organisation ;
- statut du projet ;
- feature flag.

# API Sprint 1

Respecter les conventions API existantes.

## Projets

```http
GET    /api/v1/b2b/order-projects/
POST   /api/v1/b2b/order-projects/
GET    /api/v1/b2b/order-projects/{id}/
PATCH  /api/v1/b2b/order-projects/{id}/
DELETE /api/v1/b2b/order-projects/{id}/
```

Le `DELETE` peut être un soft delete ou une annulation selon les conventions actuelles.

## Lignes

```http
POST   /api/v1/b2b/order-projects/{id}/items/
PATCH  /api/v1/b2b/order-projects/{id}/items/{item_id}/
DELETE /api/v1/b2b/order-projects/{id}/items/{item_id}/
POST   /api/v1/b2b/order-projects/{id}/items/{item_id}/duplicate/
POST   /api/v1/b2b/order-projects/{id}/items/reorder/
```

## Actions métier du Sprint 1

```http
POST /api/v1/b2b/order-projects/{id}/submit/
POST /api/v1/b2b/order-projects/{id}/cancel/
```

Ajouter des réponses d’erreur structurées.

Exemple :

```json
{
  "code": "INVALID_PROJECT_TRANSITION",
  "message": "Le projet ne peut pas être transmis depuis son statut actuel.",
  "details": {
    "current_status": "UNDER_REVIEW",
    "requested_status": "SUBMITTED"
  }
}
```

# Interface B2B Sprint 1

Créer ou modifier les écrans suivants.

## Dashboard B2B

Ajouter :

- bouton « Nouvelle commande DTF » ;
- compteur de brouillons ;
- compteur d’actions requises ;
- liste des derniers projets ;
- statut de chaque projet ;
- bouton « Continuer ».

## Création du projet

Créer un tunnel en plusieurs étapes :

```text
1. Projet
2. Fichiers
3. Dimensions et quantités
4. Vérification
5. Validation
```

Dans le Sprint 1, implémenter principalement :

- l’étape Projet ;
- la structure de navigation ;
- la liste des lignes ;
- les formulaires dimensions et quantités ;
- la sauvegarde automatique du brouillon.

Utiliser HTMX et Alpine.js si cela correspond à l’architecture actuelle.

Ne pas introduire React sans nécessité.

# Audit et historique

Créer ou réutiliser un modèle d’événements.

Chaque événement doit stocker :

```python
project
actor
event_type
previous_status
new_status
public_message
internal_message
metadata
created_at
```

Événements minimums du Sprint 1 :

```text
PROJECT_CREATED
PROJECT_UPDATED
ITEM_ADDED
ITEM_UPDATED
ITEM_DELETED
PROJECT_SUBMITTED
PROJECT_CANCELLED
```

Les événements internes ne doivent pas forcément être visibles par le client.

# Sprint 1 à implémenter maintenant

## Inclus

- audit du dépôt ;
- modèle `B2BOrderProject` ;
- modèle `B2BOrderProjectItem` ;
- enum des statuts ;
- règles de transition ;
- feature flag ;
- permissions ;
- CRUD API ;
- création de brouillon ;
- modification de brouillon ;
- ajout, modification et suppression de lignes ;
- duplication et réorganisation des lignes ;
- liste des projets B2B ;
- page de détail ;
- sauvegarde automatique ;
- audit minimal ;
- migrations ;
- tests unitaires ;
- tests d’intégration ;
- documentation.

## Exclus

Ne développe pas encore :

- analyse d’image ;
- calcul DPI ;
- moteur de métrage ;
- aperçu de laize ;
- nesting ;
- paiement ;
- workflow OPS complet ;
- conversion en commande ;
- notifications réelles ;
- connexion au RIP ;
- génération de fichiers de production.

Préparer uniquement les interfaces et abstractions nécessaires aux prochains sprints.

# Tests obligatoires

## Modèles

- création d’un projet ;
- génération du numéro ;
- isolation par organisation ;
- validation des quantités ;
- validation des dimensions ;
- transitions autorisées ;
- transitions interdites.

## Permissions

- membre B2B autorisé sur son organisation ;
- membre B2B refusé sur une autre organisation ;
- client non approuvé refusé ;
- OPS autorisé ;
- utilisateur anonyme refusé ;
- feature flag désactivé.

## API

- création de brouillon ;
- modification d’un brouillon ;
- refus de modification d’un projet transmis ;
- ajout d’une ligne ;
- suppression d’une ligne ;
- duplication d’une ligne ;
- filtrage par organisation ;
- pagination ;
- validation des erreurs.

## Sécurité

- tentative d’accès inter-tenant ;
- asset d’une autre organisation ;
- modification de prix depuis le client ;
- modification de statut arbitraire ;
- ID inexistant ;
- quantité négative ;
- dimensions nulles.

Exécuter les outils réellement présents dans le projet, notamment si disponibles :

```bash
pytest
ruff check .
ruff format --check .
```

Ne supprime aucun test existant pour faire passer la suite.

# Méthode de travail

Travaille de manière incrémentale.

Pour chaque étape :

1. inspecte l’existant ;
2. décide ce qui doit être réutilisé ;
3. implémente ;
4. ajoute les tests ;
5. exécute les tests ;
6. corrige les régressions ;
7. documente.

Ne remplace pas massivement des fichiers existants.

Ne fais pas de refactor global non demandé.

Ne modifie pas la structure du projet sans justification.

Ne désactive aucune règle de sécurité.

Ne présente pas une implémentation simulée comme terminée.

# Livrable final attendu

À la fin, fournis un rapport structuré avec :

## Résumé

Description de ce qui a réellement été développé.

## Audit de l’existant

Éléments réutilisés et décisions prises.

## Fichiers créés

Tableau :

- chemin ;
- type ;
- fonction.

## Fichiers modifiés

Tableau :

- chemin ;
- modification ;
- justification.

## Modèles

Liste des modèles et champs ajoutés.

## Endpoints

Liste des routes ajoutées.

## Permissions

Résumé des règles d’accès.

## Migrations

Nom et contenu des migrations.

## Tests

Indiquer :

- nouveaux tests ;
- nombre de tests réussis ;
- éventuels tests échoués ;
- commandes exécutées.

## Configuration

Documenter :

```env
B2B_DTF_ORDER_PROJECT_ENABLED=true
```

## Limitations

Lister ce qui n’est pas encore développé.

## Sprint suivant recommandé

Proposer un Sprint 2 consacré à :

- upload des fichiers ;
- rattachement aux assets ;
- miniatures ;
- analyse DPI ;
- transparence ;
- contrôles techniques ;
- tâches Celery.

Commence maintenant par l’audit complet du dépôt, puis implémente le Sprint 1 sans demander de confirmation intermédiaire.
