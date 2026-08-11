# Sprint 34 — Audit et fiabilité production

Date : 2026-08-11

## Objectif

Fermer les écarts de l'audit du dépôt `main` qui pouvaient provoquer une régression Docker,
maintenir une CI durablement rouge, exposer des données locales dans une image ou empêcher une
restauration fiable. Aucun contrat métier, rôle, permission objet ou modèle multi-tenant n'a été
modifié.

## Correctifs livrés

### Runtime Docker

- suppression systématique du PID Celery Beat périmé avant démarrage ;
- image backend unique et traçable pour `web`, `worker` et `beat` ;
- code de production immuable, sans bind mount des sources applicatives ;
- statiques Nginx servis depuis le volume produit par Django ;
- dépendance Nginx sur un `web` sain ;
- séparation explicite des settings, hôtes, origine CSRF et URL publique entre dev et prod ;
- schéma HTTP direct conservé en local, schéma du reverse proxy respecté en production ;
- redirection HTTPS, cookies sécurisés et contrôle `check --deploy` non désactivables en prod ;
- tags de release et labels OCI reliés au SHA Git ;
- images Node, Python, Nginx, PostgreSQL et Redis figées par digest multi-architecture ;
- exclusion du contexte Docker de `.env`, outils locaux, tests, graphes, sorties, sauvegardes et
  données hôte. Le contexte backend est passé d'environ 435 Mo à moins de 7 Mo en build production.

### Sauvegardes

- `infra/scripts/backup-postgres.sh` : dump custom, validation `pg_restore --list`, checksum SHA-256,
  publication atomique, rétention et refus des chemins dangereux ;
- `infra/scripts/backup-media.sh` : archive du volume médias, relecture `tar`, checksum, publication
  atomique et rétention ;
- runbook NAS avec politique de rétention, planification, vérification, restauration isolée et
  procédure de restauration réelle.

### CI et supply chain

- actions GitHub migrées vers leurs runtimes Node 24 (`checkout`, `setup-python`, `setup-node`) ;
- permissions minimales et annulation des runs obsolètes ;
- validation des deux fichiers Compose et contrôle Django production en CI ;
- installation explicite de Ghostscript dans les deux jobs backend pour aligner les runners GitHub
  avec l'image applicative et couvrir les formats EPS/AI ;
- couverture applicative mesurée avec seuil anti-régression de 79 % ;
- CodeQL Python et JavaScript/TypeScript ;
- Dependabot hebdomadaire pour Python, npm, Docker et GitHub Actions ;
- audits Python et npm maintenus bloquants.

## Validation observée

- [x] 627 tests SQLite : réussis ; couverture 80,04 % ;
- [x] 627 tests PostgreSQL 16 : réussis ;
- [x] tests e-mails transactionnels, dédoublonnage et Sendcloud/webhooks inclus ;
- [x] Ruff lint et format sur 301 fichiers ;
- [x] `manage.py check`, migrations et contrats agents ;
- [x] `manage.py check --deploy --fail-level WARNING` dans l'image finale ;
- [x] `pip-audit` : aucune vulnérabilité connue ;
- [x] `npm audit --audit-level=high` : aucune vulnérabilité ;
- [x] build assets reproductible, aucun diff généré ;
- [x] Compose local et production valides ;
- [x] build Docker dev et prod réussi sur les digests figés ;
- [x] six services locaux sains et `/healthz/` à 200 ;
- [x] POST login via Nginx avec CSRF local : 200, aucun 403 de configuration ;
- [x] redémarrage Beat brutal puis reprise sans erreur de PID ;
- [x] statiques application et admin à 200 ;
- [x] sauvegarde PostgreSQL réelle, checksum valide et restauration dans PostgreSQL 16 jetable ;
- [x] archive médias réelle, checksum et lecture de l'archive valides ;
- [x] image prod sans `.env`, `data/`, tests, sorties locales ni graphe runtime ;
- [x] `web`, `worker` et `beat` résolvent un tag d'image backend unique.

## Actions environnement cible

Ces actions ne peuvent pas être réalisées depuis le dépôt seul :

- [ ] faire tourner tous les secrets qui ont pu être affichés ou copiés pendant l'audit ;
- [ ] pousser la branche et vérifier le premier run GitHub Actions/CodeQL ;
- [ ] rendre les checks CI obligatoires sur `main` ;
- [ ] planifier les deux scripts de sauvegarde dans DSM et activer la réplication hors NAS ;
- [ ] exécuter la recette avec les vraies API SMTP, Drive, Sendcloud, PayPal et Stripe ;
- [ ] déployer l'image taguée par SHA et vérifier la restauration mensuelle.

## Définition de terminé

Le lot dépôt est terminé : code, tests, sécurité de build, sauvegardes, documentation et checklist
sont livrés. La mise en production reste conditionnée aux six actions d'environnement cible
ci-dessus, notamment la rotation des secrets exposés.
