# Audit global de cohérence frontend — 10 juillet 2026

## Verdict

Les surfaces publiques, prospect, client et staff partagent désormais une hiérarchie, des composants et des états d'interaction cohérents. Les défauts bloquants observés pendant la recette réelle — textes clairs sur fonds clairs, cartes sans padding, menu prospect invisible, stepper mobile débordant et erreur JavaScript HTMX — sont corrigés.

Direction retenue : **atelier éditorial premium** pour l'acquisition et **SaaS opérationnel clair** pour les portails. Le backoffice Django technique n'entre pas dans ce périmètre produit.

## Matrice de couverture

| Surface | Vues contrôlées | Desktop | Mobile 375 px | Résultat |
| --- | --- | :---: | :---: | --- |
| Publique | Accueil, Services, Connexion | ✓ | ✓ | Navigation, CTA et contraste cohérents |
| Prospect | Étapes 1 à 4 | ✓ | ✓ | Formulaire prioritaire, progression compacte, menu lisible |
| Client | Dashboard, commandes, détail, checkout et panneaux | ✓ | ✓ | Boutons, badges, cartes, uploads et facturation harmonisés |
| Staff | Dashboard, commandes, détail et panneaux opérationnels | ✓ | ✓ | Densité, actions, états et synchronisation Drive harmonisés |

## Corrections livrées

- Tokens sémantiques clairs pour textes secondaires, références, badges, fichiers, couleurs et listes.
- Boutons normalisés : contraste explicite, hauteur tactile minimale de 46 px et focus clavier bleu visible.
- Checkout remis sur une palette claire unique, cartes correctement espacées et résumé non collant sur petit écran.
- Stepper checkout en trois colonnes stables sans débordement horizontal.
- Tunnel prospect mobile condensé pour afficher le formulaire dès le premier écran.
- Header prospect clair : marque, hamburger, liens Services et Connexion lisibles, y compris menu ouvert.
- Cartes commande mobile allégées ; références longues autorisées à se couper sans élargir la page.
- Script inline dupliqué des onglets supprimé ; le runtime HTMX mutualisé traite les cibles `HTMLElement` sans exception.
- Formulaire de création de compte complété avec l'identifiant d'autocomplétion attendu par les gestionnaires de mots de passe.

## Mesures et validations

| Page | Performance | Accessibilité | Bonnes pratiques | CLS |
| --- | ---: | ---: | ---: | ---: |
| Tunnel prospect — étape 1 | 99 | 100 | 100 | 0 |
| Connexion | 99 | 100 | 100 | 0 |

- Console navigateur sur les parcours corrigés : 0 erreur, 0 avertissement.
- Menu prospect mobile : ouverture, fermeture, libellé accessible et contraste vérifiés dans Chromium.
- Contrats de cohérence templates : 22 tests passés.
- Suite complète : 265 tests passés.
- `manage.py check`, Ruff check et Ruff format : validés.
- Stack Docker : six services démarrés et sains.

## Garde-fous

- Ne pas réintroduire de classes de palette sombre dans les cartes checkout claires.
- Utiliser les classes sémantiques `product-*`, les badges partagés et les boutons du shell au lieu de couleurs ponctuelles dans les templates.
- Conserver le runtime mutualisé pour les onglets HTMX ; aucun script inline par composant.
- Vérifier toute nouvelle vue à 375 px et au clavier, avec une cible tactile d'au moins 44 px.

## Backlog non bloquant

- Ajouter des tests E2E persistants pour les parcours authentifiés quand une stratégie de données de recette stable sera arrêtée.
- Mesurer les Core Web Vitals en production avec du RUM ; Lighthouse local reste une mesure de laboratoire.
