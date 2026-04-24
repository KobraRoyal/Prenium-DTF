# AGENTS.md — Règles Codex du projet prenium-dtf.com via IDS supply

## Mission
Construire un SaaS e-commerce premium DTF avec backoffice workflow, stockage documentaire centralisé, génération d’ordre de fabrication, scan code-barres, expédition Sendcloud et isolation stricte des données client.

## Priorités absolues
1. Sécurité et isolation des données
2. Lisibilité et maintenabilité
3. DRY et SRP
4. Traçabilité métier
5. UI moderne, simple, utile
6. Tests systématiques

## Règles d’architecture
- Respecter SRP : une classe / un service / un composant = une responsabilité claire
- Éviter la logique métier dans les vues, serializers et templates
- Centraliser les règles métier dans des services applicatifs
- Centraliser les transitions de statuts
- Centraliser les permissions objet
- Encapsuler les APIs Google Drive et Sendcloud
- Utiliser des tâches asynchrones pour les opérations longues

## Règles sécurité
- Ne jamais exposer une ressource par simple ID incrémental en front
- Vérifier l’autorisation côté serveur pour chaque accès objet
- Refuser toute implémentation qui pourrait permettre à un client de voir les données d’un autre
- Ne jamais committer de secret
- Prévoir tests d’accès croisé et tests permissions pour toute feature sensible
- Préférer URLs signées ou téléchargement médié par backend pour les fichiers

## Règles de travail Codex
- Commencer les tâches complexes par un plan
- Proposer les fichiers à modifier avant implémentation
- Écrire les tests en même temps que la feature
- Fournir une checklist de validation
- Signaler explicitement les hypothèses
- Mettre à jour la documentation du lot concerné
- Ne pas toucher à des domaines non demandés sauf si nécessaire et justifié

## Définition de terminé
Une tâche n’est terminée que si :
- code implémenté
- tests ajoutés
- permissions vérifiées
- logs/audit ajoutés si nécessaire
- documentation mise à jour
- checklist du sprint mise à jour
