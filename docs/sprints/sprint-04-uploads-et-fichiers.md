# Sprint 04 — Contrôle fichier basique et métadonnées

> Ce sprint prolonge le socle sécurisé du Sprint 03 sans élargir le périmètre
> au workflow production, à Google Drive ni au contrôle DTF avancé.

## Objectif
Livrer une base sécurisée pour :
- extraire des métadonnées de base sur les fichiers de commande ;
- produire un résultat de contrôle simple rattaché à `OrderUpload` ;
- exposer ce résultat côté client avec scope strict ;
- exposer une consultation staff séparée ;
- préparer les prochains contrôles DTF sans sur-ingénierie.

## Périmètre
- modèle `OrderUploadInspection` rattaché en `OneToOne` à `OrderUpload`
- extraction centralisée des métadonnées de base
- statut simple `ok` / `warning` / `error`
- messages minimaux et audit minimal du contrôle
- endpoint client de détail du contrôle
- endpoint staff de détail du contrôle avec permission dédiée
- compatibilité avec le scope dérivé `OrderUpload -> Order -> Customer`

## Hors périmètre
- détection de finesse
- preview complexe
- OCR
- Google Drive
- workflow production
- paiement et facturation

## Tâches
- [x] ajouter le modèle `OrderUploadInspection`
- [x] centraliser l'extraction de métadonnées dans un service dédié
- [x] déclencher le contrôle basique à la création d'un upload
- [x] exposer le détail de contrôle côté client
- [x] exposer le détail de contrôle côté staff avec permission dédiée
- [x] journaliser l'exécution du contrôle sans exposer de chemin disque
- [x] couvrir les cas image lisible / image illisible / type inattendu
- [x] vérifier la non-régression uploads / orders / scope
- [x] mettre à jour décisions, risques et statut projet

## Choix d'implémentation
- `OrderUploadInspection` reste rattaché uniquement à `OrderUpload`, sans FK directe vers `Customer`
- le contrôle basique reste synchrone et léger au moment de l'upload
- l'extraction image se limite à la lecture d'en-têtes PNG/JPEG
- les types non couverts reçoivent un statut `warning`, pas une fuite d'erreur interne
- aucun chemin de stockage, `file.url` ou détail système n'est exposé en API ni en audit

## Validations attendues
- [x] résultat de contrôle scoped via `OrderUpload -> Order -> Customer`
- [x] aucune logique critique dans les vues
- [x] aucun chemin disque exposé
- [x] aucune URL brute de stockage exposée
- [x] refus par défaut sur les routes client/staff
- [x] audit minimal du contrôle ajouté

## Tests attendus
- [x] client voit le contrôle de son propre fichier
- [x] client A ne voit pas le contrôle du fichier de B
- [x] anonyme refusé
- [x] client refusé sur route staff
- [x] staff sans permission dédiée refusé
- [x] extraction métadonnée image lisible : OK
- [x] fichier non lisible : statut `error`
- [x] type inattendu : statut `warning`
- [x] non-régression uploads / orders / scope

## Checklist de clôture
- [x] code implémenté
- [x] tests ajoutés
- [x] permissions vérifiées
- [x] logs/audit ajoutés si nécessaire
- [x] documentation mise à jour
- [x] checklist du sprint mise à jour

## Validation exécutée
- [x] `DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ../.venv/bin/pytest ../tests/uploads -q`
- [x] `DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ../.venv/bin/pytest ../tests/orders ../tests/customers ../tests/accounts ../tests/uploads -q`
- [x] `./.venv/bin/ruff check backend/apps/uploads tests/uploads`
- [x] `DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ../.venv/bin/python manage.py makemigrations --check --dry-run`
