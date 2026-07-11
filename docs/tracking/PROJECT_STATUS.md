# Statut projet

## Sprint en cours
- [x] Sprint 00 — Fondations
- [x] Sprint 00.1 — Stabilisation fondation
- [x] Sprint 01 — Comptes et rôles
- [x] Sprint 01.1 — Stabilisation sécurité
- [x] Sprint 03 — Catalogue, pricing, commandes
- [x] Sprint 02.1 — Hardening sécurité catalogue / commandes
- [x] Sprint 03 — Uploads sécurisés rattachés à la commande
- [x] Sprint 04 — Contrôle fichier basique et métadonnées
- [x] Sprint 05 — Synchronisation Google Drive des fichiers de commande
- [x] Sprint 06 — Workflow production + ordre de fabrication
- [x] Sprint 07 — Code-barres + scan atelier
- [x] Sprint 08 — Expédition Sendcloud
- [x] Sprint 09 — Frontend produit (espace client + backoffice staff)
- [x] Sprint 10 — Paiement PayPal + facturation automatique
- [x] Sprint 11 — Tunnel produit final + polish UX
- [x] Micro-sprint 11.1 bis — Frontend e-commerce premium + tunnel de commande moderne
- [x] Micro-sprint 11.2 — Landing page premium UI/UX
- [x] Micro-lot 11.3 — Audit frontend P1 (wording, guidance, conversion, shipping staff)
- [x] Micro-lot 11.4 — Frontend P2 (prospects, staff forms, hierarchy, HTMX local states, services)
- [x] Micro-lot 11.5 — Frontend P3 (landing proof, tables, skeletons, iconography)
- [x] Micro-lot 11.6 — Hardening transverse UI (contraste, hiérarchie, cartes, badges, onglets, feedback)
- [x] Micro-lot 11.7 — Landing + prospect hardening UI (hero, sections marketing, tunnel, stepper, formulaires)
- [x] Micro-lot 11.8 — Signature UI 2026 (landing éditoriale + dashboards premium hiérarchisés)
- [x] Micro-lot 11.9 — Cohérence UI/UX 100% ciblée (breadcrumbs, auth, checkout, panels, tabs, menu mobile, labels)
- [x] Micro-lot 11.10 — Système de boutons SaaS unifié et cohérent
- [x] Micro-lot 11.11 — Audit global UI/UX par app et vues + corrections de cohérence SaaS

## Dernier lot terminé
- [x] Lot 0 — Fondations implémenté et validé techniquement
- [x] Lot 1 — Comptes, rôles, séparation client/staff et permissions de base implémentés
- [x] Lot 1.1 — Surface `/admin/`, audit minimal et compte hybride stabilisés
- [x] Lot 2 — Catalogue, pricing initial et première commande implémentés
- [x] Lot 2.1 — Hardening service d’écriture + permissions staff par domaine + test d’injection prix
- [x] Lot 3 — Uploads sécurisés rattachés à la commande avec stockage protégé, permission staff dédiée et audit minimal
- [x] Lot 4 — Contrôle fichier basique, métadonnées et consultation client/staff sécurisée implémentés
- [x] Lot 5 — Synchronisation Google Drive minimale, sécurisée et auditée implémentée
- [x] Lot 6 — Workflow production minimal, transitions contrôlées et ordre de fabrication simple implémentés
- [x] Lot 7 — Identifiant scan opaque, résolution staff et transition atelier via scan implémentés
- [x] Lot 8 — Base Sendcloud sécurisée implémentée
- [x] Lot 9 — Surface UI produit client/staff avec panneaux HTMX implémentée
- [x] Lot 10 — Socle paiement PayPal + facturation automatique sécurisé et scope client/staff implémenté
- [x] Lot 11 — Tunnel produit final et polish UX client/staff implémentés sans dérive métier
- [x] Lot 11.1 bis — Front-office premium + tunnel client moderne implémentés sans nouveau domaine métier
- [x] Lot 11.2 — Landing conversion premium structurée et responsive livrée
- [x] Lot 11.3 — Corrections frontend P1 visibles (wording, guidance checkout, clarification landing/services, recomposition shipping staff) livrées sans changement métier
- [x] Lot 11.4 — Harmonisation frontend P2 (prospects, formulaires staff, hiérarchie fiche staff, feedback HTMX local, page services enrichie) livrée sans changement métier
- [x] Lot 11.5 — Optimisation frontend P3 (proof landing, tables, skeletons, iconographie) livrée sans changement métier
- [x] Lot 11.8 — Refonte visuelle 2026 landing + portail livrée sans impact métier ni permissions
- [x] Lot 11.9 — Audit cohérence UI/UX ciblé clôturé à 100/100 sans impact métier ni permissions
- [x] Lot 11.10 — Système de boutons SaaS unifié livré sur portail/prospect/actions staff
- [x] Lot 11.11 — Audit global UI/UX orchestré par sous-agents, corrections header/tabs/empty states/shipping et documentation livrées

## Derniers chantiers transverses

- [x] Lot 1 refonte frontend — Design foundations / shell / navigation implémenté (tokens, shell portail, headers, page heads, formulaires, tables, feedback, skeletons, tabs)

## Blocages
- [ ] Aucun blocage technique immédiat sur le socle Sprint 01
- [ ] Polling tracking, portail client riche, multi-colis avancé et PDF atelier enrichi restent volontairement hors périmètre
- [ ] Paiement et pricing avancé restent volontairement hors périmètre du slice livré
- [ ] Aucun blocage restant sur le slice uploads avant le prochain domaine sensible
- [ ] Le contrôle fichier basique reste volontairement minimal avant le futur contrôle DTF avancé
- [ ] Aucun blocage immédiat sur le socle workflow production livré
- [ ] Aucun blocage immédiat sur le socle scan atelier ; génération visuelle réelle barcode/QR et UI riche restent hors périmètre
- [ ] Durcissement sécurité Sprint 11 reste à compléter séparément (rate limiting, audit renforcé)

## Décisions récentes
- [x] Stack initiale Django + HTMX + Alpine + Tailwind retenue
- [x] Configuration sensible via variables d’environnement uniquement
- [x] `accounts.User` personnalisé et `auditlog` créés dès les fondations
- [x] Stack Docker locale validée avec `db`, `redis`, `web`, `worker`, `nginx`
- [x] Login figé sur email
- [x] `CustomerMembership` introduit pour préparer le scope client
- [x] `Customer` confirmé comme racine de tenant et d’isolation des données client
- [x] Permission staff dédiée `accounts.access_staff_portal` ajoutée
- [x] Routes client et staff séparées côté serveur avec tests d’accès croisé
- [x] `/admin/` confirmé comme surface d’administration technique
- [x] Audit minimal branché sur les changements sensibles déjà exposés
- [x] Test hybride client/staff ajouté
- [x] Catalogue / pricing / commandes initialisés comme premier vertical slice métier
- [x] `Customer` maintenu comme frontière de tenant pour tous les futurs objets métier client
- [x] Routes `api/client/...` et `api/staff/...` étendues au catalogue et aux commandes avec scoping serveur
- [x] `OrderService.create_order` durci pour refuser tout scope acteur / `Customer` incohérent
- [x] Permissions staff de lecture découpées par domaine pour catalogue et commandes
- [x] Test explicite d’injection de prix ajouté côté API
- [x] App `uploads` initialisée avec scoping serveur strict et permission staff dédiée
- [x] Téléchargement des fichiers de commande médié exclusivement par backend
- [x] Validation centralisée MIME / taille / fichier vide ajoutée côté serveur
- [x] Sprint 04 cadré autour du contrôle fichier basique et des métadonnées sûres
- [x] `OrderUploadInspection` ajouté comme rapport de contrôle basique rattaché à l’upload
- [x] Endpoint client scoped et endpoint staff séparé ajoutés pour la consultation du contrôle
- [x] Permission staff dédiée `uploads.view_orderuploadinspection` ajoutée pour la lecture du rapport
- [x] Statuts `ok` / `warning` / `error` et extraction PNG/JPEG de base validés par tests
- [x] Sprint 05 Google Drive cadré autour d'un Shared Drive unique, d'un mapping des IDs Drive et d'un backend source de vérité
- [x] `OrderDriveFolder` et `OrderUploadDriveSync` ajoutés pour persister l'arborescence et le statut de sync Drive
- [x] Tâche Celery minimale de sync Drive branchée avec audit de queue/succès/échec
- [x] Endpoint staff séparé de consultation Drive ajouté avec permission dédiée `uploads.view_orderuploaddrivesync`
- [x] Aucune route client n'expose d'ID Drive ni de lien brut ; la non-régression `accounts/customers/orders/uploads` est validée
- [x] App `production` dédiée introduite pour isoler le workflow atelier du domaine commande
- [x] `ProductionJob` et `ProductionJobTransition` ajoutés avec historique de transitions et audit de changement de statut
- [x] Endpoints staff production séparés ajoutés avec permissions dédiées de lecture et de transition
- [x] `OrderService.create_order` initialise le socle de workflow via le service dédié sans logique critique dans la vue
- [x] Aucune route client n'expose les données production internes ; la non-régression `orders/customers/accounts/uploads/production` est validée
- [x] `ProductionJob.scan_identifier` opaque et unique ajouté avec génération automatique
- [x] `ProductionJobScanLog` ajouté pour historiser résolution, transition et refus de scan
- [x] Endpoints staff scan séparés ajoutés avec permissions dédiées `scan_productionjob` et `scan_transition_productionjob`
- [x] La transition par scan réutilise strictement `ProductionWorkflowService` et ne contourne pas la matrice centrale
- [x] La non-régression ciblée `orders/uploads/accounts/customers/production` est validée après ajout du scan atelier
- [x] App `shipping` dédiée introduite pour isoler l’intégration Sendcloud du domaine commande
- [x] `Shipment` lié à `Order` ajouté avec stockage label, tracking, statut et références Sendcloud
- [x] La création d’expédition reste staff-only, centralisée dans un service dédié et conditionnée à `ready_to_ship`
- [x] Permissions staff dédiées `shipping.view_shipment` et `shipping.create_shipment` ajoutées
- [x] Aucune route client n’expose le domaine shipping et aucun secret Sendcloud n’est sérialisé
- [x] La non-régression ciblée `orders/uploads/accounts/customers/production/shipping` est validée
- [x] App `portal` ajoutée pour livrer des pages Django templates + HTMX client/staff sans mega-endpoint backend
- [x] Surface client livrée : dashboard, liste commandes, détail et blocs uploads/inspection/production/shipping
- [x] Surface staff livrée : dashboard, fiche commande consolidée, panneaux production/uploads/inspection/drive-sync/shipping/scan
- [x] Les permissions backend existantes restent la source de vérité ; les panneaux staff appliquent des checks domaine par domaine
- [x] Stabilisation Sprint 09: tests shipping API réalignés sur le contrat Sendcloud actuel (3 échecs résolus)
- [x] Commande de seed recette `seed_sprint09_recipe` ajoutée pour validation manuelle client/staff/admin avant sprint paiement
- [x] Micro-lot final UX/auth: login portail dedie `/login/`, redirection post-login staff/client, redirection anonyme portail hors `/admin/login/`
- [x] Correctifs P1 UX: creation shipment masquee si deja creee, message production client clarifie, loading HTMX plus visible
- [x] App `billing` ajoutee avec modeles `Payment`/`Invoice`, routes client/staff/backend dediees et services centralises
- [x] Confirmation/capture PayPal tokenisee cote backend avec idempotence minimale et audit succes/echec
- [x] Facture simple generee automatiquement apres paiement capture et exposee en lecture client scopee
- [x] Mini-lot Sprint 10.1: reserve QA shipping levee par realignement de tests services obsoletes sans changement de contrat metier
- [x] Sprint 11 UX: composant `alert` et hierarchie visuelle portail harmonises sur dashboards/listes/details
- [x] Sprint 11 UX: panneaux `Facture` client et `Billing` staff ajoutes avec permissions backend conservees
- [x] Sprint 11 UX: feedback HTMX renforce (indicateurs, anti double-submit, erreurs/succes lisibles) et tests UI de securite etendus
- [x] Micro-sprint 11.1 bis: homepage premium (`/`) et page services (`/services/`) ajoutees en Django templates
- [x] Micro-sprint 11.1 bis: tunnel client 4 etapes ajoute sous scope customer avec upload HTMX et resume sticky
- [x] Micro-sprint 11.1 bis: tests UI checkout ajoutes (creation commande, upload, cross-tenant)
- [x] Micro-sprint 11.2: landing `/` refondue en sections conversion (hero, reassurance, pourquoi nous, services, process, preuve, CTA)
- [x] Micro-sprint 11.2: templates landing modularises en partials + styles dedies dans `app.css`
- [x] Micro-sprint 11.2: test landing anonyme et presence des sections obligatoires ajoute
- [x] Micro-lot 11.3: wording portail client/staff harmonisé et plus produit
- [x] Micro-lot 11.3: checkout client rendu plus guidé sans changement de logique métier
- [x] Micro-lot 11.3: landing/services clarifient mieux les entrées prospect vs client existant
- [x] Micro-lot 11.3: panneau shipping staff recomposé pour séparer état, sync et création
- [x] Micro-lot 11.4: tunnel prospect `step2/3/4` homogénéisé au niveau qualitatif de `step1`
- [x] Micro-lot 11.4: formulaires staff mieux normalisés (labels, aides, actions, erreurs)
- [x] Micro-lot 11.4: hiérarchie de lecture staff renforcée sur la fiche commande
- [x] Micro-lot 11.4: feedback HTMX local ajouté sans changement de logique métier
- [x] Micro-lot 11.4: page services enrichie par bénéfices, cas d'usage et réassurance
- [x] Micro-lot 11.5: landing enrichie par preuves B2B, exemples d'usage et signaux premium plus concrets
- [x] Micro-lot 11.5: tables portail raffinées (densité, anomalies, regroupements légers)
- [x] Micro-lot 11.5: skeletons rendus visibles dans les chargements HTMX principaux
- [x] Micro-lot 11.5: cohérence iconographique renforcée sur les onglets workflow
- [x] Micro-lot 11.6: hardening transverse UI appliqué sur shell, navigation, page heads, badges, workflow et feedback sans impact métier
- [x] Micro-lot 11.7: landing/services et tunnel prospect renforcés visuellement sans changement de logique métier
- [x] Micro-lot 11.8: landing éditoriale renforcée et dashboards client/staff hiérarchisés avec tables plus premium
- [x] Micro-lot 11.8: shells landing et tunnel prospect restaurés pour contenir les sections, supprimer l'effet bord a bord et garder une cohérence avec le shell global
- [x] Micro-lot 11.9: breadcrumbs profonds, login, checkout, panels uploads/billing, tabs HTMX, fallback menu mobile et labels prospect alignés sur le product-shell brutaliste
- [x] Micro-lot 11.10: système de boutons SaaS unifié (`ui-btn`) appliqué aux actions portail/prospect avec hiérarchie primaire/secondaire, états focus/loading et cible tactile 44px
- [x] Micro-lot 11.11: audit global des vues par app orchestré avec sous-agents ; nav SaaS, tabs `?panel=`, états vides, shipping staff et langage staff harmonisés

## Vague 2 — Sprints ciblant les fonctionnalités manquantes (vision V1)
- [x] Sprint 14 — Emails transactionnels (`docs/sprints/sprint-14-emails-transactionnels.md`) — base livrée (`apps.notifications`, hooks commande / paiement / B2B)
- [x] Sprint 15 — Durcissement sécurité prod (`docs/sprints/sprint-15-durcissement-securite-prod.md`) — rate limit + audit/login + `SECURITY_BASELINE.md`
- [x] Sprint 16 — PDF métiers facture + OF (`docs/sprints/sprint-16-pdf-documents-metier.md`) — ReportLab + lien staff panneau production
- [x] Sprint 17 — Logistique Sendcloud avancée (`docs/sprints/sprint-17-logistique-sendcloud-avancee.md`) — sync tracking API + client + Celery
- [x] Sprint 18 — Pricing & B2B avancé (`docs/sprints/sprint-18-pricing-b2b-avance.md`) — tests encours + email tarifé + doc

## Documentation produit & UX (suivi)
- Modèle B2B (produit, parcours, grille, laize, encours) : `docs/architecture/B2B_PRODUCT_AND_OPERATIONS.md`
- Architecture technique commandes B2B facturation différée : `docs/architecture/B2B_DEFERRED_BILLING.md`
- Audit UI/UX portail client (score, backlog P1–P3) : `docs/product-design/AUDIT_PORTAIL_CLIENT_UI_UX_2026.md`
- Audit global UI/UX des vues par app : `docs/product-design/AUDIT_GLOBAL_UI_UX_VUES_2026-06-14.md`
- Index product design : `docs/product-design/README.md`

## Sprint 19 — Operational readiness (2026-07-10)

- [x] Découverte complète des tests et boucle Ruff Python 3.12 rétablies
- [x] Celery Beat ajouté aux stacks locale et production
- [x] Polling Sendcloud périodique activé hors settings de développement
- [x] Emails transactionnels asynchrones avec retries Celery
- [x] Variables production et HSTS documentés
- [x] HTMX et Alpine.js auto-hébergés, npm/pip audit sans vulnérabilité connue
- [x] Suite complète : 261 tests passés sous Python 3.12
- [x] Builds Docker local/production et smoke des six services validés
- [ ] Recette avec secrets et APIs réels sur l’environnement cible

## Sprint 20 — Frontend UI/UX haute performance (2026-07-10)

- [x] Hero mobile recentré sur le CTA et les preuves prioritaires
- [x] Polices auto-hébergées et runtime marketing allégé
- [x] Compression gzip et cache statique Nginx activés
- [x] Aucun overflow horizontal à 375 px et console navigateur propre
- [x] Lighthouse mobile : 98 performance, 100 accessibilité, 100 bonnes pratiques, 100 SEO
- [x] Suite complète : 265 tests passés
- [x] Recette globale desktop/mobile : public, tunnel prospect, portail client et backoffice staff
- [x] Contrastes, boutons, badges, cartes, checkout et steppers harmonisés
- [x] Menu prospect lisible et erreur JavaScript HTMX des onglets supprimée
- [x] Lighthouse tunnel/connexion : 99 performance, 100 accessibilité, 100 bonnes pratiques
- [x] UI/UX Pro Max : design system maître et overrides par famille de vues
- [x] Navigation clavier : lien d’évitement et repère principal uniques sur toutes les surfaces
- [x] Lighthouse UI/UX Pro Max : 98–100 performance et 100 accessibilité/bonnes pratiques
- [x] Suite complète finale : 267 tests passés
- [x] Correctif final accessibilité : titres séquentiels checkout/client/staff, 268 tests passés
- [x] Connexion premium sans exposition client/staff et logo unique sur toutes les surfaces, 270 tests passés
