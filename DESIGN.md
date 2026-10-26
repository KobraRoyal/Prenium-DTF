---
name: Prenium DTF
description: Portail B2B DTF clair — production cadrée, fichiers contrôlés, suivi atelier.
colors:
  bg: "#f4f0e6"
  surface: "#fbf6ee"
  raised: "#fffdf8"
  ink: "#1a1815"
  muted: "#6b675c"
  line: "#e2dccb"
  brand: "#ff8775"
  brand-strong: "#e65944"
  accent: "#a83bc4"
  focus: "#770176"
  success: "#287451"
  warning: "#8b5d08"
  danger: "#a33b45"
  action-text: "#1a1815"
typography:
  display: {fontFamily: "Space Grotesk, system-ui, sans-serif", fontWeight: 700, lineHeight: 1.05}
  headline: {fontFamily: "Space Grotesk, system-ui, sans-serif", fontWeight: 700, lineHeight: 0.98}
  body: {fontFamily: "DM Sans, system-ui, sans-serif", fontWeight: 400, lineHeight: 1.45}
  label: {fontFamily: "DM Sans, system-ui, sans-serif", fontWeight: 650, lineHeight: 1.35}
rounded:
  sm: "14px"
  md: "16px"
  lg: "18px"
  pill: "999px"
spacing:
  page: "clamp(1rem, 3vw, 1.75rem)"
  section: "clamp(1rem, 2vw, 1.5rem)"
  action: "0.65rem 1.05rem"
components:
  button-primary: {backgroundColor: "{colors.brand}", textColor: "{colors.action-text}", rounded: "{rounded.pill}", padding: "{spacing.action}", height: "2.75rem"}
  button-secondary: {backgroundColor: "{colors.surface}", textColor: "{colors.ink}", rounded: "{rounded.pill}", padding: "{spacing.action}", height: "2.75rem"}
  input: {backgroundColor: "{colors.surface}", textColor: "{colors.ink}", rounded: "{rounded.sm}", padding: "0.65rem 0.8rem", height: "2.75rem"}
---

## Overview

**Creative North Star: « Atelier clair et chaleureux »**

Prenium DTF est une régie prépresse pour des professionnels qui doivent comprendre un état, agir, puis laisser une trace exploitable. La THESIS est : « Prenium DTF makes every production state legible at a glance, with one calm light shell and one coral action per view. » Le monde construit repose sur un fond crème chaud, des panneaux blancs cassé, un header blanc compact, des lignes fines et des marques de contrôle corail.

La story guide chaque surface : fil d’Ariane, titre d’état, badges calmes, puis une seule prochaine action. La landing est **Persuade**; Client, Atelier et Studio sont **Operate**. Le canevas Studio reste clair pour la fidélité prépresse ; ses poignées, guides, sélection et focus utilisent le corail de marque.

Les routes, permissions, modèles, isolation multi-tenant et logique métier restent inchangés. Les parcours essentiels visent WCAG AA : clavier, focus visible, labels explicites, erreurs actionnables, cibles tactiles `2.75rem`, `prefers-reduced-motion` respecté et aucun contenu essentiel dépendant d’un reveal JavaScript.

**Key Characteristics:**

- Header produit partagé (`ui-foundation-nav`) : lockup corail, nav pills, workspace Atelier/Client, menu compte.
- Fil d’Ariane uppercase sous le header sur toutes les vues authentifiées à profondeur > 1.
- Cartes blanches sur fond crème ; badges sage/ambre pour les statuts métier.
- Une action primaire corail par vue, sans prompts dupliqués.

## Colors

La palette est chaude et mate : le crème accueille, le blanc cassé porte, le corail signale l’action et l’accent violet renforce le focus clavier.

### Primary

- **Corail de marque** (`#ff8775`): action primaire, repère lockup, sélection Studio.
- **Corail fort** (`#e65944`): hover et présence renforcée.

### Neutral

- **Fond crème** (`#f4f0e6`): arrière-plan global produit et portail.
- **Surface blanche cassée** (`#fbf6ee`): header, cartes, champs.
- **Surface levée** (`#fffdf8`): panneaux renforcés et cartes de lecture.
- **Encre chaude** (`#1a1815`): texte principal.
- **Encre muette** (`#6b675c`): aide, métadonnées, labels de facts.
- **Ligne sable** (`#e2dccb`): bordures 1px et séparateurs.

### Status

- **Focus accent** (`#770176`): anneau clavier.
- **Succès sage** (`#287451`), **avertissement ambre** (`#8b5d08`) et **danger rouge** (`#a33b45`): états métier.
- **Texte d’action** (`#1a1815`): texte sur boutons corail.

**The Signal Scarcity Rule.** Le corail est réservé aux actions, sélections, focus et marques d’inspection ; il ne remplit pas les surfaces pour les décorer.

**The Brand Override Rule.** Primaire et secondaire d’action sont des variables live (`--brand`, `--accent`) injectées sur `<html>` depuis Identité visuelle Atelier (`/staff/settings/branding/`). Les composants n’écrivent jamais le hex corail ou violet : ils consomment `var(--brand)` / `var(--accent)`. Neutres, statuts et typo ne sont pas configurables Atelier. Détail : `docs/product-design/TOKEN_BRAND_CONTRACT.md`.

## Typography

**Display Font:** Space Grotesk (avec `system-ui, sans-serif`)

**Body Font:** DM Sans (avec `system-ui, sans-serif`)

Space Grotesk structure titres, navigation et chiffres ; DM Sans porte données, formulaires et statuts.

### Hierarchy

- **Display** (700, taille fluide, line-height proche de 1.05): promesse landing et titres majeurs.
- **Headline** (700, échelle compacte à fluide): état principal d’un dashboard ou d’une fiche focus.
- **Title** (700, panneaux et regroupements).
- **Body** (400, environ 0.88–1rem, 1.45–1.55): instructions et données.
- **Label** (650–700, 0.72–0.88rem, uppercase pour facts et breadcrumb).

**The Two-Voice Rule.** Space Grotesk structure et signale ; DM Sans explique et renseigne.

## Layout

Le shell utilise un conteneur jusqu’à `1180px`, un padding horizontal `clamp(1rem, 3vw, 1.75rem)` et des écarts de section `clamp(1rem, 2vw, 1.5rem)`.

Structure type d’une vue Operate :

1. Header fixe blanc (`product-header`, `ui-foundation-nav`).
2. Fil d’Ariane (`ui-breadcrumb`) quand la profondeur le justifie.
3. Titre premium (`page-head--premium`) ou carte focus (`staff-*-focus`, `client-order-summary`).
4. Contenu : table `ui-data-table`, cartes `ui-data-card` ou workspace `details`.

Landing, Client, Atelier et Studio partagent tokens et lockup ; seule la densité varie. Vérification 1440px et 375px sans overflow horizontal.

## Elevation & Depth

La profondeur est tonale d’abord : `bg` crème, `surface` blanche, `line` pour séparer. Ombres douces et chaudes uniquement sur header et cartes levées : `0 8px 24px rgba(83, 67, 43, 0.08)` ; pas d’ombres dures offset.

**The Tonal Tray Rule.** Une surface se distingue par son ton et sa ligne avant de se distinguer par une ombre.

## Shapes

14px pour petits contrôles, 16px pour panneaux courants, 18px pour surfaces majeures, `999px` pour actions, badges, tabs et nav pills. Bordures fines ; pas de style brutaliste.

## Components

### Buttons

`buttons.css` possède primaire, secondaire, ghost et danger, y compris alias `.btn-*`, `.dui-btn-*`. Primaire corail pill `2.75rem` ; secondaire surface bordée ; ghost transparent pour nav et actions tertiaires.

### Inputs / Fields

Surface blanche, bordure `line`, rayon 14px, hauteur `2.75rem`. Focus accent ; erreur danger ; labels et aide explicites via `ui-field-group`.

### Cards / Containers

Cartes blanches bordées `1px var(--line)`, rayon 16–18px. Fiches focus staff/client regroupent identité, badges et facts en grille horizontale séparée par lignes verticales fines.

### Pages d’erreur HTTP

`templates/404.html` réutilise le shell auth Operate (`product-shell--auth`, carte `product-error-card`) : code discret brand, titre Space Grotesk, CTAs `ui-btn`, recours support. Handler : `handler404` dans `config/urls.py`. Visible avec `DEBUG=False`.

### Tables / listes responsives

`shell.css` possède `ui-table-shell`, `ui-data-table`, `ui-data-card`, `ui-mobile-order-card`, `ui-list-pagination`. Breakpoint table/cartes : 960px. `components/portal/pagination.html` et `components/forms/form_actions.html` mutualisent pagination et actions.

### Navigation / Status

Header : lockup corail, label workspace (point vert « Atelier » / « Espace client »), nav pills avec état actif fond corail pâle, dropdown « Outils » staff, menu « Mon compte ». Breadcrumbs : partials `staff_trail.html` et `client_trail.html` ; wrappers par section pour compatibilité.

Badges : pills calmes `is-success`, `is-warning`, `is-danger`, `is-neutral`.

### Studio crop / inspection

Canevas clair ; chrome, toolbar et poignées corail. `studio-polish.css` reste prioritaire sur les règles legacy de l’éditeur.

## Do's and Don'ts

- **Do** réutiliser `portal/layout.html`, `portal_header.html`, `page_head.html` et les partials breadcrumb.
- **Do** utiliser `#f4f0e6`, `#fbf6ee`, `#fffdf8` et `#e2dccb` pour organiser les niveaux.
- **Do** réserver `#ff8775` et `#e65944` aux actions, sélections et repères d’inspection — via `var(--brand)`, jamais en hex recopié dans un composant.
- **Do** vérifier 375px et 1440px, le clavier, les erreurs et `prefers-reduced-motion`.
- **Don't** réintroduire le thème sombre graphite, le lime acide, les ombres dures offset ou le glassmorphism.
- **Don't** dupliquer pagination, tables, boutons ou breadcrumbs si le contrat `ui-*` couvre le besoin.
- **Don't** ajouter gradients décoratifs, eyebrows ou CTA dupliqués sur une même vue.
- **Don't** créer de styles locaux de table ou header si `shell.css` / `product-polish.css` couvrent déjà le cas.
- **Don't** hardcoder `#8f3d1f` / `#6f2f17` (ancien brun) ni un second écran de thème à côté d’Identité visuelle.

## Surface marketing DTF by IDS Supply — 24 octobre 2026

L’accueil `/` suit une direction technique éditoriale dans le monde clair existant :
ivoire, graphite, actions corail pilotées par `--brand`, Space Grotesk et DM Sans.
Le lockup partagé « Prenium DTF / By IDS.Supply » est identique dans la landing,
les services, la connexion, le tunnel professionnel, les portails et le Studio. Les actions de la landing ont un rayon de 4 px,
les panneaux techniques un rayon de 3–8 px, sans changer les tokens des espaces métier.

Les gradients sont réservés aux encres et aux matières explicatives. Les simulations
sont identifiées ; la galerie attend des photos réelles. La figure originale Hairline
sépare PET, couleur, blanc et adhésif sur un moteur à ressorts qui dort au repos.
Les contrôles restent accessibles au clavier et au toucher, avec mouvement réduit.

La composition, les sources et les hypothèses commerciales sont détaillées dans
[DTF_INTERACTIVE_LANDING_2026-10-24.md](docs/product-design/DTF_INTERACTIVE_LANDING_2026-10-24.md).

### Passe Impeccable — identité B2B et matières

La conversion publique se nomme « Demander votre accès » et conduit au tunnel
professionnel. L’exclusivité B2B est explicite dès le hero et la connexion. Les comptes
connectés gardent leur entrée dans l’espace professionnel.

La vue de transfert se lit du bas vers le haut : film PET, couleur florale, même
silhouette en blanc, poudre granuleuse. La figure et le hero utilisent ce même ordre.
Les infobulles sont spécifiques à chaque matière, accessibles au survol, au clavier
et au toucher, et fermables par Échap. Leur contenu reste survolable ; sur mobile,
il est placé dans le flux pour garder les contrôles dégagés.

### Landing — rédaction, preuve produit et ancrage breton

Chaque section porte un argument distinct. Le bandeau d’origine est discret, défilant,
avec pause explicite ; il devient fixe en mouvement réduit. Les captures du portail
forment une démonstration à deux onglets, annotée données et montants fictifs, avec
agrandissement et taille réelle. La FAQ utilise les disclosures HTML natifs. Les photos
de machines et de résultats restent des emplacements réservés aux images réelles.
Les frais éventuels demeurent visibles avant tout dépliage de conditions.

[Dossier rédaction et médias](docs/product-design/DTF_MARKETING_REFINEMENT_2026-10-24.md).

### Landing — clarté métier, sans fioritures

L’offre est nommée dès le titre : « Votre DTF au mètre ». Les schémas doivent montrer
une opération identifiable, avec un contrôle explicite et une légende courte. Le motif,
les couleurs d’encre et les matières portent l’expression ; repères décoratifs, slogans
redondants et mouvements sans rôle explicatif sont retirés. La préparation de détail
reste locale, les trois traitements de contour restent distincts et les simulations
ne sont jamais présentées comme des résultats de production.

[Dossier de clarté](docs/product-design/DTF_CLARITY_2026-10-24.md).

### Hero — transfert Hairline et diagramme chromatique

Le hero porte l’unique anatomie interactive : film PET fin, motif floral, blanc et
poudre proches au repos, séparés à l’interaction. Chaque matière dispose d’une
infobulle ; les boutons assurent l’équivalence tactile et clavier. L’image statique
du hero et l’ancienne section d’anatomie séparée disparaissent. Le gamut étendu
dispose de son propre schéma explicatif, explicitement sans données de mesure.

[Dossier hero et gamut](docs/product-design/DTF_HERO_TRANSFER_2026-10-24.md).

### Passe Taste — 25 octobre 2026

Le transfert est posé sur un champ clair, face à un titre monochrome. Le corps marketing
est en encre pleine à 17 px ; les légendes et commandes visent 13 px. Les surfaces se
séparent par leurs tons. Les lignes restent dans les schémas et les contrôles techniques.
Les entrées sont ponctuelles ; les changements de panneau et d’infobulle sont courts et
interruptibles. Le contenu HTML reste visible sans animation. Le mouvement réduit et
les onglets cachés annulent les animations en cours.

[Passe Taste et recette](docs/product-design/DTF_TASTE_MOTION_2026-10-25.md).

### Motion-graphics — séquences de lecture, 25 octobre 2026

Le gamut s’ouvre en une poussée SVG, suivie de quatre accents nommés et d’un état
final immobile. La lecture est courte, contrôlable, interruptible et suspendue hors
écran. Le balayage du fichier accompagne les zones à vérifier sans changer la zone
choisie. Les timelines sont déterministes ; le mouvement réduit garde l’état final.

[Installation Hyperframes et recette](docs/product-design/DTF_HYPERFRAMES_MOTION_2026-10-25.md).

### Landing — argumentaire et photographie, 25 octobre 2026

Le premier parcours compte neuf chapitres : offre, résultats, couleurs, préparation,
atelier, commande, budget, FAQ et accès. Les trois démonstrations prépresse approfondies
restent accessibles dans un disclosure natif et par lien direct. Chaque chapitre porte
une question du professionnel, sans réexpliquer le chapitre précédent.

Douze emplacements photo sont répartis dans ce récit, avec deux captures du portail.
Les cadres provisoires sont identifiés et non interactifs. Une source réelle fournie au
composant photo active l’agrandissement. La palette et le hero Hairline restent la référence.

[Argumentaire, prises de vue et recette](docs/product-design/DTF_EDITORIAL_PHOTOGRAPHY_2026-10-25.md).

### Hero — film souple et planche de motifs

Le transfert est placé directement sur le fond crème, sans panneau blanc. Le PET garde
une faible épaisseur et un coin droit relevé ; les deux traits intérieurs sont retirés.
Cinq motifs de tailles différentes remplacent le visuel unique. Leurs silhouettes sont
communes aux encres, au blanc et à la poudre granuleuse. Les contrôles et infobulles
conservent leur lisibilité et les mêmes interactions clavier / tactile.

[Figure Hairline, matières et recette](docs/product-design/DTF_HERO_GANG_SHEET_2026-10-25.md).


## Affinement essentiel — 25 octobre 2026

Une idée par section et une action principale : demander son accès professionnel. Titres plus courts, corps de texte direct, couleurs et typographies de marque conservées. Le carrousel de préparation présente une photo et une explication par étape ; les démonstrations techniques restent dans une divulgation native. Les résultats sont une bande de photos à parcourir. Les douze photographies de production restent explicitement en attente. Pas de rotation automatique des contenus à lire. Les certifications sont attachées aux encres uniquement.

Petites notes de la landing : supprimer les commentaires de construction et les légendes redondantes. Un cadre photo en attente porte seulement son titre et son statut ; une vraie photo peut garder sa légende. Les informations de couche se consultent à la demande. Les précisions commerciales restent dans les conditions et les simulations portent une identification courte.

## Direction actuelle — composition inspirée d’Odoo, 25 octobre 2026

La palette reste exactement celle de la marque : fond #f4f0e6, surface #fbf6ee, surface claire #fffdf8, corail #FF8775, corail clair #FFEAE3, texte #1a1815. Aucun remplacement du logo.

Les h1/h2 utilisent Caveat variable locale, avec licence SIL OFL. Les paragraphes et contrôles restent en DM Sans ; Space Grotesk est conservée dans le logo et certains repères techniques SVG. Le hero est centré en une colonne, suivi de la planche Hairline interactive. L’accent corail derrière « des pros. » reprend le traitement de titre de la référence demandée. Une flèche courbe accompagne le tarif de base près du bouton d’accès, à la demande du 25 octobre.

Introductions des sections centrées ; contenu visuel alterné dans les rubriques couleur, préparation et atelier ; deux sélecteurs de commande compacts ; FAQ sur une colonne. Les cadres de médias ont un rayon de 12 px. La galerie affiche deux images entières sur grand écran, une sur mobile, avec défilement natif. Les douze réservations photo, les prix et les interactions sont conservés. Les petites notes retirées ne reviennent pas.

Les galeries et le carrousel de préparation partagent des commandes de navigation de 44 px. Les photos en attente restent statiques ; les flèches parcourent les cadres. La couleur textile active porte un anneau distinct. Les outils d’analyse se réorganisent sur tablette et leurs onglets s’empilent sur petits écrans pour rester entièrement visibles.

### Tarif et conversion dans le hero — 25 octobre 2026

La landing DTF affiche le tarif public de base dès le hero, près de l’action d’accès B2B, avec une flèche SVG courbe. Le prix est issu du contexte public existant ; largeur, dégressivité mensuelle et exclusions utiles restent explicites. Sur mobile, le prix précède le bouton. Le lien secondaire mène au simulateur. Le fond crème, le corail, les titres Caveat et le transfert Hairline restent canoniques. Voir `docs/product-design/DTF_HERO_CONVERSION_2026-10-25.md`.

### Direction livrée — hero commercial et Hairline visible, 25 octobre 2026

La passe commerciale remplace le hero centré précédent par une grille : « Votre DTF. Notre exigence. », bénéfice de préparation des fichiers et offre à gauche, transfert interactif à droite dès 601 px. Sur téléphone, le transfert et ses quatre commandes précèdent le prix et le CTA, tous deux visibles dans le premier écran au repos aux largeurs de référence. Les titres Caveat, l’accent corail, les motifs, la géométrie et le comportement Hairline sont conservés.

L’action publique est « Demander mon accès pro », accompagnée dans le hero de la validation préalable du compte. Commande et tarifs précèdent les démonstrations techniques. Le simulateur propose directement la demande d’accès avec un lien distinct vers les modes de commande. Les photos en attente restent identifiées et les conditions de prix inchangées.

[Rédaction, composition et recette](docs/product-design/DTF_PREMIUM_HERO_2026-10-25.md).

### Sections livrées — Impeccable, 25 octobre 2026

Le récit après le hero présente la commande et son budget avant les réalisations encore en attente. Les introductions s’alignent en deux colonnes sur grand écran et s’empilent sur téléphone. La capture de commande se lit avec son explication ; les paliers tarifaires utilisent une grille de deux ou quatre colonnes selon la largeur de leur conteneur. Les exclusions restent près du résultat.

Les réservations photo sont plus compactes et explicitement identifiées. Couleurs, préparation et atelier expliquent le soin de production, avec les mêmes figures et contrôles. Le texte des couleurs précède son diagramme. La FAQ possède une introduction latérale et le final rapproche la demande d’accès de la validation du compte. Le hero et Hairline ne changent pas.

[Wording, choix UI et validation](docs/product-design/DTF_PREMIUM_SECTIONS_2026-10-25.md).

### Passe premium — épreuves, légal et passe d’impression, 26 octobre 2026

Les réservations photo prennent la forme d’une épreuve : repères de coupe, barre de contrôle des huit encres et pastille « Photo à venir ». Chaque action d’accès est suivie de trois faits vérifiés (3 étapes, réponse sous 1 à 2 jours ouvrés, sans engagement). Sur téléphone, une barre d’accès apparaît seulement quand aucun autre bouton d’accès n’est visible. Le footer porte conditions commerciales, mentions légales et confidentialité ; une donnée légale absente s’affiche « À compléter ».

Mouvement : le rail de trois pixels sous le header se remplit des huit encres au fil de la lecture ; les épreuves « s’impriment » à leur entrée. Ces effets passent par les scroll timelines CSS, avec état final sans support ou en mouvement réduit. Les gradients restent réservés aux encres. Les pages légales gardent Space Grotesk pour leurs intertitres de lecture.

[Livrables, mouvement et réserves](docs/product-design/DTF_PREMIUM_PASS_2026-10-26.md).

### Passe taste-skill — composition, images et typographie, 26 octobre 2026

Remplace les points contraires des passes précédentes. La landing tient sur deux familles : Caveat pour h1/h2 et le mot-symbole du footer, DM Sans pour tout le reste (y compris les intertitres des pages légales). Space Grotesk ne sert plus sur la surface DTF ; le token portail reste inchangé. Échelle : 14 · 17 · 20 · 36 · 60 · 88 px.

- **Hero** : le bandeau défilant au-dessus du h1 est retiré. Les onglets de couches portent la couleur de leur matière. Les puces de volume (1 m + paliers publics) recalculent le prix sans quitter le hero ; elles restent masquées sans script, le texte « Dégressif selon votre volume mensuel » sert de repli. La flèche courbe est retirée. La mention B2B reste à côté de l’action.
- **Images** : trois réservations seulement, dans « Du motif au textile » (grille de trois sur grand écran). La préparation utilise les dessins de couches (expression, blanc, poudre) sur fond textile noir. Deux images sourcées : carte postale de Rennes (domaine public) dans l’atelier, presse à chaud (CC0) dans la FAQ ; crédits liés dans le footer de l’accueil uniquement. Le final montre la capture du Studio Gang Sheet.
- **Composition** : bande « 8 encres » sur fond textile noir `#222321` ; introductions de section en 5/7 ; footer clos par le mot-symbole « Prenium DTF ».
- **Retraits** : repères de coupe, pointillés et contours des réservations ; filets décoratifs ; ombres au repos (sauf barre mobile flottante).
- **Barre d’accès mobile** : visible seulement en remontant la page, hors hero et quand aucun autre bouton d’accès n’est à l’écran.
- **Mouvement ajouté** : la carte de Rennes se pose, les encres de la bande noire arrivent, le mot-symbole monte. Même garde `@supports` et mouvement réduit.

[Mesures et réserves](docs/product-design/DTF_PREMIUM_PASS_2026-10-26.md#passe-taste-skill--26-octobre-2026).
