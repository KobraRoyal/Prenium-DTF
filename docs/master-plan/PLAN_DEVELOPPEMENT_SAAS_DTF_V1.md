# Plan de développement — SaaS e-commerce premium DTF

## Objectif du document
Ce document sert de **plan directeur de développement** pour le SaaS e-commerce premium DTF.

Il doit permettre de :
- cadrer le périmètre fonctionnel et technique ;
- suivre l’avancement lot par lot ;
- garder une logique **DRY** ;
- imposer un niveau de **sécurisation élevé** ;
- garantir un **isolement strict des données client** ;
- construire des interfaces **modernes, intuitives et dynamiques** côté front-office et backoffice workflow.

---

# 1. Principes directeurs

## 1.1 Vision produit
Construire une plateforme SaaS de vente et de gestion de production DTF premium avec :
- site e-commerce orienté conversion ;
- espace client sécurisé ;
- gestion documentaire centralisée ;
- workflow atelier clair avec ordre de fabrication ;
- code-barres unique par commande ;
- intégration logistique Sendcloud ;
- architecture prête à évoluer.

## 1.2 Principes de développement
- **DRY** : aucune duplication inutile de logique métier, de règles de validation ou de composants UI.
- **Security by design** : la sécurité n’est pas un ajout tardif, elle structure tout le projet.
- **Least privilege** : chaque utilisateur, service et intégration ne voit que ce qui lui est nécessaire.
- **Traçabilité** : toutes les actions critiques doivent être historisées.
- **Modularité** : chaque domaine métier doit être découplé autant que possible.
- **Lisibilité** : code, architecture et interfaces compréhensibles rapidement.
- **Évolutivité** : préparer le terrain pour futures V2/V3 sans complexifier inutilement le MVP.

## 1.3 Objectifs UX
- front-office premium, moderne et rassurant ;
- tunnel de commande fluide ;
- espace client simple ;
- backoffice workflow visuel, rapide, orienté production ;
- écrans de scan et transitions intuitifs ;
- design cohérent desktop + tablette + mobile.

---

# 2. Périmètre produit V1

## 2.1 Front-office
- page d’accueil premium ;
- pages services ;
- pages argumentaires ;
- tunnel de commande DTF au mètre ;
- tunnel de commande préparation de fichier ;
- upload de fichiers ;
- espace client ;
- suivi de commande ;
- historique et téléchargement de documents.

## 2.2 Backoffice interne
- gestion des commandes ;
- gestion des fichiers ;
- génération ordre de fabrication ;
- scan code-barres ;
- workflow de production ;
- gestion expédition Sendcloud ;
- historique et audit.

## 2.3 Intégrations
- Google Drive Shared Drive pour centralisation documentaire ;
- Sendcloud pour expédition ;
- emails transactionnels ;
- génération PDF ;
- génération code-barres et QR code.

---

# 3. Exigences DRY

## 3.1 Logique métier centralisée
À imposer dès le départ :
- règles métier dans des **services applicatifs** dédiés ;
- validations communes dans des couches réutilisables ;
- transitions de statuts centralisées ;
- calculs tarifaires factorisés ;
- règles d’accès unifiées ;
- templates réutilisables pour notifications et documents.

## 3.2 Réutilisation UI
- design system commun front + backoffice quand pertinent ;
- composants réutilisables : tableaux, cartes, badges de statut, timeline, upload zone, filtres, modales ;
- tokens de design centralisés ;
- variantes standardisées.

## 3.3 Réutilisation technique
- couche service pour Google Drive ;
- couche service pour Sendcloud ;
- couche service pour génération documents ;
- couche service pour barcode/QR ;
- couche permissions commune ;
- couche audit commune.

## 3.4 Points de contrôle DRY
- [ ] aucune logique métier critique dans les vues
- [ ] aucune duplication de calcul tarifaire
- [ ] aucune duplication de règles de statut
- [ ] aucune duplication de permissions
- [ ] aucun accès direct non abstrait aux APIs externes depuis les vues
- [ ] composants UI communs documentés

---

# 4. Exigences sécurité

## 4.1 Objectif général
Empêcher :
- fuite de données entre clients ;
- exposition de fichiers ;
- accès non autorisés au backoffice ;
- erreurs d’autorisation horizontales et verticales ;
- fuite de secrets d’intégration ;
- suppression ou altération non tracée des données.

## 4.2 Règles d’isolation des données
Chaque client ne doit voir que :
- ses commandes ;
- ses fichiers ;
- ses documents ;
- ses adresses ;
- ses factures ;
- ses suivis d’expédition.

À imposer :
- filtrage systématique par propriétaire / organisation ;
- aucune ressource exposée par simple incrément d’ID ;
- UUID externes ou identifiants non prédictibles pour liens publics internes ;
- vérifications d’autorisation systématiques côté serveur ;
- aucun contrôle de sécurité uniquement côté front.

## 4.3 Gestion des rôles
Rôles minimum :
- visiteur ;
- client ;
- client revendeur ;
- opérateur ;
- prépresse ;
- logistique ;
- support ;
- administrateur.

Chaque rôle doit avoir :
- permissions explicites ;
- périmètre de lecture ;
- périmètre de modification ;
- journalisation des actions critiques.

## 4.4 Sécurisation applicative
- authentification robuste ;
- mots de passe hashés avec algorithmes modernes ;
- MFA à prévoir pour admin/backoffice ;
- CSRF activé ;
- protections XSS ;
- protections clickjacking ;
- validation stricte des uploads ;
- contrôle de type MIME ;
- limitation de taille ;
- antivirus/scan à prévoir ;
- rate limiting ;
- journalisation centralisée.

## 4.5 Sécurisation des fichiers
- jamais de mise à disposition brute sans contrôle d’accès ;
- URLs signées ou accès médiés par backend ;
- séparation fichiers temporaires / validés / production ;
- métadonnées tracées ;
- suppression ou archivage contrôlé ;
- permissions restreintes côté stockage.

## 4.6 Secrets et configuration
- secrets uniquement via variables d’environnement ;
- aucun secret dans le dépôt ;
- rotation documentée ;
- comptes de service dédiés ;
- accès minimaux pour Google Drive et Sendcloud.

## 4.7 Audit et observabilité
- journal des connexions ;
- journal des accès fichier sensibles ;
- journal des changements de statut ;
- journal des actions admin ;
- alertes en cas d’erreurs critiques.

## 4.8 Check-list sécurité
- [ ] séparation stricte client / backoffice
- [ ] autorisations objet par objet
- [ ] tests d’accès croisé entre clients
- [ ] secrets hors repo
- [ ] fichiers protégés par backend ou URLs signées
- [ ] logs d’audit sur actions critiques
- [ ] stratégie de sauvegarde documentée
- [ ] politique de rétention définie
- [ ] revue sécurité avant mise en production

---

# 5. Stack technique cible

## 5.1 Backend
- Python 3.12
- Django
- Django REST Framework
- PostgreSQL
- Redis
- Celery

## 5.2 Front-end
Deux approches compatibles, à arbitrer au démarrage :

### Option recommandée
- Django API back-end
- front moderne en **Next.js** ou équivalent
- UI dynamique riche pour front-office et backoffice

### Option simplifiée MVP
- Django templates + HTMX/Alpine.js
- composants modernes
- montée en puissance progressive

## 5.3 Infra / conteneurisation
- Docker
- Docker Compose
- Nginx reverse proxy
- volumes persistants
- stockage temporaire local sécurisé
- synchronisation Google Drive

## 5.4 Bibliothèques à prévoir
- auth / sécurité
- génération PDF
- barcode Code 128
- QR code
- clients API Google Drive
- client API Sendcloud
- gestion permissions objet

## 5.5 Décision à figer
- [ ] choisir stack front exacte
- [ ] choisir UI kit / design system
- [ ] choisir stratégie auth client + staff
- [ ] choisir stratégie stockage médias temporaires

---

# 6. Architecture applicative

## 6.1 Apps Django recommandées
- `core`
- `accounts`
- `customers`
- `catalog`
- `pricing`
- `orders`
- `uploads`
- `documents`
- `production`
- `barcodes`
- `drive_integration`
- `shipping_sendcloud`
- `notifications`
- `billing`
- `auditlog`

## 6.2 Règles d’architecture
- une app = un domaine clair ;
- services métier isolés ;
- schémas de permissions centralisés ;
- pas de logique métier lourde dans les serializers/vues ;
- tâches longues déportées dans Celery ;
- intégrations externes encapsulées.

## 6.3 Check-list architecture
- [ ] apps séparées par domaine
- [ ] services métier définis
- [ ] intégrations externes isolées
- [ ] tâches async identifiées
- [ ] stratégie erreurs/réessais définie

---

# 7. Modèle métier central

## 7.1 Entité principale
La **commande** est le centre du système.

Elle relie :
- client ;
- lignes de commande ;
- fichiers ;
- dossier Drive ;
- ordre de fabrication ;
- code-barres ;
- expédition ;
- historique ;
- notifications.

## 7.2 Référentiel de statuts
Statuts V1 recommandés :
- brouillon
- en attente de paiement
- payée
- fichiers reçus
- contrôle en attente
- contrôle validé
- à produire
- en production
- en finition
- prête à expédier
- expédiée
- terminée
- annulée
- bloquée

## 7.3 Check-list métier
- [ ] numérotation commande définie
- [ ] transitions autorisées définies
- [ ] historique de transitions obligatoire
- [ ] commande liée à tous les documents et fichiers

---

# 8. Gestion documentaire Google Drive

## 8.1 Objectif
Centraliser les fichiers de production dans un **Shared Drive** avec structure stable et traçable.

## 8.2 Arborescence recommandée
`/Commandes/AAAA/MM/NUMERO_COMMANDE/`
- `00_source_client/`
- `01_controle/`
- `02_production/`
- `03_of/`
- `04_shipping/`
- `05_archive/`

## 8.3 Règles
- le backend crée les dossiers ;
- le backend synchronise les fichiers ;
- les IDs Drive sont stockés en base ;
- aucune manipulation critique manuelle requise au quotidien ;
- gestion des erreurs et reprise sur échec.

## 8.4 Sécurité Drive
- Shared Drive dédié ;
- comptes d’accès maîtrisés ;
- compte de service ou délégation maîtrisée ;
- accès minimum ;
- aucune surexposition des liens Drive côté client.

## 8.5 Check-list Drive
- [ ] structure dossier automatique
- [ ] mapping DB ↔ Drive IDs
- [ ] reprise sur upload échoué
- [ ] politique d’accès Drive définie
- [ ] aucun lien Drive brut exposé au client sans contrôle

---

# 9. Ordre de fabrication

## 9.1 Objectif
Produire un document atelier clair, visuel et immédiatement exploitable.

## 9.2 Contenu minimum
- numéro de commande
- barcode
- QR code
- client
- date
- métrage
- service
- options
- notes client
- notes internes
- fichiers associés
- statut
- opérateur assigné
- zones contrôle / production / emballage / expédition

## 9.3 Formats
- PDF imprimable A4
- vue écran moderne dans backoffice
- attaché à la commande et au Drive

## 9.4 Check-list OF
- [ ] template OF validé
- [ ] génération PDF automatisée
- [ ] barcode lisible imprimé
- [ ] QR ouvre la fiche commande
- [ ] document stocké et historisé

---

# 10. Code-barres et scan

## 10.1 Objectif
Permettre le pilotage rapide du workflow via scan.

## 10.2 Format recommandé
- barcode Code 128 pour usage atelier
- QR code pour accès direct à la fiche commande

## 10.3 Usages
- ouvrir commande
- passer au statut suivant
- enregistrer un passage atelier
- tracer l’opérateur et l’heure

## 10.4 UX scan
- champ unique de scan
- retour immédiat visuel
- gros boutons d’action
- historique affiché

## 10.5 Check-list scan
- [ ] valeur barcode unique
- [ ] écran scan rapide
- [ ] transitions sécurisées
- [ ] logs scan conservés

---

# 11. Expédition Sendcloud

## 11.1 Objectif
Créer les expéditions, récupérer les étiquettes et tracer le suivi.

## 11.2 Données à gérer
- transporteur
- méthode d’envoi
- identifiant shipment
- identifiant parcel
- tracking number
- tracking URL
- étiquette PDF
- statut expédition

## 11.3 Règles
- création depuis backoffice ;
- données expédition validées avant appel ;
- récupération et stockage des documents ;
- lien avec statut commande.

## 11.4 Check-list Sendcloud
- [ ] connexion API sécurisée
- [ ] création shipment fonctionnelle
- [ ] récupération étiquette fonctionnelle
- [ ] stockage document local + Drive
- [ ] suivi enregistré en base

---

# 12. Front-office — exigences UX/UI

## 12.1 Objectif
Un rendu moderne, premium, rassurant et performant.

## 12.2 Exigences
- hero premium et crédible ;
- argumentaire orienté expertise ;
- mise en avant qualité + accompagnement ;
- tunnel de commande clair ;
- upload intuitif ;
- feedback visuel immédiat ;
- espace client sobre et lisible ;
- responsive fort.

## 12.3 Composants clés
- header premium
- configurateur de commande
- zone upload drag-and-drop
- cartes service
- frise de statuts
- liste de commandes
- vues de documents

## 12.4 Check-list front
- [ ] design system défini
- [ ] navigation claire
- [ ] tunnel commande sans friction inutile
- [ ] compte client sécurisé
- [ ] responsive validé
- [ ] performance front mesurée

---

# 13. Backoffice workflow — exigences UX/UI

## 13.1 Objectif
Un outil atelier fluide, clair, rapide et agréable à utiliser.

## 13.2 Exigences
- tableau de bord visuel ;
- statuts lisibles ;
- priorités visibles ;
- scans rapides ;
- actions en 1 clic ;
- vue commande dense mais lisible ;
- exploitation sur tablette.

## 13.3 Vues clés
- dashboard production
- liste commandes filtrable
- fiche commande multi-onglets
- vue scan
- vue expédition
- vue documents

## 13.4 Composants clés
- badges statuts
- timeline commande
- panneau actions rapides
- tableau filtrable
- cartes KPI
- timeline d’audit
- modales de confirmation

## 13.5 Check-list backoffice
- [ ] dashboard production validé
- [ ] transitions rapides
- [ ] vue scan optimisée
- [ ] fiche commande intuitive
- [ ] expérience tablette correcte

---

# 14. Permissions et contrôle d’accès

## 14.1 Règle absolue
Aucune donnée sensible ne doit être accessible sans vérification explicite des droits.

## 14.2 Contrôles à imposer
- niveau route ;
- niveau vue ;
- niveau objet ;
- niveau fichier ;
- niveau action métier.

## 14.3 Cas à tester systématiquement
- un client tente d’accéder à une commande d’un autre client ;
- un client tente d’accéder à un fichier d’un autre client ;
- un opérateur tente une action non autorisée ;
- un revendeur voit uniquement son périmètre ;
- un admin voit tout.

## 14.4 Check-list permissions
- [ ] matrice des rôles documentée
- [ ] permissions objet testées
- [ ] fichiers protégés testés
- [ ] routes privées correctement sécurisées

---

# 15. Plan de développement par lots

## Lot 0 — Fondations
- repo
- Docker
- configuration environnement
- PostgreSQL
- Redis
- Celery
- Nginx
- base Django
- auth staff

### Check-list
- [ ] structure repo créée
- [ ] docker-compose opérationnel
- [ ] environnements dev/prod séparés
- [ ] CI minimale en place

## Lot 1 — Comptes et clients
- modèle User
- rôles
- modèle Customer
- espace client de base
- permissions initiales

### Check-list
- [ ] comptes clients créables
- [ ] rôles opérationnels
- [ ] règles d’accès de base validées

## Lot 2 — Catalogue et commande
- catalogue services
- panier / commande
- calcul tarifaire initial
- validation checkout

### Check-list
- [ ] commande DTF au mètre possible
- [ ] commande préparation fichier possible
- [ ] total cohérent

## Lot 3 — Uploads et fichiers
- upload sécurisé
- validation de base
- stockage temporaire
- rattachement commande

### Check-list
- [ ] upload multiple fonctionnel
- [ ] validation type/poids active
- [ ] accès fichiers sécurisé

## Lot 4 — Work order, barcode, QR
- numérotation commande
- génération OF
- génération code-barres
- génération QR

### Check-list
- [ ] OF généré automatiquement
- [ ] barcode unique
- [ ] QR ouvre la fiche commande

## Lot 5 — Google Drive
- création dossier commande
- mapping IDs
- synchronisation fichiers
- gestion erreurs

### Check-list
- [ ] dossier créé automatiquement
- [ ] fichiers synchronisés
- [ ] historique sync disponible

## Lot 6 — Workflow production
- statuts
- transitions
- dashboard
- écran scan
- historique

### Check-list
- [ ] transitions sécurisées
- [ ] dashboard lisible
- [ ] scan fonctionnel

## Lot 7 — Sendcloud
- création expédition
- récupération label
- stockage docs
- tracking

### Check-list
- [ ] expédition créée
- [ ] label récupéré
- [ ] tracking enregistré

## Lot 8 — Finition UX/UI
- design system
- micro-interactions
- responsive
- polish front/back

### Check-list
- [ ] front premium
- [ ] backoffice moderne
- [ ] responsive validé

## Lot 9 — Durcissement sécurité
- revues d’accès
- tests permissions
- tests fuite de données
- logs et monitoring

### Check-list
- [ ] tests croisés client/client OK
- [ ] audit sécurité V1 OK
- [ ] secrets et accès revus

---

# 16. Tests et qualité

## 16.1 Tests à prévoir
- tests unitaires services métier ;
- tests intégration API ;
- tests permissions ;
- tests transitions workflow ;
- tests intégrations externes mockées ;
- tests UI critiques ;
- tests de non-régression.

## 16.2 Priorités absolues
- permissions ;
- isolation données ;
- transitions workflow ;
- uploads ;
- génération documents ;
- expédition.

## 16.3 Check-list qualité
- [ ] couverture des services métier critiques
- [ ] tests permissions présents
- [ ] tests flux commande présents
- [ ] tests upload présents
- [ ] tests workflow présents

---

# 17. Conventions de développement

## 17.1 Code
- typage maximal raisonnable ;
- fonctions courtes ;
- services explicites ;
- pas de logique cachée ;
- noms explicites ;
- commentaires utiles seulement quand nécessaires.

## 17.2 Git
- branches courtes ;
- PR petites ;
- messages de commit explicites ;
- relecture obligatoire sur sécurité et permissions.

## 17.3 Documentation
- chaque module documenté ;
- variables d’environnement listées ;
- procédures d’installation ;
- procédures de reprise incident ;
- procédures de rotation secrets.

## 17.4 Check-list conventions
- [ ] conventions de nommage définies
- [ ] conventions services définies
- [ ] conventions permissions définies
- [ ] doc setup projet rédigée

---

# 18. Points à arbitrer rapidement

- [ ] Django templates enrichis ou front séparé moderne
- [ ] choix du design system
- [ ] méthode exacte d’authentification staff renforcée
- [ ] hébergement cible
- [ ] stratégie de sauvegarde
- [ ] stratégie antivirus fichiers
- [ ] méthode exacte de génération OF
- [ ] politiques de rétention des fichiers

---

# 19. Définition de terminé

Une fonctionnalité est considérée terminée seulement si :
- le code est implémenté ;
- les permissions sont appliquées ;
- les cas d’accès non autorisés sont testés ;
- les logs critiques existent ;
- l’UI est exploitable ;
- la doc minimale est mise à jour.

## Check-list DoD
- [ ] code terminé
- [ ] tests présents
- [ ] permissions vérifiées
- [ ] logs ajoutés
- [ ] UI validée
- [ ] documentation mise à jour

---

# 20. Suivi d’avancement global

## État global
- [ ] Lot 0 — Fondations
- [ ] Lot 1 — Comptes et clients
- [ ] Lot 2 — Catalogue et commande
- [ ] Lot 3 — Uploads et fichiers
- [ ] Lot 4 — Work order, barcode, QR
- [ ] Lot 5 — Google Drive
- [ ] Lot 6 — Workflow production
- [ ] Lot 7 — Sendcloud
- [ ] Lot 8 — Finition UX/UI
- [ ] Lot 9 — Durcissement sécurité

---

# 21. Notes de pilotage

## Priorité actuelle
À renseigner au fur et à mesure.

## Risques ouverts
À renseigner au fur et à mesure.

## Décisions prises
À renseigner au fur et à mesure.

## Questions en attente
À renseigner au fur et à mesure.
