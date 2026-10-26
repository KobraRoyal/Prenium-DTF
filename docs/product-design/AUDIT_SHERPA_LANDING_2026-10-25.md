# Benchmark Sherpa et optimisation de la landing Prenium DTF

Date : 25 octobre 2026. Périmètre : audit marketing, conversion et UI/UX ; aucune modification applicative ni publication.

## Conclusion

Notre priorité est de **montrer le résultat, rapprocher la décision et expliquer l’accès professionnel**. Le prix public et le simulateur sont déjà de bons points d’entrée. La crédibilité visuelle reste à construire avec nos propres réalisations.

Sherpa présente une offre et des ressources riches, avec des visuels du produit et des signaux de confiance. Sa page donne aussi beaucoup de place à la pédagogie et laisse l’achat en retrait. Une reprise de sa structure entière allongerait notre parcours.

## Cadrage, méthode et limites

- Audience présumée : ateliers, marques, imprimeurs et professionnels du textile ; service B2B avec validation du compte, conformément à l’existant.
- Action principale : déposer une demande d’accès professionnel qualifiée. Action secondaire : estimer son budget. Commander devient possible après validation ; cette règle reste structurante.
- Concurrent : [collection Transfert DTF de Sherpa](https://www.sherpa-transfert.com/collections/transfert-dtf), consultée dans un navigateur et par extraction du contenu public.
- Notre référence : version locale sur `http://127.0.0.1:8080/`, avec les changements de travail existants. Ce constat ne décrit pas une version publique déployée.
- Revue du hero au footer à 1440 px et 390 px pour les deux pages. Contrôles additionnels de notre page à 375 et 768 px, lecture des templates et revue conversion déléguée en lecture seule.
- Aucun graphe existant à la racine ; aucune indexation lancée.
- Scores éditoriaux d’expert, fondés sur le rendu et le parcours observés. Aucun accès aux ventes, taux de conversion, classements SEO ou données publicitaires de Sherpa. Aucun gain de conversion chiffré prédit.
- Les labels et engagements Sherpa sont des éléments affichés par le concurrent : leur portée documentaire n’a pas été auditée. La provenance de son visuel de hero n’est pas établie ; il ne constitue pas une preuve indépendante de fabrication.
- Les emplacements photo de notre version locale sont des réservations documentées. Leur classement P1 ci-dessous concerne la préparation de la publication.

Skills : `skill-landing-audit-pixel-perfect`, `design-taste-frontend`, `graphify` pour le contrôle de présence du graphe. Navigation et contrôles en navigateur avec Playwright. Profil spécialisé `landing-conversion-agent` appliqué par un agent UI, sans écriture.

## Scores pondérés

Chaque cellule exprime les points attribués sur le poids de l’axe. La somme donne le score sur 100.

| Axe | Poids | Sherpa | Prenium DTF actuel |
| --- | ---: | ---: | ---: |
| Clarté immédiate | 20 | 17 | 17 |
| Structure et flux | 15 | 9 | 10 |
| Crédibilité | 20 | 17 | 10 |
| Différenciation | 15 | 11 | 12 |
| Conversion et CTA | 20 | 10 | 16 |
| Cohérence visuelle et mobile | 10 | 6 | 7 |
| **Total** | **100** | **70** | **72** |

La comparaison porte sur une page de collection large et un accueil B2B centré sur l’accès : elle sert à identifier des leviers, pas à classer les entreprises.

**Verdict : notre landing n’atteint pas encore le niveau premium selon la grille du skill.** Le score reste inférieur à 75 et la preuve photographique est un P1 avant publication. Le socle visuel et commercial permet une amélioration ciblée.

## Ce que Sherpa fait bien

1. **Produit visible sur desktop.** Un grand visuel de transfert sur film rend l’offre tangible à côté du titre. Les exemples de textiles et les applications donnent ensuite une idée de l’usage final.
2. **Confiance identifiable.** Implantation locale, certifications affichées avec liens, téléphone et module d’avis donnent plusieurs moyens d’évaluer le fournisseur.
3. **Choix relié à un besoin.** Logo, planche, mètre et forfait expliquent des façons différentes de produire. Nous pouvons rendre nos deux modes aussi compréhensibles, en conservant leurs conditions d’accès.
4. **Réponse aux objections techniques.** Fichiers, matières, pose, entretien et ressources répondent aux questions avant achat. C’est une matière utile pour des guides reliés à une landing plus courte.

Ces observations viennent de la [page concurrente consultée](https://www.sherpa-transfert.com/collections/transfert-dtf).

## Limites de la page concurrente

- Le bouton principal du hero ouvre une page explicative sur le DTF. Il ne conduit pas directement vers la sélection d’un produit ou une commande.
- Aucun prix de transfert comparable au mètre n’a été relevé dans le contenu de cette collection. Le seuil de livraison offerte affiché n’est pas un tarif produit. Aucun argument « moins cher que Sherpa » n’est établi.
- La navigation du catalogue, les répétitions et les nombreux blocs rendent le parcours long : environ 10 000 px sur desktop et 21 000 px sur mobile dans les conditions examinées.
- À 390 px, le visuel du hero passe après le texte et les labels. Le document mesure 441 px de large, avec un débordement horizontal reproduit après rechargement et un haut de page partiellement rogné.
- Les 8 couleurs sont également proposées par Sherpa. Ce seul argument ne constitue donc pas une exclusivité pour Prenium DTF.

## Nos points forts à conserver

1. **Prix lisible dès le hero** : 13,75 € HT/m dans la configuration locale observée, largeur de référence 55 cm et exclusions visibles. C’est un tarif de base dynamique, pas un montant à coder en dur ni un « dès » représentant le prix minimum.
2. **Action principale disponible sur mobile** : le CTA mesure 52 px de haut et reste dans le premier écran aux largeurs testées ; aucun débordement global relevé à 375, 390, 768 et 1440 px.
3. **Offre concrète** : commande au mètre, huit encres et préparation selon le textile constituent une proposition à articuler ensemble, sans prétendre qu’elle serait exclusive.
4. **Simulateur et preuve du portail** : prix, remises et exclusions sont consultables ; les deux captures de commande sont identifiées comme démonstration.

## Freins vérifiés sur notre landing

### P1 — Preuves de production à fournir avant publication

Douze emplacements « Photo à venir » occupent la galerie, la couleur, la préparation, l’atelier et l’envoi. La galerie, située immédiatement après le hero, invite à découvrir un résultat qu’elle ne montre pas encore.

Sources : `backend/templates/shop/partials/dtf/photo.html`, `gallery.html`, `gamut.html`, `analysis.html`, `expertise.html`, `ordering.html`.

Livraison photo minimale recommandée : une pièce finie, une macro des contours, un transfert sur film, un cliché de l’impression en atelier et une pose à la presse. Chaque image doit montrer une réalisation de l’entreprise, avec l’autorisation nécessaire si elle contient un motif client. Les dessins Hairline conservent leur fonction pédagogique.

### P2 — Résultat trop bas et décision trop tardive

Le hero conserve une grande distance entre le groupe prix/CTA et la planche illustrative. Sur mobile, cette dernière n’apparaît que très partiellement dans le premier écran. Sur desktop, une large plage vide sépare l’offre du visuel.

L’ordre actuel est hero → galerie → gamut → préparation → atelier → commande → prix → FAQ → accès. Sur mobile à 390 px, « Commander » commence autour de 5 000 px et le simulateur autour de 6 350 px. Les coordonnées varient avec les dimensions du viewport et les états ouverts ; le lien de hero permet déjà de sauter au tarif.

Sources : `backend/templates/shop/home.html`, `hero.html`, `backend/static_src/css/components/dtf-taste.css`.

### P2 — Effort de demande d’accès peu expliqué au premier écran

Le bouton fonctionne et mène à `/demande-acces/etape-1/`. Cette première étape comporte onze informations obligatoires : prénom, nom, e-mail, téléphone, société, SIREN, activité, adresse, code postal, ville et pays. Aucun formulaire n’a été envoyé pendant l’audit.

La landing doit expliquer l’étape à venir et la validation du compte à proximité du bouton. Modifier ou supprimer des champs relève d’un lot distinct, à évaluer avec le besoin de qualification B2B.

Le composant `cta.html` impose actuellement « Demander votre accès » aux visiteurs anonymes, même lorsqu’un appelant fournit un autre libellé. Ce comportement conserve une destination cohérente avec le statut du visiteur : ce n’est pas un blocage fonctionnel. Une harmonisation éditoriale peut rendre le but plus personnel et précis.

### P2 — Sortie indirecte du simulateur

Le lien « Préparer ma prochaine commande » remonte vers `#commander`, puis un prospect doit utiliser un autre CTA pour demander son accès. Recommandation : conserver un lien pédagogique vers les modes de commande et rendre la demande d’accès directement disponible au résultat de simulation.

Source : `backend/templates/shop/partials/dtf/pricing.html`. Ne pas promettre une commande immédiate à un compte non validé.

## Proposition de premier écran

Texte proposé, à intégrer dans une prochaine passe :

> **Votre DTF au mètre.**
>
> Des transferts DTF 8 couleurs, imprimés en Bretagne et préparés pour votre textile.
>
> **[Tarif de base dynamique] € HT/m** — largeur utile [configuration] cm. Dégressif selon votre volume mensuel. Hors transport et préparation.
>
> **Demander mon accès professionnel**
>
> Réservé aux professionnels. Présentez votre entreprise, puis commandez après validation de votre compte.
>
> Lien secondaire : **Simuler mon tarif**.

Conserver le corail, les fonds et la personnalité de marque. Rapprocher le visuel du texte : sur desktop, composer offre et transfert dans une grille commune ; sur mobile, compacter l’espace avant le visuel sans repousser le bouton hors du premier écran. Une photo réelle pourra compléter le schéma lorsque les médias seront disponibles.

La mention OEKO‑TEX® actuelle porte sur les encres couleur et blanche. Conserver ce périmètre ; les badges du concurrent ne justifient pas d’étendre notre affirmation à l’ensemble du transfert.

## Parcours recommandé

1. **Hero** : offre, prix de base, demande d’accès et aperçu du transfert.
2. **Résultat** : deux ou trois réalisations réellement disponibles, avec une macro pertinente.
3. **Commande** : les modes « Par fichier » et « Gang Sheet », chacun avec une phrase d’usage et ses conditions. Les captures existantes servent de preuve produit.
4. **Prix** : simulateur, grille, conditions et demande d’accès accessible directement.
5. **Préparation et atelier** : contrôle du fichier, blanc, adhésif, fabrication près de Rennes ; approfondissements techniques repliables. Regrouper ici le gamut étendu.
6. **FAQ et accès** : fichiers, dimensions utiles, facturation, livraison et conditions de pose, puis rappel de l’action principale.

Les informations de délais, minimum de commande, échantillons et essais matière doivent provenir de conditions commerciales ou techniques validées avant d’être ajoutées. Les paramètres de pose Sherpa ne sont pas transposables à notre production par simple reprise.

## Backlog et critères d’acceptation

| Priorité | Action | Critère de validation |
| --- | --- | --- |
| P1 avant publication | Remplacer les réservations photo prioritaires par nos médias | Les sections présentées comme preuves montrent une pièce, un détail et une étape réels ; aucun faux témoignage ni faux résultat photographique. |
| P2 | Compacter le hero et préciser le titre | Offre, prix et action lisibles à 375/390 px ; visuel rapproché ; aucun chevauchement aux quatre largeurs de contrôle. |
| P2 | Rapprocher commande et prix | Ces deux décisions précèdent les démonstrations techniques longues ; ancres et navigation restent fonctionnelles. |
| P2 | Ajouter la microcopy d’accès | Le visiteur comprend qu’il fournit des informations d’entreprise et attend la validation du compte. |
| P2 | Proposer un CTA depuis le résultat du simulateur | Le prospect accède à la demande sans devoir remonter par une autre section ; parcours authentifié conservé. |
| P2 | Compléter les réponses commerciales | Délais et éventuel minimum annoncés seulement après confirmation opérationnelle. |
| P3 | Rationaliser les tailles de texte et les polices | Réduire les variantes sans effacer la direction de marque existante. |
| P3 | Développer les guides utiles à l’acquisition | Pages originales sur préparation et pose, fondées sur nos spécifications, reliées à la demande d’accès. Aucun bénéfice SEO garanti. |

Fichiers candidats pour une future implémentation : `backend/templates/shop/home.html`, `backend/templates/shop/partials/dtf/{hero,gallery,ordering,pricing,cta,faq}.html`, `backend/static_src/css/components/dtf-taste.css`, tests UI de contenu et d’ordre des sections. Le présent lot ne les modifie pas.

## Validation réalisée

- [x] Revue concurrente desktop et mobile, du hero au footer, avec captures complémentaires de la FAQ et du pied de page mobile.
- [x] Revue de notre page desktop et mobile ; contrôle à 375, 390, 768 et 1440 px, aucun débordement global.
- [x] Ancres internes existantes vérifiées : aucune cible absente.
- [x] Lien du hero vers le simulateur, menu mobile et ouverture de FAQ exercés en navigateur.
- [x] Simulation au palier 10 m : 20 % de remise, 11,00 € HT/m et 110,00 € HT dans la grille locale observée.
- [x] Destination de demande d’accès et champs de première étape contrôlés sans soumission.
- [x] Inspection Taste exécutée aux trois largeurs 1440/768/390 : **2 FAIL et 8 WARN**, conservés comme constats d’audit ; il ne s’agit pas d’une recette de correction réussie.
- [x] Sources des constats éditoriaux relues ; revue conversion indépendante des captures.
- [x] Documentation et suivi du lot mis à jour. Aucun changement métier, de permissions ou de tarif.
- [ ] Prochaine passe : implémenter les choix retenus et mettre à jour les tests concernés.
- [ ] Prochaine passe : recette finale clavier, tactile, réduction des mouvements, prix et parcours par statut utilisateur.
- [ ] Avant publication : fournir les médias et les conditions commerciales manquantes.

Les FAIL Taste concernent les libellés interprétés comme des surtitres et le manque d’images. Le premier comporte des faux positifs de structure : bandeau B2B et description avant le prix ; le second rejoint le manque réel de photos de production. Les WARN de palette et de polices relèvent d’une convention du skill et ne suffisent pas à justifier un changement de marque. Les mesures de vides et de bords sur les carrousels doivent être interprétées avec les captures, car elles incluent les éléments hors champ.

### Critique visuelle Taste — ronde d’audit unique

ROUND 1

Seen in one second: le titre manuscrit, puis le bouton corail et le prix ; le produit arrive trop bas.

Idea (one sentence): rendre visibles le transfert imprimé et le coût de production au mètre, avec la préparation comme preuve.

Live thing: simulateur de volume et exploration des couches du transfert.

Layout words by section: hero=centré / galerie=carrousel / couleurs=deux colonnes / préparation=carrousel / atelier=deux colonnes / commande=onglets / tarifs=simulateur / FAQ=accordéons / accès=centré.

Scores: design 6 · usability 7,5 · creativity 7 · content 5 → calcul 6,55 ; score plafonné à **6,0/10** par les FAIL de l’inspection.

Caps applied: preuves photographiques insuffisantes, placeholders de contenu et FAIL ouverts. Cette note de style est distincte du score conversion pondéré de 72/100.

Top three problems (most visible first), each with the screenshot it shows in and the fix:

1. Galerie et ateliers sans réalisations — `prenium-audit-2026-10-25-desktop-contact.jpg` : fournir les photos de production prévues avant publication.
2. Visuel séparé de l’offre par un espace important — `prenium-audit-2026-10-25-desktop-hero.png` et `prenium-audit-2026-10-25-mobile-hero.png` : rapprocher les éléments dans la composition existante.
3. Commande et prix après plusieurs séquences techniques — `prenium-audit-2026-10-25-mobile-contact.jpg` : remonter ces sections et regrouper la technique plus bas.

Pas de nouvelle direction tirée, de média généré, d’animation créée ni de maquette implémentée dans cet audit. Les captures de pages entières peuvent présenter des artefacts de navigation fixe ; les captures de viewport et la lecture des éléments visibles lors du défilement ont été utilisées pour les constats.

## Mesurer la prochaine passe

Mesure principale proposée : demandes d’accès abouties et qualifiées rapportées aux visites pertinentes de la landing. Mesures intermédiaires : clics CTA, démarrages et abandons de formulaire, utilisation du simulateur. Segmenter au moins mobile et desktop ; conserver une définition et une période comparables avant/après. Une hausse des clics seule ne prouve pas une hausse de clients.

## Pièces de revue locales

Les captures et le rapport navigateur sont dans `output/playwright/`, ignoré par Git :

- Comparaison des premiers écrans mobiles : `benchmark-sherpa-prenium-mobile-2026-10-25.png`.
- Heroes : `sherpa-audit-2026-10-25-{desktop,mobile}-hero.png` et `prenium-audit-2026-10-25-{desktop,mobile,tablet}-hero.png`.
- Planches de lecture : `{sherpa,prenium}-audit-2026-10-25-{desktop,mobile}-contact.jpg`.
- Compléments mobiles Sherpa : `sherpa-audit-2026-10-25-mobile-{materials,faq,footer}.png`.
- Inspection automatique : `benchmark-sherpa-2026-10-25/report.json` et captures associées.

Cette livraison comprend l’audit et le backlog. Les changements de landing restent proposés, sans déploiement ni modification des travaux utilisateur existants.
