# Audit front-end global — cohérence brutaliste & motion (Prenium DTF)

Date : 2026-06-20
Méthode : lecture du design system source (`static_src/css`), crawl navigateur du rendu réel sur `http://localhost:8080` (Docker actif), captures desktop des surfaces clés (landing, login, dashboard staff, liste + fiche commande staff, tunnel prospect), analyse des composants partagés et des templatetags de statut.
Référence de style demandée : skill `ui-ux-pro-max` — orientation « brutalist elements, motion-driven animations, case study previews, team showcase, contact form ».

## Synthèse exécutive

Le projet est **déjà majoritairement néo-brutaliste et cohérent**. Le langage visuel (Space Grotesk display, DM Sans/Manrope corps, bords carrés, bordures 2px, ombres dures `Npx Npx 0`, accent acid `#dcff1a`, secondaires cyan/pink/orange) est partagé sur trois couches :

| Couche | Classe body | Thème | État |
| --- | --- | --- | --- |
| Marketing (landing, services) | `ui-marketing-body` | Brutalist **clair** (paper `#fff8ea`) | Solide — hero, case studies, proof, team, FAQ, contact, CTA déjà en place |
| Portail client + staff | `product-shell` | Brutalist **sombre** (`#0b0d10`) | Solide — header, KPI, panneaux, onglets workflow, tables cohérents |
| Tunnel demande d'accès | `prospect-tunnel-page` | Brutalist **sombre** (override `--product-*`) | Bon, migration brutaliste quasi terminée |

La landing répond déjà au brief « case study previews / team showcase / contact form ». **Le travail utile n'est donc pas une refonte, mais la correction de défauts transversaux de finition** qui cassent la cohérence et l'accessibilité.

## Score

| Axe | Score | Commentaire |
| --- | --- | --- |
| Cohérence du langage visuel | 88 / 100 | Brutalisme homogène ; reste des reliquats legacy (pills arrondis) |
| Accessibilité (contraste) | 72 / 100 | Badges de statut sous le seuil AA sur fond sombre |
| Motion / vivacité | 70 / 100 | Landing animée (reveal + marquee) ; portail statique |
| Cohérence éléments (pills/eyebrows) | 75 / 100 | Mélange carré-acid vs arrondi-amber selon l'écran |
| Densité / lisibilité ops | 90 / 100 | Tables et panneaux bien structurés |

## Backlog priorisé

### P1 — Badges de statut illisibles et arrondis (transversal portail)
- **Constat** : `<span class="badge {{ status|badge_tone }}">` s'appuie sur `.badge` de `legacy/app-legacy.css` (`border-radius:999px`, fonds `color-mix(... 8%, white)` pensés pour fond clair) et **n'est pas redéfini** sous `body.product-shell`. Sur le fond sombre, les badges (« Soumise », « Facturation différée », « Prix calculé », « Encours OK ») apparaissent gris très faible contraste et **arrondis**, en rupture avec le carré brutaliste.
- **Surfaces touchées** : fiche commande staff (`order_detail`), fiche commande client, panneaux `production`, `shipping`, `scan`, `inspection`, `billing`, `drive_sync`.
- **Cause** : aucun sélecteur `body.product-shell .badge`. Le badge par défaut (mode facturation, pricing status) n'a même pas de tonalité → texte sombre invisible.
- **Correctif** : override brutaliste des `.badge` et tonalités sous `product-shell` (carré, bordure 2px, palette alignée sur les `.alert` sombres, contraste ≥ AA).

### P2 — Incohérence des eyebrows / kickers (tunnel)
- **Constat** : sur le tunnel, les eyebrows oscillent entre **acid carré** (`DEMANDE D'ACCÈS ATELIER`, `IDENTITÉ & CONTACT`) et **amber arrondi faible contraste** (`ACCÈS ATELIER PRENIUM`).
- **Cause** : `.landing-kicker--pill` (steps 1–4) garde l'identité legacy amber (`border-radius:999px`, `rgba(143,61,31,.35)`), non couverte par l'override brutaliste de `prospect-tunnel.css`.
- **Correctif** : intégrer `.landing-kicker--pill` au groupe eyebrow brutaliste (carré, accent acid).

### P3 — Motion d'entrée absente sur le portail
- **Constat** : la landing a révélation au scroll + marquee. Le portail (`product-shell`) n'a que des micro-interactions hover ; aucune entrée animée alors que le brief insiste sur « motion-driven ».
- **Correctif** : révélation d'entrée subtile et staggerée sur les grilles principales du portail (dashboard, KPI, command grid), strictement `prefers-reduced-motion: no-preference`, sans rejouer sur les swaps HTMX (cibler les enfants de layout, pas les cibles de panneau).

### P3 — Finitions secondaires (non bloquantes)
- Pills meta header (`portal-top-meta__pill`) restent arrondis : acceptable (méta, non statut) mais à harmoniser à terme.
- Bloc « Étape suivante » de la fiche staff rendu en texte nu hors carte.
- Titre fiche commande : UUID qui wrappe (lisible mais peu élégant ; envisager troncature + mono).

## Correctifs appliqués dans ce lot

- P1 — Override brutaliste des badges de statut sous `product-shell` (`components/product-shell.css`).
- P2 — Harmonisation `.landing-kicker--pill` en eyebrow carré acid sur le tunnel (`components/prospect-tunnel.css`).
- P3 — Révélation d'entrée staggerée sur les grilles portail, reduced-motion safe (`components/product-shell.css`).

## Finitions P3 appliquées (lot 2)

- **Pills meta header** (`portal-top-meta__pill`, `product-pill`) : carré + bordure 2px + texte `--product-ink` (cohérence brutaliste). (`components/product-shell.css`)
- **Bloc « Étape suivante »** (`workflow-next-action`) : passé d'un texte nu à une **carte accent** (bord gauche acid 6px, ombre dure, label acid). Gain UX direct : la prochaine action est désormais visuellement prioritaire sur la fiche staff. (`components/product-shell.css`)
- **Titre fiche commande (UUID)** : `<code>` du `title_code` rendu en **puce mono compacte** (`font-size:.5em`, acid, `word-break`), suppression du wrap disgracieux. S'applique aux fiches staff **et** client. (`components/product-shell.css`)
- **Labels de groupe d'onglets** (`workflow-tab-group__label` : PRÉPARATION / ATELIER / CLÔTURE) : derniers reliquats amber arrondis → **acid carré 2px**, cohérents avec les eyebrows. (`components/workflow.css`)

## Revue UX des parcours métier (intuitivité)

Parcours testés en session réelle (client `client.a.owner`, staff) :

| Parcours | Verdict | Observations |
| --- | --- | --- |
| Dashboard client | Intuitif | CTA primaire « Commander maintenant » acid + secondaire « Voir toutes les commandes » ; cartes numérotées 01/02/03 actionnables. |
| Checkout client (3 étapes) | Très intuitif | Stepper carré 1·Demande → 2·Fichiers → 3·Validation, « Parcours guidé » numéroté, réassurance « aucun paiement à cette étape », activation progressive des zones (fichiers/résumé) après création. |
| Fiche commande client | Intuitif | Bandeau KPI (Statut / Facturation / Prix / Encours / Créée le) avec badges désormais lisibles ; onglets groupés Préparation / Atelier / Clôture ; cartes fichiers détaillées (métrage, support, prix ligne, état contrôle). |
| Fiche commande staff | Intuitif | Barre de commande (client + statuts + montant + OF/Drive + « Calculer le prix ») ; carte « Étape suivante » contextualisée par statut/OF ; onglets workflow par zone. |
| Tunnel prospect (4 étapes) | Intuitif | Progression guidée, eyebrows acid homogènes. |

**Conclusion** : les logiques métier sont exposées de façon guidée et cohérente (steppers, prochaine action contextuelle, statuts lisibles). Aucune incohérence de logique relevée ; les seules frictions étaient visuelles (badges, eyebrows, labels de groupe, bloc « étape suivante ») et sont corrigées.

## Lot 3 — Cohérence couleur 100 % (re-thème clair = landing)

Demande : *« cohérence des couleurs, comme la landing page, très lisible pour toutes les vues, cohérence à 100 % »*. Le portail et le tunnel étaient en **thème sombre** (`#0b0d10` / `#0c0a09`), divergents de la landing « agency » **claire** (papier `#fff8ea`, encre `#0b0b0b`, bordures noires, ombres dures, accents acid/cyan/pink/orange).

### Bascule réalisée
- **Tokens `--product-*`** redéfinis sur la palette claire de la landing (papier, encre noire, bordures noires, accents acid `#dcff1a` / cyan `#00b8ff` / pink `#ff3d8b`). (`components/product-shell.css`)
- **Fonds** : grille papier (comme la landing) au lieu des dégradés sombres, sur `body.product-shell` **et** `body.prospect-tunnel-page`.
- **Surfaces** : conversion systématique des `rgba(255,255,255,…)` (panneaux/bordures pensés pour fond sombre) → teintes sombres sur clair ; cartes en panneaux blancs `#fffdf8` + bordure 2px noire + ombre dure `8px 8px 0 #0b0b0b`.
- **Texte** : tous les textes clairs (`#faf7f2`, `#f4f0e8`, `rgba(244,240,232,…)`) → encre `#0b0b0b` / muted `#4c463b`.
- **Acid en texte → pastilles** : l'acid étant illisible en texte sur fond clair, les eyebrows/kickers/labels passent en **pastilles acid à texte noir** (eyebrows portail + tunnel, labels de groupe, UUID).
- **Badges** : blocs colorés à **texte noir** (success vert, warning ambre, danger rose) lisibles sur clair.
- **Legacy non-layered** (`legacy/app-legacy.css`) : le gros bloc `body.landing-saas.portal-shell …` (texte clair / fonds sombres, prioritaire car hors `@layer`) ainsi que le dégradé blanc de `.brand-link` et le bloc `landing-auth-shell` (login) ont été convertis en clair (cartes blanches, bordures/boutons acid, inputs clairs).
- **Tunnel** (`components/prospect-tunnel.css`) : fond papier, champs clairs, cartes de choix blanches + état sélectionné acid (radio activité rose), stepper « done » acid, track multicolore.

### Surfaces vérifiées (navigateur, après rebuild `app.css?v=20260620g`)
Landing (déjà claire), **login**, dashboard client, fiche commande client, **checkout**, liste commandes staff, **fiche commande staff** (barre de commande + montant), **tunnel prospect** (étapes + cartes de choix + état sélectionné) : toutes en palette claire identique, contraste AA, 100 % cohérentes avec la landing.

## Validation

- `npm run build:css` puis `collectstatic` (Docker), cache-bust `app.css?v=20260620g`, redémarrage `web`.
- Tests de cohérence UI : `apps.portal.tests.test_ui_coherence` → **17/17 OK**.
- Re-crawl navigateur de **toutes** les surfaces (client + staff + tunnel + login) : fond papier, bordures noires, ombres dures, accents acid/cyan/pink, textes encre lisibles, badges lisibles.
