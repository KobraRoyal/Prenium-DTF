# Landing DTF — passe Taste et mouvement

## Skill et direction

Le skill `design-taste-frontend` a été installé depuis
[Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill/tree/main/skills/taste-skill)
dans `/Users/kobrasolution/.codex/skills/design-taste-frontend`.
Installation et recette datées du 25 octobre 2026, heure de Paris.

Direction tirée : **The split stage**, seed **1106499781**. Palette et typographies
conservées avec `--keep palette,type`. Parmi les trois directions proposées, la scène
partagée est celle qui sert le mieux l’objet physique et la lecture de l’offre.

Il s’agit d’un restyle de la page existante : le transfert reste dans le hero comme
demandé. La mise en page générale et les parcours fonctionnels sont conservés. Le
blueprint photographique, ses bandes décoratives et le défilement fixé sur toute la
page ne sont pas repris : ils contredisent le hero Hairline imposé et l’absence de
photographies réelles. Aucun nouveau tirage de palette ou de typographie.

Idée : **le transfert floral de Prenium DTF devient la scène matière face au texte**.
L’interaction centrale reste son ouverture au survol, au clavier ou au toucher.

## Changements visuels

- Hiérarchie à cinq rôles : titre principal, titre de section, sous-titre, corps et note.
  Les chiffres, le logo et les schémas conservent leurs contraintes propres.
- Corps de texte à 17 px, notes et commandes remontées à 13 px. Encre pleine pour la
  lecture, couleur secondaire réservée aux légendes.
- Titre du hero monochrome, champ clair pour le transfert et rythme commun aux sections.
- Titres raccourcis pour rester lisibles sur deux lignes, y compris sur tablette.
- Simplification de 52 déclarations anciennes : ombres, bordures et masques inutiles retirés.
  Les guides SVG, les matières et les contrôles prépresse gardent leur fonction explicative.
- Six emplacements photo conservés, sans pictogrammes répétés. La mention de leur statut
  provisoire reste visible. Les photos de production et machines sont toujours à fournir.
- Captures de commande dans une fenêtre commune, sans recadrage destructif, pour garder
  la même hauteur lors du changement de parcours. Le dialogue donne la taille réelle.
- Le slot atelier est contraint à sa colonne ; la relecture visuelle a révélé et corrigé
  un débordement lié à son ancienne hauteur minimale sur tablette.

## Motion et transitions

`dtf-motion.js` ajoute une couche indépendante, sans dépendance de rendu supplémentaire.
La page HTML est visible par défaut. Les animations ajoutent une arrivée et ne conditionnent
jamais l’accès au contenu.

- Entrée du hero en moins de 1,2 seconde : lignes, phrase, actions puis visuel.
- Entrées ponctuelles au défilement : texte et média ont des amplitudes et délais distincts.
- Changements d’onglets, vues alpha et infobulles : animation courte, interruption propre
  lors d’un nouveau choix. Les états et associations ARIA sont mis à jour immédiatement.
- Pression, survol et focus cohérents ; ouverture des menus et dialogues progressive.
- Les animations s’annulent si l’onglet devient caché ou si le mouvement réduit est demandé.
- Mouvement réduit : contenu final et interactions disponibles, sans déplacement animé.
- FAQ et informations tarifaires conservent les disclosures HTML natifs.

## Audit Taste et limites

Lint final sur 22 fichiers : **0 FAIL, 0 WARN**. Les commentaires d’exemption du lint
concernent les déclarations `box-shadow: none` et `backdrop-filter: none`, que le détecteur
signale malgré leur rôle de suppression d’un effet hérité.

Inspection réelle à 1440, 768 et 390 px : **0 FAIL**, avec deux exceptions documentées :

1. `few-pictures` : deux captures de l’interface existent, une seule visible à la fois.
   L’utilisateur a explicitement demandé des placeholders en attendant les photos réelles.
2. `eyebrow` : le détecteur assimile le bandeau Bretagne à une légende au-dessus du titre.
   Ce bandeau d’origine est une demande explicite de l’utilisateur et reste un `<aside>`.

Aucun élément n’est masqué pour contourner le contrôle. Les avertissements restants portent
sur la palette crème imposée par la marque, l’absence de vidéo réelle, la diversité des
tailles des contrôles, un texte de contrôle très petit et un mouvement modéré. L’inspecteur
mesure 15, 13 et 11 éléments animés selon le viewport, contre 2 avant la passe. Il ne compte
pas l’exploration Hairline au survol. Aucun effet décoratif ajouté pour atteindre un quota.

Aucune image ou vidéo externe ajoutée. Les deux captures gardent leurs données et montants
fictifs identifiés ; aucune fausse preuve de production.

## Critique finale

ROUND 2

Seen in one second: le DTF au mètre et une feuille de transfert sur un champ clair.

Idea (one sentence): le transfert floral devient la scène matière face au texte.

Live thing: ouvrir les couches, explorer leurs fonctions et refermer le transfert.

Layout words by section: hero=split / couleur=diagramme / préparation=workstation /
détail=comparateur / textile=outil / transparence=split / galerie=emplacements /
commande=onglets / prix=simulateur / atelier=split / FAQ=liste / CTA=statement.

Scores: design 6.5 · usability 8.5 · creativity 7.0 · content 5.0 → overall **7.1**.

Caps applied: photographies réelles absentes, placeholders explicitement demandés ; le
score de contenu reste plafonné. Il s’agit d’une autoévaluation, pas d’une note de jury.

Top three problems (most visible first), each with the screenshot it shows in and the fix:

1. `desktop-page-02.jpg` : galerie encore provisoire. Remplacer les six emplacements par
   les productions réelles lorsqu’elles seront disponibles.
2. `tablet-fold.jpg` : la scène réserve de l’espace pour ouvrir les couches. Cette réserve
   maintient les commandes stables ; ne pas la remplir d’éléments décoratifs.
3. `mobile-page-02.jpg` : les captures restent petites dans le flux. Leur dialogue à taille
   réelle est indispensable et a été validé au toucher.

## Validation

- 196 tests serveur/UI réussis.
- 7 tests JavaScript réussis : tarifs, annulation des animations, onglet caché, mouvement réduit.
- Régression hero : quatre matières, souris, clavier, toucher, infobulles et fermeture validés.
- Recette : menu, panneaux rapides, hauteur des captures, agrandissement, FAQ et fallback sans JS.
- Aucun débordement à 375, 390, 768, 1024 et 1440 px.
- Lighthouse mobile local : performance 99, accessibilité automatisée 100, SEO 100 ;
  LCP 2,1 s, TBT 0 ms, CLS 0. Mesure de laboratoire, sans garantie en production ni audit WCAG exhaustif.
- Sources, données tarifaires et parcours B2B conservés. Aucun changement de permission,
  de modèle ou de règle de facturation.

Rapports et captures locaux : `.taste-skill/before`, `.taste-skill/final` et
`output/playwright/taste-*`, `output/playwright/dtf-taste-*`. Les fichiers d’audit sont ignorés
par Git ; le présent document conserve les décisions et résultats.
