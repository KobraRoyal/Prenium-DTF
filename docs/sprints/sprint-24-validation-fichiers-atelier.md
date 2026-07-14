# Sprint 24 — Validation des fichiers Atelier

Date : 2026-07-14  
Statut : **terminé**

## Objectif

Remplacer le tableau ambigu « Contrôle technique » par une expérience de revue Atelier qui distingue explicitement l’analyse automatique de la décision humaine avant production.

## Architecture livrée

- `OrderUploadInspection` reste le diagnostic automatique utilisé par les métadonnées et le pricing.
- `OrderUploadReview` porte uniquement la décision Atelier : à contrôler, approuvé pour production ou correction demandée.
- `OrderUploadReviewService` centralise les transitions, le scope commande/fichier, les validations et l’audit.
- Les routes de revue et d’aperçu utilisent uniquement les UUID publics et revalident l’appartenance du fichier à la commande.
- La demande de correction déclenche une tâche Celery et le modèle d’e-mail personnalisable `file_correction_requested` pour le client et l’équipe interne.

## UX livrée

- synthèse compacte : à contrôler, prêts pour production, corrections demandées et alertes automatiques ;
- une carte responsive par fichier avec aperçu protégé, métadonnées utiles et historique de décision ;
- vocabulaire non ambigu : « Analyse réussie » n’est jamais affiché comme « Valide » ;
- action principale « Approuver pour production » ;
- demande de correction repliée avec motif, commentaire et notification client ;
- lien direct vers la personnalisation de l’e-mail de correction ;
- feedback HTMX local + toast, y compris pour les messages accentués.

## Permissions et sécurité

- lecture du panneau : `uploads.view_orderuploadinspection` ;
- décision Atelier : `uploads.review_orderupload` ;
- aperçu : `uploads.view_orderupload` ;
- revue croisée entre deux commandes refusée en 404 ;
- commentaire client absent des métadonnées d’audit ; seuls le statut et le code motif sont journalisés.

## Définition de terminé

- [x] Modèle, migration et index ajoutés.
- [x] Service métier centralisé et actions auditées.
- [x] Permissions et seed recette mis à jour.
- [x] Panneau responsive et actions HTMX implémentés.
- [x] Aperçu fichier médié par le backend.
- [x] Notification client/interne personnalisable branchée sur Celery.
- [x] Tests service, permission, isolation, portail, e-mail et cohérence UI ajoutés.
- [x] CSS reconstruit et recette navigateur desktop/mobile effectuée.
- [x] Documentation et checklist sprint mises à jour.

## Recette manuelle

1. Ouvrir une commande Atelier puis l’onglet **Contrôle**.
2. Vérifier que le résultat machine affiche « Analyse réussie » et que la décision reste « À contrôler ».
3. Approuver un fichier et vérifier le toast, l’auteur, la date et le compteur.
4. Demander une correction sur un autre fichier, avec motif et commentaire.
5. Vérifier la notification et le modèle dans **E-mails → Correction fichier demandée**.
6. Contrôler le rendu à 375 px et l’absence de débordement horizontal.
