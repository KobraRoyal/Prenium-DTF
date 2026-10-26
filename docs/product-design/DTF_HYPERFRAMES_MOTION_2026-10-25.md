# Landing DTF — motion-graphics et séquences explicatives

## Installation demandée

La commande demandée a été exécutée avec les options non interactives pour Codex :
`npx skills add https://github.com/heygen-com/hyperframes --skill motion-graphics --agent codex --global --yes`.
Le dépôt courant ne publie plus ce skill. Son retrait est documenté par le
[commit officiel 6882293 du 21 octobre 2026](https://github.com/heygen-com/hyperframes/commit/688229314fb219c4317351c25483ecc3c56a519b).

Le skill exact a donc été installé avec le helper `skill-installer`, au dernier état
précédant ce retrait, révision **207c8a4daf6480d697f203784f1fd422727569e3** :
[SKILL.md historique officiel](https://github.com/heygen-com/hyperframes/blob/207c8a4daf6480d697f203784f1fd422727569e3/skills/motion-graphics/SKILL.md).
Destination : `/Users/kobrasolution/.codex/skills/motion-graphics`. Les guides associés
hyperframes, core, CLI, registry, creative et animation proviennent du même état.
Une mise à jour globale Hyperframes supprimerait à nouveau ces skills retirés.

L’installation est disponible dans les prochains échanges. Le contenu a été lu et
appliqué dans cette tâche. Le catalogue officiel a été interrogé pour les primitives
SVG (`svg-stroke-trace`, `svg-mask-reveal`) ; aucune composition générique embarquée.
Une direction motion bornée a été relue par un agent Director en lecture seule.

## Adaptation à la landing

Le livrable demandé est une page interactive dans la stack existante. Les principes
retenus du skill sont : une idée dominante, construction / respiration / résolution,
rythmes distincts, timelines en pause et repositionnables, valeurs déterministes,
état final immobile et preuves à plusieurs temps. La page pilote elle-même la lecture
via `timeline.time(t, false)` ; aucune lecture GSAP autonome ni boucle ambiante.
Il ne s’agit pas d’un projet vidéo exportable Hyperframes et aucun export n’a été demandé.

Le runtime **GSAP 3.15.0** est épinglé dans le lockfile, copié par le build vendor et
servi localement avec sa notice de licence préservée. Ce cœur permet l’interpolation
SVG et la relecture déterministe sans réimplémenter un moteur de morphing. Son
chargement est différé près de la section concernée ; il est absent du parcours
initial en mouvement réduit. Les contrôles HTML restent utilisables en cas d’échec.

## Intention et rythme

**Moment principal : l’ouverture de la palette.** Le contour CMJN reste un repère fixe.
Une seule poussée développe l’enveloppe chromatique ; les quatre noms accompagnent
ce mouvement, puis la scène se stabilise. La géométrie reste illustrative et ne
représente ni une couverture mesurée ni le résultat d’un profil d’impression.

| Temps | État |
|---|---|
| 0–0,2 s | Base CMJN, temps d’accueil |
| 0,2–1,05 s | Dessin du contour |
| 1,3–2,55 s | Ouverture progressive de l’enveloppe SVG |
| 1,9 / 2,5 / 3,1 / 3,7 s | Orange, vert, rouge puis bleu ; apparition de 450 ms |
| 4,15–6,4 s | Lecture finale immobile |

Bouton natif : « Mettre en pause », « Reprendre l’animation », puis « Rejouer la
démonstration ». Les modes Base CMJN / 8 couleurs interrompent la séquence et
appliquent le choix. La légende ne fait pas annoncer chaque accent par le lecteur d’écran.
Le logement de la commande est réservé dans la mise en page pour éviter un saut.
Les noms SVG sont agrandis sur mobile.

**Mouvement de soutien : contrôle du fichier floral.** Un balayage de 2,85 s dessine
brièvement les trois zones à examiner, sans changer l’onglet actif. Un clic ou le focus
dans l’outil interrompt immédiatement ce balayage. Les cercles de détection sont
séparés du marquage de la zone sélectionnée pour éviter les conflits d’état.

## Contrôle, accessibilité et budget

- Démarrage unique lorsque 25 % de la scène est visible.
- Horloge suspendue hors écran et dans un onglet caché ; aucun temps caché accumulé.
- Pause utilisateur persistante après une sortie et un retour dans le viewport.
- Le choix manuel prime sur la séquence ; la reprise nécessite une action explicite.
- Mouvement réduit : état final, pas d’autoplay, commandes de mode instantanées.
- Le hero Hairline, ses quatre matières et ses infobulles restent indépendants.
- Seules les formes SVG concernées changent ; pas de shader, filtre ou flou continu.
- Prix, accès B2B, données, permissions et photographies provisoires inchangés.

## Validation

- **18 tests Python ciblés** réussis : contenu, marque, accès et offre publique.
- **13 tests JavaScript** réussis, dont 6 nouveaux sur l’horloge : visibilité, pause
  utilisateur, reprise sans saut, choix manuel, mouvement réduit et destruction.
- Recette navigateur réelle : lecture complète, pause, reprise, relecture, choix
  manuel, repositionnement déterministe, toucher, mouvement réduit initial ou en
  cours, bibliothèque bloquée et fallback HTML.
- Régressions hero : quatre couches, souris, clavier, toucher, infobulles et Échap.
- Menu, onglets commande, cadre stable des captures, agrandissement, FAQ et sans JS.
- Aucun débordement à 375, 390, 768, 1024 et 1440 px ; aucune erreur JS dans la recette.
- Dix captures examinées à 1440, 768 et 390 px, dont les preuves gamut à
  0 / 2,3 / 3,8 / 6,4 s et analyse à 0 / 1,8 / 2,85 s. Une passe de correction a
  aligné le mode actif sur l’étape CMJN et agrandi les libellés sur tablette.
- Lint Taste ciblé : **0 FAIL, 0 WARN** ; vérification de syntaxe JS et `git diff --check`.
- Lighthouse courant : accessibilité automatisée **100**, SEO **100**. Le score de
  performance est indisponible : erreur de capture de trace `NO_NAVSTART` avec
  Lighthouse 13.5 / Chrome 155. La tentative avec le cache 12.8 a rencontré une
  dépendance Puppeteer manquante. Le score performance 99 de la passe précédente
  ne constitue pas une mesure de cette livraison. Aucun score nouveau n’est inventé.
- Échantillon local de 120 callbacks `requestAnimationFrame` pendant la scène :
  médiane **16,7 ms**, p95 **16,8 ms**, aucun intervalle supérieur à 50 ms. Mesure
  de laboratoire sur cette machine, sans garantie de cadence sur tous les appareils.
- Six services Docker sains ; `/` et `/healthz/` répondent 200.

Les limites commerciales et les emplacements de photographies réelles restent ceux
du dossier initial. Aucune permission, donnée client, règle de prix ou modèle modifié.
La page conserve ses cinq tailles de référence et sa conversion réservée aux professionnels.

Artefacts de recette locaux ignorés par Git : `output/playwright/hyperframes/`.
Le helper de recette CLI a bloqué lors d’une capture car une callback renvoyait une
timeline GSAP assimilée à une Promise. Le contrôle a été corrigé pour ne rien renvoyer ;
la recette a ensuite été exécutée avec Playwright natif sur Chrome, sans framework de tests ajouté.

