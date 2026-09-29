# Contrat UX — espace POD

## Cadre

Production interne uniquement. L’expédition reste gérée directement entre Shopify
et Sendcloud. Le catalogue commercial Shopify est importé, jamais remplacé par
un CRUD local.

Toutes les vues partagent le shell Atelier, le fil d’Ariane, le rail POD et le
scope visuel `pod-page`. Les opérations restent séparées des réglages selon les
habilitations, avec contrôles serveur.

## Parcours cohérents

| Vue | Lecture et action principale |
| --- | --- |
| À produire | File filtrable, quantités, picking, réservation et préparation RIP |
| Lots RIP / détail | Lots et pièces, fichiers, documents atelier, synchronisation |
| Pose | Scan, recette et confirmation de pose |
| Contrôle qualité | Scan, validation/refus, reprise et historique |
| Stocks | Un mouvement visible à la fois. Les onglets (réception, sortie, rangement) utilisent le rail de sélection ; le bouton corail reste la validation du panneau actif. Soldes recherchables et paginés |
| Réglages | Synthèse en lecture seule et accès aux référentiels autorisés |
| Boutiques | Connexion/reconnexion, client associé, import et webhooks |
| Catalogue / produit | Recherche et pagination, configuration locale des variantes |
| Supports / détail | Création, modification, variantes, photos, marquages et emplacement |
| Techniques | Création, recherche, modification du nom et activation |
| Emplacements / détail | Création, libellé/activation, règles et stock par propriétaire |

## Composants partagés

Le mapping POD suit « support variant → zone autorisée → technique autorisée →
version HD ». Les possibilités proviennent exclusivement du support parent ; ses
variantes taille/couleur en héritent. Une même zone peut proposer plusieurs
techniques. Le panneau affiche les marquages sélectionnés et permet l’ajout/retrait
des marquages sans rechargement. Aucune zone n’est imposée par le support.
Les fichiers proposés sont les versions validées du client de la boutique,
compatibles avec la technique. Aucun ajout/retrait ni changement de sélection
n’est persisté avant « Enregistrer ». Les contrôles serveur restent l’autorité.

La fiche support expose deux listes indépendantes en base : `allowed_zones`
(référentiel `MarkingZone`) et `allowed_techniques` (`PrintTechnique`). Aucun couple,
fichier HD ni obligation n’est créé sur le support. Les variantes héritent de ces
listes via le parent. Le mapping produit crée seul les couples zone/technique/HD,
à partir de ces listes ; toute zone choisie peut utiliser toute technique choisie.
La migration additive reprend les ensembles des anciennes possibilités actives,
sans supprimer les anciennes lignes, recettes, fichiers ni identifiants.
Le fallback ancien modèle est transitoire, réservé aux supports non encore
configurés par les nouvelles listes ; il ne s’applique plus après sauvegarde.
Le retrait d’une dimension utilisée par une recette activée est refusé : modifier
la recette d’abord. Les sauvegardes du support et des recettes verrouillent le
même parent, valident les UUID actifs et auditent les mutations.

- `_list_toolbar.html` : titre, nombre de résultats, recherche et remise à zéro.
- `_editor_actions.html` : enregistrement et fermeture sans soumission.
- `_active_field.html` : activation/désactivation réversible.
- `_form_error.html` : erreur explicite « Action non enregistrée ».
- `pod-workspace.css` : densité, formulaires, disclosures et tables.

Les éditeurs sont des `details` natifs, utilisables au clavier sans JavaScript.
Un éditeur invalide se rouvre et conserve les valeurs non sensibles. Les secrets
ne sont jamais réinjectés. La fermeture conserve le brouillon affiché sans
l’enregistrer ; une navigation abandonne les modifications non soumises.

La validation requise et les états de chargement réutilisent
`product-shell.js`, les succès les toasts Django existants. Les tables larges
restent dans une région défilable au clavier ; elles ne débordent pas le viewport.
Les boutons ont une cible tactile de 44 px et utilisent les tokens live Atelier.

## Sécurité et conservation

Aucune suppression physique des référentiels. SKU, code, parent, zone et chemin
d’export restent immuables après création. Les services contrôlent les dépendances
avant désactivation : travail en attente, réservations, contenu ou règles des bacs.
Les parents actifs sont requis pour réactiver ou sélectionner une ressource.
L’historique des lots, pièces, fichiers et mouvements reste consultable.

Le droit `operate_pod_production` couvre le poste : quantité, picking, reprise d’étiquettes, file RIP, pose et contrôle qualité. Le droit `manage_pod_catalog` reste limité aux boutiques, au mapping, aux supports et aux techniques. L’accès atelier sans ce droit de production reste en lecture. Au déploiement, les comptes et groupes qui avaient déjà le droit catalogue reçoivent aussi le droit de production, pour ne pas bloquer l’atelier en place. Les nouveaux opérateurs reçoivent seulement le droit de production.

Les variantes et marquages sont résolus par UUID dans le support parent ; le
paramétrage de l’emplacement par défaut respecte ce même périmètre. Les soldes
client sont identifiés par leur propriétaire. Chaque mutation est auditée.

## Validation du lot

- Tests CRUD service, permissions, UUID, périmètre enfant et conservation.
- Tests rendu des pages, GET sans mutation, recherche/pagination et erreurs.
- Tests refus des actions POST inconnues et non-divulgation des jetons Shopify.
- Relecture sécurité indépendante et régression POD.
- Contrôle responsive ordinateur/mobile et validation requise dans le navigateur.
# Interactions dynamiques — 26/09/2026

Le runtime `pod-workspace.js` améliore les liens, filtres, pagination et formulaires locaux POD via HTMX. Il remplace uniquement `.pod-page`, conserve le shell, et laisse les PDF, liens externes et autorisations OAuth au navigateur. Les contrôles qui ont déjà une cible HTMX gardent leur cible.

La configuration de variante prévisualise les changements de mode/support par POST CSRF sans écriture et sans envoyer les brouillons dans l’URL. Les champs et zones dépendants changent dans le drawer ; les valeurs compatibles et non sensibles restent disponibles après erreur. Seul un enregistrement réussi émet `pod-config-saved`, ce qui actualise la vue derrière le drawer préservé. Les permissions et la validation métier restent côté serveur. Les réponses 400 contenant le fragment attendu sont affichées ; les 403/500 ne deviennent pas des succès.

Un rechargement initial charge la nouvelle version JavaScript ; le fonctionnement sans JavaScript reste disponible. Pas d’enregistrement automatique d’un changement de mode/support. Après interruption réseau sur une action métier, vérifier le résultat avant de réessayer.
