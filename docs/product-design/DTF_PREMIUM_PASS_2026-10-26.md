# Landing DTF — passe premium, conversion et mouvement (26 octobre 2026)

Audit préalable : `skill-landing-audit-pixel-perfect` + Impeccable `critique` (double évaluation isolée), score initial **56/100**, Nielsen **24/32**. Snapshot : `backend/.impeccable/critique/2026-10-26T12-31-15Z__templates-shop-home-html.md`.

## Décisions conservées

- H1 « Votre DTF. Notre exigence. », titres Caveat, palette crème/corail, hero Hairline : décisions explicites du 25 octobre, non modifiées.
- Douze emplacements photo : pas de photo réelle disponible. Ils restent des réservations honnêtes (« Photo à venir », `role="img"`, aucune action).
- Mention « 6 € HT si fichiers non conformes » : texte commercial validé par les tests, inchangé.

## Livré

| Sujet | Changement | Fichiers |
|---|---|---|
| Placeholders | Épreuve d’impression : repères de coupe, barre de contrôle 8 encres, pastille de statut | `dtf/photo.html`, `dtf-premium.css` |
| Légal (P0) | Pages `/mentions-legales/`, `/conditions-commerciales/`, `/confidentialite/`, accessibles même si l’accueil redirige vers la connexion. Identité via `LEGAL_*` (env) ; champ vide = marqueur « À compléter », jamais une valeur inventée | `apps/core/services/legal.py`, `views.py`, `urls.py`, `templates/shop/legal/*`, `.env.example` |
| Footer | Deux colonnes (Découvrir / Informations), liens absolus vers l’accueil, contact si configuré, cibles 44 px, lien externe annoncé | `dtf/footer.html` |
| Réassurance (P1) | « Demande en 3 étapes · Réponse sous 1 à 2 jours ouvrés · Sans engagement » sous le CTA du hero et du final (faits repris du tunnel prospect) ; trois étapes numérotées dans le final ; FAQ accès complétée | `dtf/access_facts.html`, `dtf/hero.html`, `dtf/final.html`, `dtf/faq.html` |
| Mobile (P1) | Barre d’accès fixe (≤ 820 px), visible seulement après le hero et quand aucun autre bouton d’accès n’est à l’écran ; inerte quand masquée ; absente sans JS et pour les comptes connectés | `home.html`, `js/dtf-sticky-cta.js` |
| Simulateur | Course du curseur = 2 × dernier palier (min 50 m, max 500 m) ; le champ numérique accepte toujours 500 m | `services/marketing.py`, `dtf/pricing.html` |
| Jargon | Gang Sheet, encours, comptant et laize définis à la première occurrence | `dtf/ordering.html`, `dtf/pricing.html`, `dtf/faq.html` |
| Navigation | « Réalisations » (cadres vides) remplacé par « 8 encres » et « Préparation » ; ↗ réservé au lien externe | `dtf/header.html`, partials |
| Partage | `canonical`, `og:url`, `og:image` 1200×630, `twitter:card` | `home.html`, `img/dtf/og-share.jpg` |

`og-share.jpg` : rendu ImageMagick de `img/dtf/transfer-sheet.svg` (rogné) sur fond `#f4f0e6`, sans retouche.

## Mouvement au scroll

Thèse : lire la page est une passe d’impression.

- **Focal** : rail de 3 px sous le header, rempli des 8 encres au fil du scroll (`animation-timeline: scroll(root)`).
- **Épreuves** : repères de coupe puis balayage de la barre d’encres (`clip-path`) à l’entrée des placeholders (`view()`).
- **Listes** : étapes finales et paliers tarifaires arrivent pendant leur entrée dans le viewport ; terminés dès qu’ils sont entièrement visibles.
- **Header** : ombre douce après 120 px de scroll.
- **Barre mobile** : glissement 380 ms, sortie 320 ms.

Tout est sous `@supports (animation-timeline: scroll())` et `prefers-reduced-motion: no-preference` : sans support (Firefox actuel) ou en mouvement réduit, chaque élément est dans son état final. Seuls `transform`, `opacity` et `clip-path` sont animés. La révélation de sections existante (`dtf-motion.js`) n’est pas dupliquée.

## Validation

- `tests/ui/test_dtf_premium_pass.py` (12 tests) + suite UI : 153 passés.
- Suite complète : 1594 passés, 2 échecs préexistants hors périmètre (`tests/core/test_static_assets.py` sur `app.css?v=` dans `base.html` ; `test_ui_coherence` attend l’ancien libellé « Demander votre accès »).
- Navigateur 1920 px et 390 px : pas de débordement horizontal ; rail actif ; barre mobile visible au milieu de page, masquée au final ; pages légales lisibles.
- Détecteur Impeccable : `overused-font` (Space Grotesk, police de marque de `DESIGN.md`, conservée) ; `side-tab` sur le rail de progression = faux positif, ignoré pour ce seul fichier dans `.impeccable/config.json`.

## Reste à fournir avant publication

1. Variables `LEGAL_*` (raison sociale, SIREN/RCS, TVA, siège, directeur de publication, hébergeur, contact).
2. CGV complètes et durées de conservation RGPD (encadrés « en cours de rédaction »).
3. **Incohérence tarifaire** : la landing annonce 6 € HT uniquement si fichier non conforme ; le moteur (`OrderPricingService`, service actif `seed-file-prep`) facture 10 € HT par fichier systématiquement. À trancher côté commercial, puis aligner texte ou catalogue.
4. Photos réelles : passer `image_src` au composant `dtf/photo.html` active l’agrandissement.

## Passe taste-skill — 26 octobre 2026

Outil : skill `design-taste-frontend` (`inspect.mjs`, `lint.mjs`, `assets.mjs`). Palette crème/corail et titres Caveat conservés par décision de marque.

| Mesure | Avant | Après |
| --- | --- | --- |
| Inspecteur | 3 FAIL, 7 WARN | 0 FAIL, 5 WARN |
| Familles de police | 3 | 2 (DM Sans, Caveat) |
| Tailles de texte desktop | 14 | 9 (dont mot-symbole) |
| Réservations photo | 12 | 3 |
| Images réelles | 2 captures | 4 (2 captures, 2 photos sourcées) |
| Lint skill (partials + CSS) | — | 0 FAIL, 0 WARN |

### Lots livrés

1. Hero : bandeau retiré, onglets de couches colorés, flèche retirée.
2. Images : 9 réservations retirées ; dessins de couches en préparation ; Rennes et presse à chaud ; capture Studio au final.
3. Simulateur compact : puces de volume dans le hero, branchées sur `updatePricing()` (`dtf-landing.js`).
4. Typographie : Space Grotesk retirée de la surface, échelle à 6 tailles.
5. Composition : bande noire « 8 encres », introductions 5/7, galerie en grille, mot-symbole du footer.
6. Barre mobile : apparaît à la remontée (seuil 12 px), `dtf-sticky-cta.js`.
7. Nettoyage : repères de coupe, contours, filets et ombres au repos.

### Sources des images

| Fichier | Source | Licence |
| --- | --- | --- |
| `img/dtf/rennes-vilaine-carte-postale.webp` | [AB 9 - RENNES - La Vilaine](https://commons.wikimedia.org/wiki/File:AB_9_-_RENNES_-_La_Vilaine.JPG), numérisée par Claude_villetaneuse | Domaine public |
| `img/dtf/presse-a-chaud.webp` | [HASHIMA HP54 at TechShop Ark Hills](https://commons.wikimedia.org/wiki/File:HASHIMA_HP54_at_TechShop_Ark_Hills.jpg), Pocsywe | CC0 |

Crédit affiché dans le footer de l’accueil (`show_photo_credits=True`). Ce sont des images de contexte : elles ne montrent pas l’atelier IDS.Supply.

### Avertissements restants, assumés

- `palette-cream` : fond crème de la marque.
- `no-footage` : aucune vidéo honnête de l’atelier disponible.
- `side-scroll` : carrousel de préparation, avec commandes et compteur.
- `empty-middle` : piste du carrousel « Le soin commence », largeur pleine voulue.
- `size-count` à 768 px : tailles fluides intermédiaires (clamp).

### Validation

- `tests/ui/test_dtf_premium_pass.py` : 6 tests ajoutés (puces de volume, repli sans paliers, crédits, dessins de préparation, bande noire et capture Studio, deux polices et barre à la remontée).
- Tests mis à jour : nombre de réservations, bandeau retiré, légendes des images réelles, libellé « Demander mon accès pro » dans `test_ui_coherence`.
- Suite complète : 1601 passés, 1 échec préexistant hors périmètre (`app.css?v=` dans `base.html`).
- Mobile 390 px : prix et action dans le premier écran ; couches dépliées sans chevauchement du texte.

### Reste à fournir

Trois photos de résultats (`result-finished`, `result-type`, `result-multicolor`), une photo réelle de l’atelier pour remplacer la carte postale, puis les points 1 à 3 ci-dessus.
