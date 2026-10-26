# Lot 11.10 — DTF by IDS Supply, précision à chaque couche

## Objectif

Refondre l’accueil local depuis `main` en vitrine DTF interactive, dans la stack Django
existante. Source du prix : grille par défaut en base. Mention conditionnelle 6 € HT
pour fichiers non conformes, conformément à la précision de l’utilisateur.

## Checklist de livraison

- [x] `main` propre et à jour avant création de la branche de travail.
- [x] Docker local redémarré et volumes conservés.
- [x] Recherche IDS / DTF / Hairline / sources techniques, limites documentées.
- [x] Douze sections françaises, composants de présentation dédiés.
- [x] Figure Hairline DTF originale, ressorts, séparation, couleurs matière.
- [x] Démonstrations détails, contours, blanc et alpha avec limites explicites.
- [x] Textile interactif, comparaison, galerie avec six emplacements honnêtes.
- [x] Grille réelle par défaut et simulateur réutilisable avec arrondis vérifiés.
- [x] CTA et restrictions des parcours vérifiés.
- [x] Tests ajoutés avec la feature, régressions UI et prix.
- [x] Relecture sécurité indépendante sur la lecture publique des tarifs.
- [x] Documentation du lot et du système visuel mises à jour.
- [x] Recette navigateur finale desktop/mobile et réduction des mouvements.
- [x] Vérification finale santé Docker et page HTTP 200.

## Hors publication locale

- Photos de production réelles à fournir pour remplacer les six emplacements.
- Références machine/consommables et promesses commerciales à confirmer avant publication.
- La politique production de redirection vers la connexion reste inchangée.
- Aucune mutation de tarif, frais ou remise dans la base et aucun déploiement distant.

[Dossier de conception, recherche et recette](../product-design/DTF_INTERACTIVE_LANDING_2026-10-24.md).

## Résultats de validation — 24 octobre 2026

- 139 tests pytest réussis (dont 119 UI) et 4 tests JavaScript réussis.
- Revue sécurité indépendante : aucun finding exploitable.
- Recette Playwright : aucun échec ni erreur console ; CTA HTTP 200 ; zéro débordement
  à 375, 390, 768, 1024 et 1440 px ; clavier et mouvement réduit validés.
- Contexte Chromium mobile avec `hasTouch=true` : vrais taps sur couches, textile,
  alpha, galerie et menu validés.
- Hairline : validateur et planche de contrôle réussis, cadre respecté, état stable.
- Lighthouse mobile local : performance **99**, accessibilité automatisée **100**,
  SEO **100** ; LCP **2,0 s**, TBT **0 ms**, CLS **0**. Mesure de laboratoire locale,
  pas de garantie de performance en production ni d’audit WCAG exhaustif.
- Docker : six services sains ; `/healthz/` et `/` répondent 200.

## Suivi utilisateur — passe Impeccable, marque et matière

- [x] Logo et signature partagés : Prenium DTF By IDS.Supply, toutes surfaces.
- [x] CTA publics « Demander votre accès », service exclusivement B2B explicite.
- [x] Film en bas → couleur → blanc → poudre dans le hero et la figure interactive.
- [x] Motif floral coloré et silhouette blanche identique.
- [x] Poudre matérialisée par 466 grains stables, sans particules animées gratuites.
- [x] Infobulles propres aux 4 matières, survolables, clavier/tactile et Échap.
- [x] Recette desktop/mobile, zéro débordement aux cinq largeurs de référence.
- [x] 194 tests pytest et 4 tests JS réussis, contrats publics et portail inclus.

Mesure Lighthouse mobile de la passe Impeccable : performance **99**, accessibilité
automatisée **100**, SEO **100** ; LCP 2,0 s, TBT 0 ms, CLS 0. Rapport local :
`output/playwright/dtf-polish-lighthouse.json`.

## Suivi utilisateur — rédaction métier, FAQ et preuve produit

- [x] Analyse des deux pages Sherpa, rédaction originale et hiérarchie clarifiée.
- [x] Bandeau défilant : Bretagne près de Rennes, B2B, livraison partout en France.
- [x] Pause/reprise, arrêt hors champ/onglet caché et mouvement réduit.
- [x] FAQ de huit questions, dimensions dynamiques et conditions explicites.
- [x] Deux captures réelles de la solution, données et montants fictifs identifiés.
- [x] Onglets, agrandissement, taille réelle et lecture mobile des captures.
- [x] Placeholder machines et résultats conservés, conformément à la réponse utilisateur.
- [x] Mention conditionnelle des 6 € HT visible avant ouverture des conditions.
- [x] Revue indépendante de l’outil de capture et de l’isolation des données.
- [x] 195 tests serveur/UI et 4 tests JS réussis ; recette navigateur sans échec.
- [x] Taps mobiles sur bandeau, captures/zoom et FAQ ; zéro débordement.
- [x] Lighthouse local : performance 99, accessibilité automatisée 100, SEO 100.

[Dossier de cette passe](../product-design/DTF_MARKETING_REFINEMENT_2026-10-24.md).

## Suivi utilisateur — clarté métier et visuels sans fioritures

- [x] Offre et titres explicites, formules redondantes retirées.
- [x] Repères décoratifs et mouvement du hero supprimés, animation matière conservée.
- [x] Trois zones de contrôle identifiées et sélectionnables.
- [x] Comparateur : une seule nervure renforcée, dessin et proportions préservés.
- [x] Carte d’opacité et trame en points opaques ; simulations identifiées.
- [x] Galerie provisoire simplifiée ; captures réelles et conditions conservées.
- [x] 196 tests serveur/UI et 4 tests JS réussis ; recette bureau/mobile sans débordement.
- [x] Lighthouse local : performance 99, accessibilité automatisée 100 et SEO 100.

[Dossier de clarté](../product-design/DTF_CLARITY_2026-10-24.md).

## Suivi utilisateur — transfert dans le hero et gamut étendu

- [x] Une seule figure Hairline, dans le hero ; anatomie séparée supprimée.
- [x] Fine feuille PET, reflet et léger relevé de bord.
- [x] Couches proches au repos, séparation au survol et réassemblage au départ.
- [x] Infobulle propre à chaque couche ; boutons, clavier, toucher et fermeture.
- [x] Diagramme du gamut étendu et deux modes, sans mesure inventée.
- [x] 196 tests serveur/UI et 4 tests JS ; banc Hairline validé et examiné.
- [x] Recette souris/clavier/tactile, infobulles et fermeture ; aucun débordement.
- [x] Lighthouse local : performance 99, accessibilité automatisée 100, SEO 100.

[Dossier hero et gamut](../product-design/DTF_HERO_TRANSFER_2026-10-24.md).

## Suivi utilisateur — skill Taste et motion, 25 octobre 2026

- [x] Skill Taste installé et appliqué, palette et typographies de marque conservées.
- [x] Corps lisible, titres courts, surfaces et commandes harmonisées.
- [x] Entrées du hero et des sections, transitions d’onglets et d’infobulles.
- [x] Réduction des animations, annulation lors d’un changement de vue ou d’onglet caché.
- [x] Cadres des captures stables, contrôles clavier et tactiles préservés.
- [x] 196 tests serveur/UI et 7 tests JS réussis.
- [x] Lint Taste sans échec ; inspection sans échec avec exceptions photos/bandeau documentées.
- [x] Relecture desktop/tablette/mobile et correction du slot atelier sur tablette.
- [x] Lighthouse local : performance 99, accessibilité automatisée 100, SEO 100 ; CLS 0.

[Rapport Taste et limites](../product-design/DTF_TASTE_MOTION_2026-10-25.md).

## Suivi utilisateur — Hyperframes motion-graphics, 25 octobre 2026

- [x] Commande demandée exécutée ; skill exact installé depuis le dernier état officiel disponible.
- [x] Retrait du dépôt courant et révision installée documentés, guides lus et appliqués.
- [x] Gamut : morphing SVG, quatre accents, pause/reprise et relecture, état final immobile.
- [x] Scan du fichier floral : trois zones, interruption au clic ou au focus.
- [x] Timelines déterministes, arrêt hors écran/onglet caché et mouvement réduit.
- [x] Chargement local différé, contrôles de mode utilisables en cas d’échec.
- [x] 18 tests Python ciblés et 13 tests JS réussis ; recette complète desktop/tactile.
- [x] Régressions hero, commande, zoom, menu, FAQ et sans JS validées.
- [x] Preuves temporelles examinées ; aucun débordement aux cinq largeurs.
- [x] Mesure locale : médiane 16,7 ms sur 120 frames ; p95 16,8 ms.
- [x] Lighthouse : A100 / SEO100 ; score performance indisponible (trace NO_NAVSTART).
- [x] Docker sain et documentation mise à jour.

[Dossier motion-graphics, installation et limites](../product-design/DTF_HYPERFRAMES_MOTION_2026-10-25.md).

## Suivi utilisateur — argumentaire et photographie, 25 octobre 2026

- [x] Argumentaire organisé autour des décisions d’achat B2B, copy deck rédigé avant markup.
- [x] Douze chapitres ramenés à neuf ; trois outils techniques réunis dans un disclosure.
- [x] Douze emplacements photo répartis : 5 résultats, 1 couleur, 2 prépresse, 3 atelier, 1 envoi.
- [x] Composant photo réutilisable, sources réelles facultatives et agrandissement prêt.
- [x] Placeholders explicites et statiques ; aucune fausse photo de production.
- [x] Deux captures de commande, tarifs et accès professionnels conservés.
- [x] Liens profonds, clavier, toucher, sans JavaScript et mouvements validés.
- [x] 198 tests Python et 13 tests JS réussis ; aucune erreur navigateur ni débordement.
- [x] Inspection Taste finale sans échec ; dix captures examinées, exceptions documentées.
- [x] Environ 14 % de mots en moins dans le premier parcours, malgré cinq réservations photo supplémentaires.
- [x] Documentation, design et checklist mis à jour ; six services Docker sains.

[Rapport éditorial et plan photographique](../product-design/DTF_EDITORIAL_PHOTOGRAPHY_2026-10-25.md).

- [x] Correctif `broken-image` : balise initiale sans source retirée, création du média uniquement avec une source valide ; 5 tests ciblés réussis et aucune suppression de règle.

## Suivi utilisateur — hero Hairline, film et planche DTF

- [x] Hairline et Impeccable appliqués au hero existant, moteur et bench conservés.
- [x] Coin droit du film légèrement courbé, deux traits intérieurs et long reflet retirés.
- [x] Grand panneau blanc supprimé ; illustration directement sur le fond crème.
- [x] Cinq motifs disposés en planche, silhouettes reprises par le blanc et la poudre.
- [x] 646 grains stables dans les zones imprimées, sans nuage de particules.
- [x] SVG de secours dérivé du même dessin, cinq motifs et gradients locaux.
- [x] 17 tests Python ciblés, 13 tests JS, banc Hairline et recette réelle réussis.
- [x] Souris, clavier, toucher, mouvement réduit et sans JS vérifiés ; aucun débordement.
- [x] Documentation et design mis à jour, Docker sain.

[Rapport hero multi-motifs](../product-design/DTF_HERO_GANG_SHEET_2026-10-25.md).

## Suivi utilisateur — lecture minimale et mentions métier

- [x] Textes centrés sur DTF professionnel, commande selon le besoin et volume mensuel réalisé.
- [x] Hiérarchie simplifiée, titres courts et FAQ raccourcie sur mobile.
- [x] Carrousel de préparation en trois étapes, avec emplacements photo et transition native fluide.
- [x] Commandes clavier/tactiles, mouvement réduit et consultation sans JavaScript vérifiés.
- [x] Hairline et gamut étendu préservés, démonstrations techniques accessibles en détail.
- [x] Infobulles PET 56 cm double face pelable à chaud, encres 8 couleurs, blanc adapté et poudre premium.
- [x] Mention OEKO‑TEX® limitée aux encres selon confirmation de l’utilisateur.
- [x] Largeur utile configurée, calcul des prix et conditions commerciales conservés.
- [x] Douze photos prévues, captures du portail et absence d’images cassées vérifiées.
- [x] 135 tests Python, 13 tests JS et recettes navigateur réussis ; 18 tests ciblés après correction finale.
- [x] Dix vues finales desktop/tablette/mobile examinées ; zéro FAIL Taste, réserves documentées.
- [x] Documentation mise à jour, six services Docker sains.

[Rapport de simplification et hypothèses métier](../product-design/DTF_ESSENTIAL_2026-10-25.md).

## Suivi utilisateur — petites notes inutiles

- [x] Légende technique sélectionnée sous le hero et textes redondants supprimés.
- [x] Photos en attente sans légendes répétées ; vrais médias toujours légendés.
- [x] Simulations, captures et conditions commerciales identifiées sans répétition.
- [x] Infobulles et quatre couches préservées ; espace mobile replié au repos.
- [x] 26 tests Python ciblés et recette navigateur réussis, aucun débordement ni erreur.
- [x] Statiques, service local et documentation actualisés.

## Suivi utilisateur — style Odoo et couleurs conservées

- [x] Référence étudiée à partir du HTML public et d’une capture de l’accueil.
- [x] Hero centré, titres manuscrits locaux et accent corail.
- [x] Introductions aérées, médias à angles doux, commande et FAQ simplifiées.
- [x] Palette comparée avant/après et strictement identique.
- [x] Police Caveat hébergée localement avec sa licence SIL OFL.
- [x] 31 tests Python ciblés réussis ; marque et offre publique inchangées.
- [x] Recette et confirmation visuelle consignées dans le rapport du lot.

[Rapport de composition Odoo](../product-design/DTF_ODOO_STYLE_2026-10-25.md).

## Suivi utilisateur — corrections UI Impeccable

- [x] Galerie : commandes visibles, compteur et accès aux cinq vues.
- [x] Couleur textile active : anneau visible et cibles tactiles de 44 px.
- [x] Analyse : contenu non rogné à 320 px, disposition adaptée aux tablettes.
- [x] Trois groupes d’options nommés avec rôle accessible explicite.
- [x] Tests de galerie ajoutés ; 17 tests JS et recettes navigateur réussis.
- [x] Dix largeurs testées, aucune erreur JS ni violation automatique Axe dans les états examinés.
- [x] Style, couleurs, Hairline et mentions commerciales conservés ; documentation actualisée.

[Rapport et limites des contrôles](../product-design/DTF_IMPECCABLE_FIXES_2026-10-25.md).

- [x] Clôture après reprise : 29 tests Python ciblés et 17 tests JS réussis ; groupes accessibles vérifiés avec et sans grille tarifaire, contrôle navigateur final sans violation automatique ni rôle ARIA indéterminé.

## Tarif et conversion dès le hero — 25 octobre 2026

- [x] Promesse concise : impression 8 couleurs, préparation textile, commande au mètre sans format de planche imposé.
- [x] Tarif public de base relié au catalogue, largeur et exclusions précisées.
- [x] Flèche originale et hiérarchie centrée sur la demande d’accès professionnel.
- [x] Lien direct vers le simulateur ; aucun montant inventé si le catalogue est indisponible.
- [x] 37 tests Python ciblés réussis, dont trois cas de montant / largeur dans le hero.
- [x] Recette navigateur : sept largeurs sans débordement, prix et CTA visibles, quatre couches Hairline, liens réels, mode sans JavaScript et mouvement réduit vérifiés.

[Rapport de la passe](../product-design/DTF_HERO_CONVERSION_2026-10-25.md).

## Benchmark Sherpa — audit du 25 octobre 2026

- [x] Page concurrente parcourue du hero au footer sur desktop et mobile.
- [x] Comparaison avec notre version locale, contrôle des CTA, du simulateur et de la première étape de demande d’accès sans soumission.
- [x] Revue conversion en lecture seule, inspection Taste et réserves documentées.
- [x] Scores, proposition de hero et backlog P1–P3 consignés ; aucun changement applicatif ni publication.
- [x] Passe suivante : rapprocher le résultat, la commande et les tarifs, clarifier la demande d’accès puis adapter les tests et refaire la recette.
- [ ] Avant publication : intégrer les photos de production et confirmer les conditions commerciales manquantes.

[Audit et critères d’acceptation](../product-design/AUDIT_SHERPA_LANDING_2026-10-25.md).

## Hero commercial et conversion professionnelle — 25 octobre 2026

- [x] Promesse commerciale centrée sur le DTF professionnel et le soin des fichiers.
- [x] Figure Hairline, prix et CTA visibles dans le premier écran sur les formats de référence.
- [x] Composition desktop/tablette en grille, lecture mobile adaptée et commandes matière conservées.
- [x] Commande et tarifs remontés avant la technique ; demande d’accès disponible directement après simulation.
- [x] Validation préalable du compte expliquée, prix dynamiques et frais conditionnels conservés.
- [x] 40 tests Python et 17 tests JavaScript réussis ; Ruff et vérification des diffs sans erreur.
- [x] Dix largeurs sans débordement ; clavier, taps mobiles, sans JS et mouvement réduit vérifiés.
- [x] Documentation, design et statiques locaux actualisés ; six services Docker sains.
- [ ] Avant publication : remplacer les emplacements photo et compléter les conditions commerciales manquantes.

[Rédaction finale, captures et limites](../product-design/DTF_PREMIUM_HERO_2026-10-25.md).

## Sections de landing — passe Impeccable, 25 octobre 2026

- [x] Argumentaire commercial B2B repris pour commande, budget, résultats, couleurs, préparation, atelier, FAQ et accès.
- [x] Hero, Hairline, palette, prix et conditions métier conservés.
- [x] Captures de commande mieux intégrées ; demande d’accès répétée remplacée par un lien de budget.
- [x] Paliers en grille adaptée au conteneur, exclusions près du prix et distinction encours/comptant explicite.
- [x] Réservations photo compactes et honnêtes, ordre de lecture couleurs corrigé, FAQ et final recomposés.
- [x] 42 tests Python et 17 tests JS réussis ; Ruff et diffs vérifiés.
- [x] Dix largeurs sans débordement et titres principaux sur deux lignes maximum.
- [x] Clavier, taps mobiles, zoom des captures, galerie, préparation, FAQ, sans JS et mouvement réduit vérifiés.
- [x] Documentation et statiques locaux actualisés ; six services Docker sains.
- [ ] Avant publication : intégrer les photos de production et compléter les conditions commerciales manquantes.

[Compte rendu et recette](../product-design/DTF_PREMIUM_SECTIONS_2026-10-25.md).

## Passe premium, légal et mouvement au scroll, 26 octobre 2026

- [x] Audit landing + critique Impeccable (56/100) et backlog P0–P2 traité.
- [x] Placeholders photo en épreuve d’impression ; aucune image inventée.
- [x] Pages mentions légales, conditions commerciales et confidentialité publiques ; identité via `LEGAL_*`, valeurs manquantes signalées.
- [x] Réassurance d’accès, étapes finales, barre d’accès mobile, curseur adapté aux paliers, jargon défini, métadonnées de partage.
- [x] Mouvement au scroll en CSS (rail 8 encres, épreuves, listes), sans effet en mouvement réduit ni sans support.
- [x] 12 tests ajoutés ; suite UI 153 passés ; suite complète 1594 passés, 2 échecs préexistants hors périmètre.
- [x] Desktop 1920 px et mobile 390 px vérifiés ; DESIGN.md et compte rendu mis à jour.
- [ ] Avant publication : renseigner `LEGAL_*`, rédiger CGV complètes et durées RGPD, trancher l’écart 6 € / 10 € HT de préparation fichier.

[Compte rendu](../product-design/DTF_PREMIUM_PASS_2026-10-26.md).

## Passe taste-skill, 26 octobre 2026

- [x] Inspecteur taste-skill : 3 FAIL → 0 FAIL ; 5 avertissements assumés et documentés.
- [x] Bandeau retiré, onglets de couches colorés, puces de volume dans le hero (masquées sans script).
- [x] 3 réservations au lieu de 12 ; dessins de couches en préparation ; 2 images libres créditées ; capture Studio au final.
- [x] Deux polices, échelle 6 tailles, bande noire « 8 encres », mot-symbole du footer, nettoyage des ombres et filets.
- [x] Barre d’accès mobile à la remontée seulement.
- [x] 6 tests ajoutés, tests obsolètes alignés ; suite complète 1601 passés, 1 échec préexistant hors périmètre.
- [ ] Avant publication : trois photos de résultats et une photo réelle de l’atelier.

[Compte rendu](../product-design/DTF_PREMIUM_PASS_2026-10-26.md#passe-taste-skill--26-octobre-2026).
