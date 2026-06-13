# Sprint UI/UX 1 - Corrections P1 Frontend Premium

## 1. Contexte

- Score UI/UX actuel : 72/100.
- Verdict : presque premium, mais pas encore "premium robuste".
- Audit realise par inspection des templates Django, CSS et JS.
- Aucun rendu navigateur complet ni screenshot automatise disponible a ce stade.
- Le frontend repose sur des templates Django, Tailwind/DaisyUI, CSS legacy/moderne et JavaScript leger.

## 2. Objectif du sprint

Ce sprint vise a corriger les problemes P1 sans refonte massive et sans changement backend metier.

- Clarifier le hero et son objectif de conversion principal.
- Reduire les CTA concurrents au-dessus de la ligne de flottaison.
- Corriger la dette d'animation landing.
- Ajouter un vrai header marketing utilisable sur mobile.
- Valider le responsive P1 avec des commandes Docker Compose.
- Documenter les risques restants et les elements reportes.

## 3. Perimetre inclus

- UIUX-1.1 : Documenter le sprint UI/UX.
- UIUX-1.2 : Clarifier le hero et reduire les CTA concurrents.
- UIUX-1.3 : Corriger le cablage de l'animation landing.
- UIUX-1.4 : Ajouter un comportement mobile au header marketing.
- UIUX-1.5 : Validation responsive P1.

## 4. Hors perimetre

- Refonte complete de la landing.
- Changement backend metier.
- Pagination.
- Durcissement upload.
- Durcissement PayPal.
- Refactoring global CSS.
- Design system complet.
- Checkout stepper.
- Preuves commerciales P2.
- Micro-interactions P3.

## 5. Backlog Sprint UI/UX 1

| ID | Titre | Type | Priorite | Effort estime | Dependance | Statut |
|---|---|---|---|---|---|---|
| UIUX-1.1 | Documenter le sprint UI/UX | Documentation | P1 | 0.5 j | Aucune | Termine |
| UIUX-1.2 | Clarifier le hero CTA | UX / Frontend | P1 | 0.5 j | UIUX-1.1 | Termine |
| UIUX-1.3 | Corriger animation landing | JS / CSS | P1 | 0.5 j | UIUX-1.1 | Termine |
| UIUX-1.4 | Header marketing mobile | UI / Frontend | P1 | 0.5 a 1 j | UIUX-1.2 | Termine |
| UIUX-1.5 | Validation responsive P1 | QA / Documentation | P1 | 0.5 j | UIUX-1.2 a UIUX-1.4 | Termine |

## 6. Tickets detailles

### UIUX-1.1 - Documenter le sprint UI/UX et cadrer l'intervention

- Type : Documentation.
- Priorite : P1.
- Objectif : creer ce document de suivi pour cadrer l'execution du sprint UI/UX frontend premium.
- Fichiers probables : `docs/sprints/sprint-uiux-frontend-premium.md`.
- Etapes techniques : creer le fichier, reporter le contexte d'audit, formaliser le perimetre, detailler les tickets, definir la validation Docker Compose, ajouter la Definition of Done, tracer les risques et initialiser le suivi d'execution.
- Criteres d'acceptation : le document existe, couvre les tickets UIUX-1.1 a UIUX-1.5, contient les commandes Docker Compose, liste les risques transverses et n'introduit aucun changement hors documentation.
- Commandes Docker de validation : `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check .'`.
- Risques : documentation trop large, plan non atomique, confusion entre P1 et P2.
- Dependances : aucune.
- Elements reportes : aucune implementation frontend dans ce ticket.
- Message de commit recommande : `docs(uiux): document frontend premium sprint plan`.

### UIUX-1.2 - Clarifier le hero et reduire les CTA concurrents

- Type : UX / Frontend.
- Priorite : P1.
- Objectif : faire de "Demander un acces pro" le CTA primaire du hero, garder "Voir les services" en CTA secondaire discret et retirer "Espace client" du contenu hero.
- Fichiers probables : `backend/templates/shop/partials/landing_hero.html`, `docs/sprints/sprint-uiux-frontend-premium.md`.
- Etapes techniques : renommer le CTA primaire, conserver un seul objectif principal dans le hero, supprimer ou simplifier la note qui ajoute des liens concurrents, garder l'acces client dans le header uniquement.
- Criteres d'acceptation : le hero affiche un CTA primaire clair, un CTA secondaire discret et aucun lien "Espace client" dans son bloc de contenu.
- Commandes Docker de validation : `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'`.
- Risques : l'acces client peut devenir moins visible tant que le header mobile n'est pas traite.
- Dependances : UIUX-1.1.
- Elements reportes : reecriture copywriting DTF concrete en Sprint UI/UX 2.
- Message de commit recommande : `feat(uiux): clarify landing hero primary conversion path`.

### UIUX-1.3 - Corriger le cablage de l'animation landing

- Type : JS / CSS.
- Priorite : P1.
- Objectif : supprimer la dette silencieuse entre `landing-motion.js`, les classes CSS ciblees et le markup actuel de la landing.
- Fichiers probables : `backend/static_src/js/app.js`, `backend/static_src/js/landing-motion.js`, `backend/static_src/css/legacy/app-legacy.css`, `backend/templates/base.html`, `docs/sprints/sprint-uiux-frontend-premium.md`.
- Etapes techniques : choisir entre brancher proprement l'animation ou supprimer le cablage mort, aligner les selecteurs avec le markup courant, conserver `prefers-reduced-motion`, reconstruire les assets CSS si necessaire.
- Criteres d'acceptation : aucun selecteur d'animation mort critique, animation visible si conservee, comportement accessible si motion reduite.
- Commandes Docker de validation : `docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && npm run build:css'`.
- Risques : regression visuelle si les classes landing sont modifiees trop largement, dependance possible a npm dans l'image Docker.
- Dependances : UIUX-1.1.
- Elements reportes : micro-interactions P3.
- Message de commit recommande : `fix(uiux): align landing motion wiring with current markup`.

### UIUX-1.4 - Ajouter un comportement mobile au header marketing

- Type : UI / Frontend.
- Priorite : P1.
- Objectif : rendre le header marketing utilisable sur mobile avec menu repliable, CTA priorise et liens secondaires accessibles.
- Fichiers probables : `backend/templates/components/nav/landing_header.html`, `backend/static_src/css/input.css`, `backend/static_src/css/legacy/app-legacy.css`, `docs/sprints/sprint-uiux-frontend-premium.md`.
- Etapes techniques : reprendre un pattern proche du header portail, ajouter un bouton menu mobile, gerer `aria-expanded` et `aria-controls`, replier les liens secondaires sous 768px, conserver l'acces client dans le header.
- Criteres d'acceptation : header lisible a 375px, CTA principal accessible, liens secondaires repliables, pas de bloc dense qui pousse le hero hors viewport.
- Commandes Docker de validation : `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'`.
- Risques : conflit CSS legacy / modern, regression mobile, CTA client moins visible si le menu mobile est mal priorise.
- Dependances : UIUX-1.2.
- Elements reportes : refactoring global du design system.
- Message de commit recommande : `feat(uiux): add mobile navigation to marketing header`.

### UIUX-1.5 - Validation responsive P1

- Type : QA / Documentation.
- Priorite : P1.
- Objectif : valider que les corrections P1 preservent la landing, les services, le tunnel prospect et le portail sans changement backend metier.
- Fichiers probables : `docs/sprints/sprint-uiux-frontend-premium.md`.
- Etapes techniques : lancer les commandes Docker Compose, verifier les pages critiques, documenter les resultats, noter les risques restants et les elements reportes.
- Criteres d'acceptation : checks Docker OK, `/healthz/` OK, navigation landing et portail preservee, risques restants documentes.
- Commandes Docker de validation : `curl --fail http://localhost:8080/healthz/`.
- Risques : absence de screenshots automatises, validation visuelle manuelle incomplete.
- Dependances : UIUX-1.2 a UIUX-1.4.
- Elements reportes : screenshots automatises et audit pixel-perfect complet.
- Message de commit recommande : `test(uiux): validate landing p1 responsive fixes`.

## 7. Ordre recommande d'execution

1. UIUX-1.1 documentation.
2. UIUX-1.2 hero CTA.
3. UIUX-1.3 animation landing.
4. UIUX-1.4 header mobile.
5. UIUX-1.5 validation responsive.

Cet ordre reduit le risque car il pose d'abord le cadre documentaire, clarifie ensuite la conversion, traite la dette JS/CSS isolee, puis securise le mobile avant validation globale.

## 8. Commandes Docker globales de validation

```bash
docker compose build web
docker compose up -d db redis web worker nginx
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && npm run build:css'
docker compose exec web sh -lc 'cd /app/backend && python manage.py collectstatic --noinput'
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest'
curl --fail http://localhost:8080/healthz/
```

## 9. Definition of Done

Le sprint est termine si :

- Le hero a un CTA primaire clair.
- L'espace client ne concurrence plus le hero.
- L'animation landing est soit correctement branchee, soit supprimee proprement.
- Le header marketing est utilisable mobile.
- Les validations Docker passent.
- Les risques restants sont documentes.
- Aucun changement backend metier n'a ete introduit.

## 10. Risques transverses

- Absence de screenshots automatises.
- Risque de conflit CSS legacy / modern.
- Risque de regression mobile.
- Risque de CTA client moins visible avant header mobile.
- Dependance possible a npm dans l'image Docker.

## 11. Suivi d'execution

| Ticket | Statut | Fichiers modifies | Resume | Validation | Risques restants |
|---|---|---|---|---|---|
| UIUX-1.1 | Termine | `docs/sprints/sprint-uiux-frontend-premium.md` | Creation du document de suivi sprint UI/UX frontend premium. | Relecture documentaire. | Les validations Docker completes seront lancees lors des tickets d'implementation. |
| UIUX-1.2 | Termine | `backend/templates/shop/partials/landing_hero.html`, `docs/sprints/sprint-uiux-frontend-premium.md` | CTA primaire renomme en "Demander un acces pro" et suppression de la note hero qui exposait "Espace client" et "Commander" comme liens concurrents. | `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` OK ; verification HTML nginx OK sur `http://localhost:8080/`. | L'acces client reste dans le header desktop, mais la priorisation mobile sera securisee dans UIUX-1.4. |
| UIUX-1.3 | Termine | `backend/static_src/js/app.js`, `backend/static_src/js/landing-motion.js`, `backend/static_src/css/legacy/app-legacy.css`, `backend/static_src/css/app.css`, `docs/sprints/sprint-uiux-frontend-premium.md` | Animation landing branchee depuis `app.js`, root corrige vers `.landing-main`, classe `js-landing-motion` ajoutee au runtime et selecteurs hero alignes sur `.landing-stack` / `.landing-command-board`. | `docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && npm run build:css'` echoue car `npm` est absent de l'image ; `npm run build:css` local OK ; `docker compose exec web sh -lc 'cd /app/backend && python manage.py collectstatic --noinput'` OK ; `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` OK. | Verification visuelle navigateur encore a faire ; screenshots automatises reportes a UIUX-1.5 ; dependance npm dans Docker a traiter hors ticket. |
| UIUX-1.4 | Termine | `backend/templates/components/nav/landing_header.html`, `docs/sprints/sprint-uiux-frontend-premium.md` | Header marketing aligne sur le pattern Alpine du portail : bouton Menu mobile, navigation repliee sous 768px, CTA mobile visible vers la demande d'acces et acces client conserve dans le header. | `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` OK ; `curl --fail http://localhost:8080/healthz/` OK ; verification HTML nginx sur `http://localhost:8080/` OK. | Validation visuelle mobile 375px encore a finaliser dans UIUX-1.5 ; screenshots automatises toujours reportes. |
| UIUX-1.5 | Termine | `docs/sprints/sprint-uiux-frontend-premium.md` | Validation P1 realisee sur les corrections hero, animation landing et header marketing mobile. Verification HTML nginx OK pour le CTA primaire, le CTA secondaire, le menu mobile, le CTA mobile et le maintien de l'espace client dans le header. Le CSS compile contient les classes responsive du header mobile et les selecteurs d'animation alignes sur le markup courant. Aucun changement backend metier ajoute dans ce ticket. | `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` OK ; `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check .'` OK ; `docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && pytest ../tests/ui/test_shop_checkout_ui.py ../tests/ui/test_prospect_tunnel_ui.py ../tests/ui/test_portal_ui.py'` OK, 19 tests passes ; `curl --fail http://localhost:8080/healthz/` OK ; verification navigateur desktop sur `http://localhost:8080/` OK. | Screenshots automatises non industrialises ; validation mobile basee sur structure HTML/CSS responsive et controles navigateur/HTML, sans matrice multi-devices complete ; l'image Docker web ne contient toujours pas `npm`, donc la commande Docker `npm run build:css` reste a traiter hors P1. |

## 12. Sprint UI/UX 2 - Copywriting DTF concret et preuves tangibles

### 12.1 Objectif

Renforcer la credibilite et la conversion sans refonte : remplacer le discours meta-produit par des benefices DTF concrets, puis ajouter progressivement des preuves tangibles.

### 12.2 Perimetre inclus

- UIUX-2.1 : Reecrire le hero en benefices DTF concrets.
- UIUX-2.2 : Ajouter des preuves tangibles sur les statuts, fichiers et controles.
- UIUX-2.3 : Clarifier les etapes du parcours avec des exemples metier.
- UIUX-2.4 : Validation copywriting et coherence responsive.

### 12.3 Hors perimetre

- Refonte visuelle globale.
- Changement JS ou animation.
- Refactoring design system.
- Changement backend metier.
- Promesse de delai non validee metier.
- Ajout de donnees commerciales non confirmees.

### 12.4 Backlog Sprint UI/UX 2

| ID | Titre | Type | Priorite | Effort estime | Dependance | Statut |
|---|---|---|---|---|---|---|
| UIUX-2.1 | Reecrire le hero en benefices DTF concrets | Copywriting / UX | P2 | 0.5 j | Sprint UI/UX 1 termine | Termine |
| UIUX-2.2 | Ajouter des preuves tangibles | UX / Frontend | P2 | 0.5 a 1 j | UIUX-2.1 | Termine |
| UIUX-2.3 | Clarifier le parcours avec exemples metier | Copywriting / UX | P2 | 0.5 j | UIUX-2.2 | Termine |
| UIUX-2.4 | Refactor landing metier DTF et validation copy/responsive | UX / Frontend / Copywriting / QA | P2 | 1 j | UIUX-2.1 a UIUX-2.3 | Termine |

### 12.5 Ticket UIUX-2.1 - Reecrire le hero en benefices DTF concrets

- Type : Copywriting / UX.
- Priorite : P2.
- Objectif : rendre le hero plus concret en parlant de fichiers DTF controles, commande cadree, suivi atelier, statuts et reduction des relances.
- Fichiers probables : `backend/templates/shop/partials/landing_hero.html`, `docs/sprints/sprint-uiux-frontend-premium.md`.
- Etapes techniques : conserver la structure existante, reecrire le titre, le lead, le ciblage, les badges et les textes du mockup hero, ne pas modifier les CTA, ne pas ajouter de promesse de delai non validee.
- Criteres d'acceptation : le hero explique un benefice DTF concret, les CTA P1 restent inchanges, aucun JS/CSS n'est modifie, aucune promesse metier non validee n'est ajoutee.
- Commandes Docker de validation : `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'`, `curl --fail http://localhost:8080/healthz/`.
- Risques : copy plus long sur mobile, absence de preuve chiffrees validees, screenshots automatises toujours absents.
- Dependances : UIUX-1.5.
- Elements reportes : preuves tangibles detaillees en UIUX-2.2.
- Message de commit recommande : `copy(uiux): make landing hero dtf benefits concrete`.

### 12.6 Ticket UIUX-2.2 - Ajouter des preuves tangibles

- Type : UX / Frontend.
- Priorite : P2.
- Objectif : remplacer les preuves abstraites par des elements concrets visibles et verifiables : formats fichiers acceptes, controle fichier, inspection et statuts atelier.
- Fichiers probables : `backend/templates/shop/partials/landing_quality_proof.html`, `docs/sprints/sprint-uiux-frontend-premium.md`.
- Etapes techniques : reecrire la section preuves sans modifier sa structure, utiliser des libelles alignes avec le produit existant, eviter les chiffres ou delais non valides, conserver le style visuel existant.
- Criteres d'acceptation : la section preuves mentionne des formats fichiers, un controle fichier, des statuts atelier et un benefice B2B concret ; aucun CSS/JS/backend n'est modifie ; aucune promesse commerciale non validee n'est ajoutee.
- Commandes Docker de validation : `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'`, `curl --fail http://localhost:8080/healthz/`.
- Risques : libelles potentiellement longs sur mobile, preuves encore textuelles sans capture produit, absence de chiffres metier valides.
- Dependances : UIUX-2.1.
- Elements reportes : exemples metier du parcours complet en UIUX-2.3.
- Message de commit recommande : `copy(uiux): add tangible dtf proof points`.

### 12.7 Ticket UIUX-2.3 - Clarifier le parcours avec exemples metier

- Type : Copywriting / UX.
- Priorite : P2.
- Objectif : rendre le parcours "comment ca marche" plus concret avec des exemples DTF lisibles a chaque etape.
- Fichiers probables : `backend/templates/shop/partials/landing_how_it_works.html`, `docs/sprints/sprint-uiux-frontend-premium.md`.
- Etapes techniques : conserver les quatre cartes existantes, remplacer les descriptions generiques, mentionner les informations collectees, fichiers acceptes, controle atelier et suivi client, ne pas modifier le style ni la logique.
- Criteres d'acceptation : chaque etape explique une action concrete du workflow DTF, aucune promesse de delai non validee n'est ajoutee, aucun CSS/JS/backend n'est modifie.
- Commandes Docker de validation : `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'`, `curl --fail http://localhost:8080/healthz/`.
- Risques : texte plus dense sur mobile, preuves toujours textuelles sans capture de workflow, wording a affiner apres revue metier.
- Dependances : UIUX-2.2.
- Elements reportes : validation responsive/copy globale en UIUX-2.4.
- Message de commit recommande : `copy(uiux): clarify dtf workflow steps`.

### 12.8 Ticket UIUX-2.4 - Refactor landing metier DTF et validation copy/responsive

- Type : UX / Frontend / Copywriting / QA.
- Priorite : P2.
- Objectif : refactoriser la landing pour presenter clairement une offre B2B concrete autour de l'impression DTF premium et de la preparation de fichiers techniques DTF.
- Fichiers probables : `backend/templates/shop/home.html`, `backend/templates/components/nav/landing_header.html`, `backend/templates/shop/partials/landing_hero.html`, `backend/templates/shop/partials/landing_services.html`, `backend/templates/shop/partials/landing_why_us.html`, `backend/templates/shop/partials/landing_quality_proof.html`, `backend/templates/shop/partials/landing_reassurance.html`, `backend/templates/shop/partials/landing_how_it_works.html`, `backend/templates/shop/partials/landing_faq.html`, `backend/templates/shop/partials/landing_cta_final.html`, `tests/ui/test_shop_checkout_ui.py`, `docs/sprints/sprint-uiux-frontend-premium.md`.
- Etapes techniques : conserver la structure de partials existante, reorienter le discours vers le metier DTF, integrer les deux offres principales, clarifier probleme/solution/services/cibles/process/expertise/confiance/CTA final, optimiser title/meta description, conserver un H1 unique, mettre a jour les tests UI de contenu.
- Criteres d'acceptation : la page ne se presente plus comme un SaaS abstrait, les services impression DTF premium et preparation fichiers DTF sont explicites, le wording mentionne base blanche et TIFF avec canal alpha de facon prudente, les CTA restent accessibles, aucun backend metier n'est modifie.
- Commandes Docker de validation : `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'`, `docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && pytest ../tests/ui/test_shop_checkout_ui.py'`, `curl --fail http://localhost:8080/healthz/`.
- Risques : refactor copy large a relire sur mobile, absence de screenshots automatises, page services separee encore partiellement alignee sur l'ancien wording.
- Dependances : UIUX-2.1 a UIUX-2.3.
- Elements reportes : harmonisation detaillee de la page `/services/`, screenshots mobile/desktop industrialises, eventuel split de nouvelles sections si un futur besoin design l'exige.
- Message de commit recommande : `copy(uiux): reposition landing around premium dtf services`.

### 12.9 Suivi d'execution Sprint UI/UX 2

| Ticket | Statut | Fichiers modifies | Resume | Validation | Risques restants |
|---|---|---|---|---|---|
| UIUX-2.1 | Termine | `backend/templates/shop/partials/landing_hero.html`, `docs/sprints/sprint-uiux-frontend-premium.md` | Hero reecrit autour de benefices DTF concrets : fichiers controles, commande cadree, suivi atelier, statut de commande et reduction des relances. Les CTA P1 sont conserves sans changement. | `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` OK ; `curl --fail http://localhost:8080/healthz/` OK ; verification HTML nginx sur `http://localhost:8080/` OK avec le nouveau titre et les CTA conserves. | Copy potentiellement dense sur mobile ; preuves tangibles encore a ajouter en UIUX-2.2 ; aucune promesse de delai chiffre non validee. |
| UIUX-2.2 | Termine | `backend/templates/shop/partials/landing_quality_proof.html`, `docs/sprints/sprint-uiux-frontend-premium.md` | Section preuves reecrite avec des elements tangibles alignes sur le produit : formats acceptes, fichiers centralises par commande, controle de type/signature/taille, inspection et statuts atelier. | `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` OK ; `curl --fail http://localhost:8080/healthz/` OK ; `docker compose restart web nginx` effectue pour rafraichir les templates servis ; verification HTML nginx sur `http://localhost:8080/` OK avec les nouveaux points de preuve. | Les preuves restent textuelles, sans captures produit ni chiffres metier valides ; attention a la longueur des libelles sur mobile. |
| UIUX-2.3 | Termine | `backend/templates/shop/partials/landing_how_it_works.html`, `docs/sprints/sprint-uiux-frontend-premium.md` | Parcours recommande reecrit avec des exemples metier DTF : qualification de l'acces pro, commande avec fichiers et quantites, controle atelier, suivi jusqu'a expedition. | `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` OK ; `curl --fail http://localhost:8080/healthz/` OK ; verification HTML nginx sur `http://localhost:8080/` OK avec les nouveaux libelles du parcours. | Texte plus dense sur mobile ; captures workflow et validation copy globale reportees a UIUX-2.4. |
| UIUX-2.4 | Termine | `backend/templates/shop/home.html`, `backend/templates/components/nav/landing_header.html`, `backend/templates/shop/partials/landing_hero.html`, `backend/templates/shop/partials/landing_services.html`, `backend/templates/shop/partials/landing_why_us.html`, `backend/templates/shop/partials/landing_quality_proof.html`, `backend/templates/shop/partials/landing_reassurance.html`, `backend/templates/shop/partials/landing_how_it_works.html`, `backend/templates/shop/partials/landing_faq.html`, `backend/templates/shop/partials/landing_cta_final.html`, `tests/ui/test_shop_checkout_ui.py`, `docs/sprints/sprint-uiux-frontend-premium.md` | Landing refactorisee autour d'une offre metier DTF concrete : impression DTF premium, preparation de fichiers techniques, base blanche, TIFF avec canal alpha, cibles B2B, process atelier, expertise prepress et CTA finaux. Tests UI mis a jour sur les nouveaux messages cles. | `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` OK ; `docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && pytest ../tests/ui/test_shop_checkout_ui.py'` OK, 5 tests passes ; `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check tests/ui/test_shop_checkout_ui.py'` OK ; `curl --fail http://localhost:8080/healthz/` OK ; `docker compose restart web nginx` effectue pour rafraichir les templates servis ; verification HTML nginx OK sur `http://localhost:8080/` avec un seul H1 et les messages cles DTF. | Relecture mobile visuelle encore necessaire ; page `/services/` a harmoniser dans un ticket separe ; pas de screenshots automatises. |

## 13. Sprint UI/UX 3 - Audit et coherence des vues metier SaaS

### 13.1 Objectif

Auditer les vues metier avec le navigateur integre et corriger les incoherences visibles qui degradent la perception premium : page services, tableaux client/staff, surfaces workflow et contraste des composants.

### 13.2 Ticket UIUX-3.1 - Harmoniser services et surfaces metier portail

- Type : UI / UX / Frontend / CSS / QA.
- Priorite : P1.
- Objectif : corriger les bugs visuels critiques observes en navigateur : page `/services/` encore incoherente avec le nouveau positionnement DTF et surfaces de tableaux/workflow trop claires dans le portail sombre.
- Fichiers modifies : `backend/templates/shop/services.html`, `backend/templates/base.html`, `backend/static_src/css/input.css`, `backend/static_src/css/components/shell.css`, `backend/static_src/css/components/workflow.css`, `backend/static_src/css/app.css`, `tests/ui/test_shop_checkout_ui.py`, `docs/sprints/sprint-uiux-frontend-premium.md`.
- Resume technique : realignement copy de `/services/` sur impression DTF premium / preparation fichier ; ajout d'overrides dark theme scoped `body.landing-saas.portal-shell` pour tables, lignes warning/anomaly, flags, workflow tabs, panneaux et command bar ; ajout d'une garde finale apres Tailwind pour eviter les regressions de contraste ; incrementation de version CSS pour contourner le cache navigateur ; mise a jour du test UI marketing.
- Impact UX attendu : lecture plus coherente entre landing et services, suppression des fonds blancs illisibles sur listes commandes et fiches commande, perception plus premium et plus stable du portail client/staff.
- Commandes Docker de validation : `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'`, `docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && pytest ../tests/ui/test_shop_checkout_ui.py ../tests/ui/test_portal_ui.py'`, `docker compose exec web sh -lc 'cd /app/backend && python manage.py collectstatic --noinput'`, `curl --fail http://localhost:8080/healthz/`.
- Commande asset hors Docker : `npm run build:css` depuis `backend/` car `npm` est absent de l'image Docker web.
- Validation navigateur : Browser Use OK sur `/services/`, `/staff/orders/` et `/staff/orders/<public_id>/` apres redemarrage web/nginx ; les lignes warning/anomaly et les groupes workflow restent en theme sombre.
- Risques restants : audit navigateur encore partiel, screenshots automatises non industrialises, autres panneaux profonds peuvent necessiter un second passage visuel, dependance npm Docker toujours ouverte.
- Elements reportes : audit mobile complet 375px, harmonisation fine de tous les panels HTMX apres interaction, eventuelle rationalisation globale des tokens light/dark.
- Message de commit recommande : `fix(uiux): harmonize business views dark surfaces`.

### 13.3 Suivi d'execution Sprint UI/UX 3

| Ticket | Statut | Fichiers modifies | Resume | Validation | Risques restants |
|---|---|---|---|---|---|
| UIUX-3.1 | Termine | `backend/templates/shop/services.html`, `backend/templates/base.html`, `backend/static_src/css/input.css`, `backend/static_src/css/components/shell.css`, `backend/static_src/css/components/workflow.css`, `backend/static_src/css/app.css`, `tests/ui/test_shop_checkout_ui.py`, `docs/sprints/sprint-uiux-frontend-premium.md` | Page services realignee avec l'offre DTF ; surfaces metier portail durcies en theme sombre pour les listes commandes et workflows ; cache CSS incremente pour publier les corrections. | `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` OK ; `docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && pytest ../tests/ui/test_shop_checkout_ui.py ../tests/ui/test_portal_ui.py'` OK, 18 tests passes ; `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check tests/ui/test_shop_checkout_ui.py'` OK ; `docker compose exec web sh -lc 'cd /app/backend && python manage.py collectstatic --noinput'` OK ; `curl --retry 10 --retry-delay 1 --retry-all-errors --fail http://localhost:8080/healthz/` OK apres redemarrage ; Browser Use OK sur services, liste staff et detail staff. | Audit navigateur partiel ; screenshots automatises non industrialises ; dependance npm encore hors image Docker web ; audit mobile complet reporte. |
