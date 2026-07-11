# Prenium DTF / IDS Hub — Design system maître

Source de vérité issue de l’audit UI/UX Pro Max du 11 juillet 2026, adaptée à l’identité existante et à la stack Django + Tailwind + DaisyUI (`dui-`) + HTMX + Alpine.

## Direction

- Acquisition : **atelier éditorial premium**, directe, expressive et orientée conversion.
- Produit : **SaaS opérationnel clair**, dense mais scannable, sans effets décoratifs qui gênent la lecture.
- Ne pas remplacer l’identité par une esthétique SaaS générique navy/bleu, du glassmorphism ou des gradients artificiels.
- Une vue possède une action principale ; les actions secondaires restent visuellement subordonnées.

## Fondations

| Rôle | Valeur | Usage |
| --- | --- | --- |
| Fond | `#FFF8EA` | Fond global quadrillé |
| Surface | `#FFFDF8` | Cartes, formulaires et tableaux |
| Encre | `#0B0B0B` | Texte, bordures structurantes |
| Texte secondaire | `#4C463B` | Aides et métadonnées, contraste AA |
| Accent principal | `#DCFF1A` | CTA et états actifs |
| Focus | `#00B8FF` | Focus clavier uniquement |
| Danger | `#FF5470` | Erreurs et actions destructives |
| Avertissement | `#FFB02E` | Anomalies non bloquantes |
| Succès | `#4ADE80` | États terminés/validés |

- Titres : Space Grotesk, 700–900, hiérarchie courte et nette.
- Texte : DM Sans, base 16 px sur mobile, interligne 1,5 minimum.
- Données et références : chiffres tabulaires ou monospace, retour à la ligne plutôt que débordement.
- Espacements : grille 4/8 px ; niveaux principaux 8, 16, 24, 32 et 48 px.
- Bordures : 2 px, angles droits. Ombres dures réservées aux surfaces importantes et actions.

## Composants

- Boutons : `ui-btn` + variante sémantique ; cible minimale 44 × 44 px, état hover/active/disabled/loading et focus visible.
- Formulaires : label toujours visible, aide persistante pour les champs complexes, erreur au niveau du champ, type et autocomplete adaptés.
- Navigation : position et libellés constants ; état actif explicite ; lien « Aller au contenu principal » sur chaque surface.
- Cartes : une structure titre → contexte → action ; pas de couleur sombre ponctuelle sur une surface claire.
- Tableaux : en-tête sticky sur desktop, vue carte ou conteneur maîtrisé sur mobile, aucun débordement de page.
- Badges : texte + couleur ; la couleur seule ne porte jamais le statut.
- Onglets HTMX : deep-link via query string, rôles ARIA, navigation clavier et cible de panneau stable.
- Feedback : indicateur après 300 ms, bouton bloqué pendant l’envoi, toast `aria-live="polite"`, récupération explicite après erreur.

## Responsive et accessibilité

- Breakpoints de recette : 375, 768, 1024 et 1440 px, plus paysage mobile.
- Aucun scroll horizontal global ; les références longues se coupent.
- Ordre DOM identique à l’ordre visuel ; titres séquentiels ; un seul `main` identifié par vue.
- Contraste texte normal ≥ 4,5:1 ; composants et grands textes ≥ 3:1.
- Animations 150–300 ms, uniquement pour expliquer un changement d’état ; `prefers-reduced-motion` obligatoire.
- Ne jamais désactiver le zoom et ne pas dépendre du hover pour une action essentielle.

## Architecture frontend

- Réutiliser les composants dans `backend/templates/components/`.
- Utiliser les tokens/classes sémantiques avant les couleurs Tailwind ponctuelles.
- Conserver le préfixe DaisyUI `dui-` et le runtime HTMX/Alpine mutualisé.
- Toute nouvelle vue doit ajouter ou étendre un test de cohérence dans `backend/apps/portal/tests/test_ui_coherence.py`.

## Définition de terminé UI

- Desktop et mobile inspectés dans un navigateur réel.
- Clavier, focus, contraste, cibles tactiles et reduced motion vérifiés.
- Console sans erreur ; pas de CLS ni de débordement horizontal.
- États loading, empty, error et success présents quand la vue en a besoin.
- Build CSS, tests de cohérence, suite projet et documentation validés.
