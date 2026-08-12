# Sprint 36 — Correctif de schéma des imports visuels

## Incident

Le 12 août 2026, deux imports pourtant valides échouaient dans l'environnement local :

- un PDF/X-4 de 865 Ko importé dans le Gang Sheet passait à l'état `failed` ;
- le premier visuel d'un nouveau projet B2B levait une `IntegrityError` sur `crop_mode`.

Le PDF n'était ni corrompu, ni chiffré, ni hors limite. La base contenait des colonnes issues du
lot de recadrage (`crop_*`) et d'aperçu HD (`large_preview`), tandis que les modèles et migrations
de la branche courante ne les déclaraient plus.

## Correction

- [x] restaurer les champs de recadrage non destructif sur `B2BOrderProjectItem` avec un crop
  complet par défaut ;
- [x] préserver ces valeurs lors de la duplication d'une ligne ;
- [x] restaurer `AssetAnalysis.large_preview` et son chemin tenant-scoped ;
- [x] fournir une migration compatible avec une base propre comme avec une base où la colonne
  `large_preview` existe déjà ;
- [x] couvrir la création du premier visuel et la persistance d'une analyse PDF.

## Sécurité et rollback

Les chemins de fichiers restent dérivés des UUID publics du client, de l'asset et de sa version.
Aucune route ni permission n'est modifiée. La migration de compatibilité ne supprime aucune donnée
et son retour arrière est volontairement non destructif.

## Validation attendue

```bash
docker compose exec -T web sh -lc 'cd /app/backend && python manage.py migrate'
docker compose exec -T web sh -lc 'cd /app/backend && pytest -q ../tests/b2b_order_projects/test_portal.py ../tests/b2b_order_projects/test_assets.py ../tests/gang_sheets/test_services.py'
```

Le retour arrière de `uploads.0018` conserve volontairement la colonne `large_preview`. Ne pas
revenir de `b2b_order_projects.0005` vers `0004` sans sauvegarde : Django supprimerait les cinq
colonnes de recadrage et leurs données.
