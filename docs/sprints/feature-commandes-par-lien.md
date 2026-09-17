# Lot — commandes par lien / création manuelle Atelier

Branche : `codex/commande-lien-fichier-admin`.
Spécification : [commandes par lien](../architecture/EXTERNAL_LINK_ORDERS.md).

- [x] Source externe sans fichier, migration additive et contrainte.
- [x] Lien alternatif au téléversement (> 20 Mo), intégré aux informations de commande.
- [x] Création Atelier pour client actif avec métrage total et tarif habituel.
- [x] Permissions, identité opérateur, audit et ouverture médiée du lien.
- [x] Aucun traitement automatique du fichier externe ; contrôle Atelier conservé.
- [x] OF, affichage client/staff, aperçus et réparation Drive adaptés.
- [x] Tests de permissions, isolation, validation, tarification et workflow.
- [x] Validation finale des suites de non-régression et recette visuelle locale.
- [x] Relecture sécurité finale et rafraîchissement Graphify.

## Validation du parcours initial — 17 septembre 2026

- Suite complète `pytest -q` : **1 319 réussis, 4 ignorés**.
- Ruff (fichiers modifiés), `git diff --check`, contrats agents : conformes.
- Django `check` et `makemigrations --check --dry-run` : conformes.
- Migrations appliquées à l'environnement Docker local.
- Recette navigateur locale : formulaires client et Atelier, champs du métrage,
  rejet d'un lien non public avec conservation des valeurs. Compte temporaire supprimé.
- Relecture sécurité indépendante : aucun blocage restant après corrections.
- `graphify update .` effectué sans appel LLM ; sorties locales non versionnées conservées.

## Extension — nombre de visuels Atelier

- [x] Champ « Nombre de visuels » à la création manuelle et dans les formulaires de métrage
  (fiche Production et étape métrage de la console Atelier).
- [x] Frais de préparation multipliés par ce nombre ; métrage total inchangé.
- [x] Entier de 1 à 10 000, défaut historique/client à 1, migration `uploads.0022`.
- [x] Correction et recalcul atomiques, audit ancien/nouveau nombre, conservation des
  préparations lors du recalcul mensuel.
- [x] Refus de modification après toute tentative de paiement comptant ; réservation du
  paiement sérialisée avec la correction (client puis commande).
- [x] Tests création, édition via les deux écrans, permission, valeurs invalides, rollback,
  cinq états de paiement, métrage inchangé et recalcul mensuel.
- [x] Relecture sécurité indépendante : aucun blocage restant.
- [x] Migration appliquée en local ; contrôles Django/Ruff conformes ; graphe rafraîchi.

Validation finale avec extension : **1 337 tests réussis, 4 ignorés** (`pytest -q`).
Aucune régression détectée dans la suite complète.

## Correction UX — formulaire client unique

- [x] Suppression de la seconde carte et des champs nom/consignes dupliqués sur la création projet.
- [x] Champ lien et action intégrés à « Informations de commande ».
- [x] Réutilisation du nom, commentaire et date souhaitée (dans les consignes Atelier).
- [x] Saisie d’un lien désactive le dépôt local ; effacement du lien le réactive.
- [x] Validation serveur et erreurs dans la même carte, sans projet ni fichier intermédiaire.
- [x] Tests d’affichage unique, création, erreurs conservées et isolation client.
- [x] Validation : **158 tests réussis, 2 ignorés** (portail liens, projets B2B, architecture UI).
- [x] Recette Chrome locale : carte unique, dépôt désactivé/réactivé selon le lien,
  URL privée rejetée avec conservation des champs. Formulaire remis vide pour l’utilisateur.
- [x] Relecture sécurité indépendante validée ; assets collectés et versions de cache mises à jour.

## Smoke test local — création par lien

- [x] Création via la route client avec CSRF actif, sur la base Docker locale.
- [x] Nom, date souhaitée, commentaire et lien d’exemple conservés ; aucun fichier local,
  aucune analyse ni synchronisation Drive.
- [x] Fiches client et Atelier accessibles ; lien médié renvoyant vers l’URL attendue.
- [x] Atelier : 3 visuels, 2,5 m, frais de préparation 30,00 EUR, total 72,38 EUR.
- [x] Audit de création et correction du nombre de visuels présents.
- [x] Défaut de titre détecté et corrigé : le nom ouvre la note, puis date et commentaire ;
  test de présentation ajouté.
- [x] Commande locale `51914782-b3b7-4dfa-92f0-97311ac56c49`, marquée TEST / ne pas produire,
  conservée pour inspection. Notifications neutralisées dans le processus du smoke test.

## Visibilité opérateur — lien contenant plusieurs fichiers

- [x] Bloc « Fichiers du lien et métrage » visible dès l’ouverture d’un OF par lien,
  même avant émission de l’OF et contrôle manuel ; il reste visible après tarification.
- [x] Champ explicite « Nombre de fichiers dans le lien », sans duplication du formulaire.
- [x] Permissions, calcul et prérequis production inchangés ; aucune donnée de l’OF utilisateur modifiée.
- [x] Tests portail / pilotage / étapes workflow / architecture : **87 réussis**.

## Séparation des étapes — correction demandée

Remplace le bloc combiné décrit dans la recette précédente.

- [x] Étape 1 : lien et nombre de fichiers uniquement ; bouton d’enregistrement dédié.
- [x] Étape Métrage : métrage seul, dans la séquence contrôle → machine → métrage.
- [x] Endpoint nombre seul : aucun champ métrage accepté, aucune tarification anticipée.
- [x] Corrections ultérieures : métrage conservé, protections paiement/facturation conservées.
- [x] Tests workflow, permissions, valeurs invalides et recalcul ; revue sécurité indépendante.


## Détail facturation — client et Atelier

- [x] Composant commun dans les panneaux existants, visible aussi après paiement.
- [x] Préparation : nombre de fichiers × prix unitaire, montant HT enregistré.
- [x] Impression : métrage linéaire, surface facturée et prix unitaire enregistré.
- [x] Remise éventuelle, sous-total HT, port, taux et montant TVA, total TTC.
- [x] Aucun recalcul ni modification des tarifs ; cas ancien sans prix brut explicité.
- [x] Tests quantité, unités catalogue/Atelier, remise, zéro TVA/port, payé et attente.
- [x] Accès croisé et permissions vérifiés ; revue sécurité indépendante sans point restant.
- [x] 145 tests ciblés réussis (facturation, commandes par lien, portail UI/architecture).
- [x] Vérification navigateur client/Atelier, ordinateur et largeur 390 px sans débordement.
- [x] CSS compilés et collectés, service web rechargé, contrôle Django sans erreur.
