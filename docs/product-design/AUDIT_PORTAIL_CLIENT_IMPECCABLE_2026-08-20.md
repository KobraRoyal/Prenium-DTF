# Audit Impeccable — portail client Prenium DTF

**Date :** 20 août 2026

**Périmètre :** toutes les vues frontend du portail client, de l'authentification au suivi de commande, aux projets de commande, aux Gang Sheets et au compte.

**Nature du lot :** audit complet puis implémentation du hardening UI/UX prioritaire ; aucune logique métier, permission ou route n'a été modifiée.

**Objectif :** faire converger le portail vers un SaaS B2B moderne, cohérent et efficace sans perdre le langage visuel propre à Prenium DTF.

## Mise à jour après implémentation — 20 août 2026

Les quatre P1 de l'audit sont corrigés. Le portail conserve son identité « atelier de précision » tout en gagnant une navigation française stable, un dashboard orienté action, un studio mobile compréhensible et des actions sensibles explicites.

| Axe | Avant | Après | Preuve principale |
|---|---:|---:|---|
| Accessibilité | 2 / 4 | **4 / 4** | Contrastes mesurés à 7,83:1 et 7,89:1, suivi en encre noire, cibles 44–48 px, étapes studio nommées. |
| Performance | 2 / 4 | **2 / 4** | Aucun ajout de dépendance runtime ; la séparation plus fine des bundles reste au backlog. |
| Responsive | 3 / 4 | **4 / 4** | Filtres visibles, onglets détail en grille 2×2, workflow studio en grille 2×2, aucun overflow à 375 et 1440 px. |
| Theming | 2 / 4 | **2 / 4** | Nouveau token danger sémantique ; consolidation générale des tokens encore à faire. |
| Implementation Integrity | 3 / 4 | **4 / 4** | Lexique canonique, confirmations contextualisées, contrats Django/HTMX et isolation inchangés. |
| **Total** | **12 / 20** | **16 / 20** | **Résultat professionnel ; dette structurelle limitée aux optimisations P2/P3 restantes.** |

### Livré dans ce micro-lot

- navigation : `Tableau de bord · Commandes · Planches DTF · Créer une commande · Mon compte` ;
- vocabulaire client unifié autour de `Commande à finaliser`, `Commande` et `Planche DTF` ;
- H1 stable et remise volume reléguée en information secondaire sur le dashboard ;
- étapes mobiles `Importer · Composer · Contrôler · Valider`, avec noms accessibles complets ;
- filtres de planches et onglets de commande tous visibles sur mobile ;
- confirmations avant désactivation d'un membre et révocation d'une invitation ;
- contrastes AA et cibles tactiles corrigés sur les éléments signalés ;
- titres de document et états vides client clarifiés.

### Validation de l'implémentation

- build des quatre bundles CSS et `collectstatic` : **OK** ;
- `manage.py check` et Ruff : **OK** ;
- tests ciblés navigation, permissions, équipe, studio et UI : **120 réussis** ;
- suite globale officielle `make test` : **729 réussis, 1 ignoré, 0 échec** ;
- recette authentifiée à 375 et 1440 px : **aucun overflow horizontal** ;
- détail commande mobile : quatre onglets visibles en grille 2×2, chacun à 44 px ;
- studio mobile : quatre actions visibles et nommées, chacune à 48 px ;
- confirmation équipe vérifiée sans soumettre l'action.

## 1. Verdict exécutif initial

Le portail possède déjà une identité forte et crédible : surfaces papier, encre noire, accent acide, typographies Space Grotesk / DM Sans, cadres francs, actions explicites et adaptations mobiles généralement réussies. Il ne ressemble pas à un produit SaaS générique.

Le verdict est néanmoins **PASS WITH DEBT**. La cohérence visuelle perçue est bonne, mais elle n'est pas encore « parfaite » à cause de quatre écarts structurants :

1. trois contrastes réellement non conformes dans le navigateur ;
2. une progression du studio devenue incompréhensible sur mobile ;
3. une architecture de mots et de navigation instable (`Dashboard`, `Commande`, `Projet de commande`, `Gang Sheet`, `Planche`, `Composition`) ;
4. une couche CSS client trop volumineuse et fragmentée entre plusieurs familles de tokens.

### Audit Health Score initial

| Axe Impeccable | Note | Motif principal |
|---|---:|---|
| Accessibilité | **2 / 4** | Trois échecs de contraste, étapes mobiles sans nom utile, quelques cibles sous 44 px. |
| Performance | **2 / 4** | Bundle portail de 343 Ko avant compression, CSS produit monolithique, aperçus de bibliothèque coûteux. |
| Responsive | **3 / 4** | Aucun débordement global à 375 px ; très bonnes cartes mobiles, mais rails horizontaux peu découvrables. |
| Theming | **2 / 4** | Direction forte, mais tokens `--ui-*`, `--product-*` et legacy parallèles, avec 639 couleurs littérales dans les trois feuilles principales auditées. |
| Implementation Integrity | **3 / 4** | Système distinctif et composants solides ; dette de duplication, vocabulaire produit divergent et checkout historique encore présent. |
| **Total** | **12 / 20** | **Acceptable — travail significatif requis avant de parler de cohérence parfaite.** |

### Répartition des constats

| Priorité | Nombre | Lecture |
|---|---:|---|
| P0 | 0 | Aucun blocage total ou parcours inutilisable. |
| P1 | 4 | À corriger avant la prochaine qualification « premium ». |
| P2 | 8 | Fort impact sur efficacité, mobile et maintenabilité. |
| P3 | 4 | Polish et cohérence de finition. |

## 2. Méthode et couverture

L'audit combine :

- lecture des templates, composants, vues Django, CSS et JavaScript associés ;
- navigation réelle authentifiée dans le portail local ;
- captures à **375 px** et **1440 px** ;
- inspection du DOM, des titres, images, cibles interactives et débordements ;
- calcul des contrastes à partir des styles réellement rendus ;
- détection statique Impeccable, puis vérification manuelle de chaque alerte ;
- vérification Django et suite de tests UI ciblée.

Douze parcours ont été contrôlés dans les deux largeurs :

| Vue | Mobile | Desktop | Verdict |
|---|---:|---:|---|
| Connexion | Oui | Oui | Solide et cohérente avec le shell produit. |
| Tableau de bord | Oui | Oui | Structure propre, mais H1 promotionnel au lieu d'orienter l'utilisateur. |
| Mes informations | Oui | Oui | Lisible ; rail de compte légèrement sous la cible tactile interne. |
| Gestion de l'équipe | Oui | Oui | Fonctionnelle ; trop d'actions empilées et actions sensibles sans confirmation. |
| Commandes à finaliser | Oui | Oui | Bonne liste ; vocabulaire « projet/commande » instable. |
| Nouvelle commande | Oui | Oui | Parcours en deux temps clair ; contraste du placeholder date à corriger. |
| Détail d'une commande à finaliser | Oui | Oui | Prochaine action bien mise en avant ; breadcrumb trop petit. |
| Bibliothèque Gang Sheets | Oui | Oui | Très bonne surface visuelle ; terminologie et filtres mobiles à stabiliser. |
| Studio Gang Sheet | Oui | Oui | Outil spécialisé convaincant ; étapes illisibles sur mobile. |
| Création de commande depuis une planche | Oui | Oui | Continuité métier correcte ; vocabulaire interne exposé. |
| Mes commandes | Oui | Oui | Table desktop efficace, liste mobile beaucoup trop longue. |
| Détail de commande et règlement | Oui | Oui | Résumé et panneaux solides ; contraste suivi et onglet hors champ. |

Le chemin `/checkout/` a également été testé. Pour le client audité, il redirige volontairement vers la nouvelle création asynchrone de commande ; le template checkout historique demeure dans le dépôt pour les clients non éligibles.

## 3. Forces à préserver

- **Identité produit propre.** Le langage « atelier de précision » est mémorable et cohérent avec le métier DTF.
- **Structure responsive robuste.** Aucun overflow global, aucune image cassée et un seul H1 par vue contrôlée.
- **Sécurité d'accès visible dans l'architecture.** Les routes objet utilisent des UUID et les vues restent scopées par client ; l'audit n'a demandé aucun assouplissement.
- **Interactions progressives.** HTMX, Alpine, `aria-live`, toasts, états actifs et panneaux de commande sont bien intégrés.
- **Tables/cartes adaptatives.** La majorité des listes passent intelligemment du tableau desktop aux cartes mobiles.
- **États de focus et mouvement réduit.** Les règles `focus-visible` et `prefers-reduced-motion` sont présentes.
- **Studio spécialisé.** Sa densité est justifiée par la tâche et ne doit pas être aplatie en dashboard générique.

## 4. P1 — écarts à corriger en premier

### P1-1 — Rétablir les contrastes WCAG dans les états réellement rendus

Trois combinaisons échouent au seuil **4,5:1** pour du petit texte :

| Élément | Contraste mesuré | Seuil | Source |
|---|---:|---:|---|
| Lien `Suivre le colis` | **1,13:1** | 4,5:1 | accent acide sur panneau clair, `order_detail.html` et `product-shell.css`. |
| Placeholder `Choisir une date` | **2,40:1** | 4,5:1 | couleur muted à 50 %, `product-shell.css:2840`. |
| Action `Supprimer` d'une carte Gang Sheet | **3,06:1** | 4,5:1 | `--product-danger` sur panneau clair, `gang-sheet.css:485`. |

**Correction recommandée :** conserver l'accent acide comme fond ou indicateur et utiliser l'encre noire pour le texte ; créer des tokens `--product-link-on-light`, `--product-danger-text` et `--product-placeholder` vérifiés AA.

**Fichiers concernés :**

- `backend/templates/portal/client/order_detail.html`
- `backend/static_src/css/components/product-shell.css`
- `backend/static_src/css/components/gang-sheet.css`

### P1-2 — Redonner un nom aux étapes du studio sur mobile

À 640 px et moins, `.gang-workflow--editor li > button > span:last-child` passe à `display: none`. Les boutons ne présentent plus que les chiffres `1`, `2`, `3`, `4`, et aucun `aria-label` ne fournit le nom de l'étape. L'utilisateur doit deviner la fonction de chaque étape.

**Correction recommandée :** afficher au minimum le libellé de l'étape active et donner à chaque bouton un nom accessible complet, par exemple `Étape 1 — Importer les fichiers`. Sur mobile, une rangée compacte `1 Importer`, `2 Composer`, `3 Contrôler`, `4 Valider` reste préférable à quatre cercles anonymes.

**Fichiers concernés :**

- `backend/templates/portal/client/gang_sheets/editor.html`
- `backend/static_src/css/components/gang-sheet-studio.css`
- test d'accessibilité clavier/nom accessible du studio.

### P1-3 — Fixer une architecture de navigation et un vocabulaire uniques

La même réalité est nommée de plusieurs façons :

- `Dashboard` dans une interface française ;
- `Nouvelle commande`, `Commande à finaliser` et `Projet de commande` ;
- `Gang Sheet`, `Planche DTF`, `Nouvelle planche`, `Composition` et `Planche autonome`.

Cette variation expose des concepts techniques internes et affaiblit la confiance, notamment entre le menu `Créer une commande`, la bibliothèque et la création à partir d'une planche.

**Lexique cible recommandé :**

| Concept | Libellé client canonique |
|---|---|
| Accueil du portail | **Tableau de bord** |
| Brouillon avant transmission | **Commande à finaliser** |
| Commande transmise | **Commande** |
| Bibliothèque | **Planches DTF** |
| Terme métier secondaire | `Gang Sheet` une seule fois dans l'aide ou le sous-titre. |
| Action principale | **Créer une commande** |

La navigation desktop cible devient : **Tableau de bord · Commandes · Planches DTF · Créer une commande · Mon compte**. Le menu de création conserve les deux intentions : `Importer des fichiers prêts` et `Composer une planche DTF`.

### P1-4 — Faire du dashboard un centre de décision, pas une bannière de remise

Quand le résumé volume existe, son message promotionnel devient le H1 de la page (`ENCORE 20 M POUR -5 %`). Le dashboard n'annonce donc ni sa fonction, ni le compte actif, ni l'état global des commandes.

**Correction recommandée :**

- H1 stable : `Tableau de bord` ou `Bonjour [prénom]` ;
- une carte `Prochaine action` unique et prioritaire ;
- quatre indicateurs sobres : `À finaliser`, `En contrôle`, `En production`, `Expédiées` ;
- la progression de remise volume devient un module secondaire, sous l'action métier ;
- conserver `Commandes à finaliser` et `Commandes transmises`, avec une densité maîtrisée.

**Fichiers concernés :** `dashboard.html`, `client-dashboard.css` et contexte de dashboard pour les compteurs déjà disponibles ou à agréger dans un service.

## 5. P2 — amélioration forte de l'expérience

### P2-1 — Réduire le coût de lecture de « Mes commandes » sur mobile

La page affiche jusqu'à **20 grandes cartes** avant la pagination. Le parcours mobile dépasse plusieurs milliers de pixels et n'offre qu'une recherche textuelle.

Ajouter des filtres HTMX serveur `Statut`, `Période`, `Règlement`, éventuellement `Expédition`, puis afficher 10 éléments sur mobile ou proposer un mode compact. Conserver la table desktop.

### P2-2 — Signaler les contenus horizontaux hors champ

Deux rails sont techniquement défilables mais ne le montrent pas :

- les filtres de la bibliothèque masquent partiellement `Validées` et `Commandées` à 375 px ;
- les onglets du détail de commande masquent `Règlement` jusqu'au scroll.

Ajouter un fondu de bord, un bouton suivant ou une grille à deux lignes lorsque le nombre d'items est stable. Le tab actif doit toujours être ramené entièrement dans le viewport.

### P2-3 — Sécuriser les actions sensibles dans l'équipe

`Désactiver` un membre et `Révoquer` une invitation soumettent immédiatement un formulaire. Ajouter une confirmation explicite avec le nom/e-mail ciblé, ou un toast avec annulation lorsque l'opération est réversible. Sur mobile, regrouper les actions secondaires dans un menu contextuel afin de réduire la hauteur des cartes.

### P2-4 — Appliquer la cible tactile interne de 44 px partout

Écarts mesurés : rail de compte **38–40 px**, selects de rôle **43 px**, recherche Gang Sheets **42 px**, breadcrumb **16–17 px**, lien de suivi **21–22 px**. Certains passent le minimum WCAG 2.5.8 de 24 px grâce aux espacements, mais pas le standard interne du projet.

Les breadcrumbs peuvent rester visuellement compacts tout en recevant un padding cliquable ; les actions principales et champs doivent atteindre 44 px.

### P2-5 — Consolider les tokens dans une seule couche

Les tokens produit principaux vivent au début du fichier `product-shell.css` de 8 562 lignes, tandis que `tokens.css` ne compte que 28 lignes. Les familles `--ui-*`, `--product-*`, `--brand*` et plusieurs couleurs directes se superposent.

Déplacer primitives, couleurs sémantiques, typographie, espacements, rayons, ombres et tailles tactiles dans `tokens.css`, puis faire des composants des consommateurs de tokens. Les valeurs littérales doivent rester réservées aux cas graphiques particuliers, notamment le canvas.

### P2-6 — Scinder les bundles client et staff

`entries/portal.css` importe dans le même bundle des composants client, prospect et staff (`inspection-workbench`, `email-template-workbench`, `access-request-queue`, `billing-statement-panel`, etc.). Le CSS généré `portal.css` pèse **343 413 octets** avant compression et `product-shell.css` **225 551 octets** à lui seul.

Créer au minimum des entrées `portal-client.css`, `portal-staff.css` et `prospect.css`, puis charger `studio.css` uniquement dans le studio. Mesurer le CSS réellement utilisé avant et après.

### P2-7 — Optimiser les aperçus de la bibliothèque

Une page commune transfère environ **195 Ko encodés** lors de l'audit ; la bibliothèque avec les deux aperçus visibles monte à environ **936 Ko**. `loading="lazy"` est déjà présent, ce qui est positif. Ajouter des miniatures serveur adaptées, `width`/`height`, `srcset` et un poids cible par carte.

### P2-8 — Formaliser la fin du checkout historique

Pour les clients utilisant les projets asynchrones, `/checkout/` redirige vers la nouvelle création. Les anciens templates et plusieurs styles `checkout-*` restent cependant actifs pour l'autre branche fonctionnelle. Documenter explicitement cette compatibilité, sa population et son horizon de suppression afin d'éviter deux expériences qui divergent silencieusement.

## 6. P3 — polish de cohérence

1. Harmoniser les `<title>` : `Mes commandes — Prenium DTF`, `Planches DTF — Prenium DTF`, `Studio — Prenium DTF`, sans `Generator Pro` ni mélange français/anglais.
2. Remplacer `Aucun visuel.` par un état vide explicatif et actionnable : `Aucun fichier n'est joint à cette commande.`
3. Corriger le `for` placé sur un `<span>` dans le label de recherche des commandes ; garder soit un vrai `<label for>`, soit le wrapper label sans attribut inutile.
4. Aligner le header sur les règles du design system : le blur et les rayons du shell restent discrets, mais doivent être explicitement assumés ou retirés pour respecter la grammaire à coins droits et sans glassmorphism.

Les bandes supérieures de KPI et d'action suivante ne sont pas considérées comme des « side stripes » bloquantes : elles sont horizontales, sémantiques et restent compatibles avec le langage produit.

## 7. Direction de design cible — « Atelier de précision »

La cible ne doit pas devenir un dashboard bleu, arrondi et interchangeable. Le produit peut gagner en maturité en conservant ses signes distinctifs :

- **surface :** papier chaud, panneaux légèrement contrastés, aucune transparence décorative ;
- **structure :** cadres noirs nets, ombre dure réservée aux éléments prioritaires ;
- **accent :** jaune acide pour les fonds, états et progression, jamais comme petit texte sur fond clair ;
- **typographie :** Space Grotesk pour titres/actions, DM Sans pour lecture ;
- **hiérarchie :** un H1 stable, une prochaine action, un seul CTA primaire par vue ;
- **navigation :** mots métier français stables et distinction claire entre préparation et commande transmise ;
- **densité :** information compacte sur desktop, cartes condensées et filtres accessibles sur mobile ;
- **studio :** surface spécialisée conservée, mais reliée au même shell, aux mêmes tokens et au même lexique.

### Schéma d'une page client standard

```text
Breadcrumb compact
H1 stable + contexte du compte                   Action primaire
Prochaine action / alerte opérationnelle
Indicateurs utiles (si pertinents)
Contenu principal filtrable
Actions secondaires dans le contexte, jamais en concurrence avec le CTA
```

## 8. Séquencement recommandé

### Lot 1 — Harden, 1 à 2 jours

- contrastes P1 ;
- noms accessibles des étapes studio ;
- cibles 44 px prioritaires ;
- confirmations équipe ;
- tests automatisés de contraste/token et noms accessibles.

### Lot 2 — Clarify + Layout, 2 à 4 jours

- lexique canonique et navigation ;
- dashboard centre de décision ;
- filtres et densité de la liste commandes ;
- états vides et titres de document.

### Lot 3 — Adapt, 1 à 2 jours

- rails de filtres/onglets découvrables ;
- cartes mobiles compactes ;
- vérification 320, 375, 768, 1024 et 1440 px.

### Lot 4 — Optimize + Polish, 3 à 5 jours

- tokens consolidés ;
- séparation des bundles ;
- miniatures d'aperçu ;
- suppression ou documentation du checkout historique ;
- recette visuelle finale et budget de performance.

## 9. Fichiers candidats par lot

| Domaine | Fichiers principaux |
|---|---|
| Shell et navigation | `templates/components/nav/portal_client_navigation.html`, `portal_client_create_menu.html`, `static_src/css/components/product-shell.css` |
| Dashboard | `templates/portal/client/dashboard.html`, `static_src/css/components/client-dashboard.css`, vue/service de contexte dashboard |
| Commandes | `templates/portal/client/orders_list.html`, `partials/client_orders_list_results.html`, `order_detail.html`, composants tabs/table, `views_client.py` |
| Compte/équipe | `templates/portal/client/profile.html`, `team.html`, `partials/team_invite_panel.html`, `account-profile.css` |
| Projets | `templates/portal/client/order_projects/*`, `b2b-order-project.css` |
| Gang Sheets | `templates/portal/client/gang_sheets/*`, `gang-sheet.css`, `gang-sheet-studio.css`, `gang-sheet-editor.js` |
| Design system | `static_src/css/tokens.css`, entrées CSS client/staff/prospect, documentation `DESIGN.md` |

## 10. Validation et preuves

### Résultats automatisés

- `python manage.py check` : **OK**, aucun problème.
- Tests ciblés portail/UI/accessibilité : **123 réussis**.
- Première exécution : 122 réussis et 1 erreur de setup car `test_prenium_dtf` était déjà utilisée par une autre session.
- Relance isolée du test concerné avec `--reuse-db` : **1 réussi**.
- Aucun overflow horizontal global à 375 ou 1440 px sur les 12 vues.
- Images cassées : **0** ; images rendues sans texte alternatif : **0**.

### Captures de référence

Les captures sont disponibles dans `output/playwright/` :

- `login-{mobile,desktop}.png`
- `dashboard-{mobile,desktop}.png`
- `profile-{mobile,desktop}.png`
- `team-{mobile,desktop}.png`
- `projects-{mobile,desktop}.png`
- `project-new-{mobile,desktop}.png`
- `project-detail-{mobile,desktop}.png`
- `gang-sheets-{mobile,desktop}.png`
- `gang-sheet-editor-{mobile,desktop}.png`
- `gang-sheet-order-{mobile,desktop}.png`
- `orders-{mobile,desktop}.png`
- `order-detail-{mobile,desktop}.png`

Les scripts reproductibles sont `output/playwright/client_ui_audit.js` et `output/playwright/client_contrast_audit.js`.

### Faux positifs exclus du score

- Les 21 alertes `overused-font` concernent Space Grotesk, police explicitement imposée par `DESIGN.md`.
- Les deux images sans `src` sont des aperçus cachés dont le JavaScript renseigne la source avant affichage.
- La grille CSS est le plan de travail fonctionnel du studio, pas une texture décorative de page.
- Les pseudo-éléments détectés comme `side-tab` sont des bandes horizontales d'état.

## 11. Checklist de définition de terminé de l'implémentation

- [x] Tous les P1 corrigés et couverts par tests.
- [x] Contrastes texte ≥ 4,5:1 et composants non-textuels ≥ 3:1.
- [x] Noms accessibles et navigation clavier validés sur les étapes du studio.
- [x] Lexique client documenté et appliqué aux vues, titres et menus du lot.
- [x] Aucune action sensible d'équipe sans confirmation ou annulation.
- [x] Aucun contenu horizontal important invisible sans affordance sur les vues corrigées.
- [x] Aucune régression d'isolation client, RBAC, CSRF ou route UUID.
- [x] `manage.py check`, tests ciblés et lint verts.
- [ ] Recette à 320, 375, 768, 1024 et 1440 px.
- [ ] Budgets CSS et images mesurés avant/après.
- [x] Documentation du lot et checklist sprint mises à jour.

## 12. Commandes Impeccable recommandées

1. `$impeccable harden` — contrastes, accessibilité, cibles et actions sensibles.
2. `$impeccable clarify` — lexique, navigation et microcopy.
3. `$impeccable layout` — dashboard et densité des listes.
4. `$impeccable adapt` — rails mobiles et cartes compactes.
5. `$impeccable optimize` — bundles CSS et aperçus.
6. `$impeccable polish` — recette finale et cohérence pixel-perfect.
