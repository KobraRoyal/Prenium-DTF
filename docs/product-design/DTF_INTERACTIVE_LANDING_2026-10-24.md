# DTF by IDS Supply — landing interactive

## Périmètre et direction

Accueil `/`, reconstruit depuis `main` `04a264b` sur `codex/dtf-premium-landing`.
La stack locale a été redémarrée, sans supprimer les volumes. Aucun déploiement distant.

Mode : **Persuade**. Le visiteur professionnel doit comprendre les matières et la
préparation qui font un bon transfert, puis entrer dans le parcours professionnel.
La direction reprend les tokens ivoire/corail, Space Grotesk et DM Sans auto-hébergées.
L’illustration couleur porte l’expression ; les surfaces et la typographie restent sobres.

Douze sections : promesse, anatomie, gamut, analyse, détails, textile, alpha, galerie,
commande, prix, expertise, conversion. Les partials `shop/partials/dtf/` isolent cette
surface. Le portail, le studio et la page services conservent leur présentation.
Les anciennes ancres utilisées par la navigation de la page services sont conservées.

## Recherche et limites de vérification

Recherches effectuées le 24 octobre 2026 :

- [IDS Supply](https://ids.supply/) : présentation de l’activité textile accessible
  dans l’index public ; téléchargement direct limité par le serveur. Pas de photographie
  authentifiée de production DTF récupérée depuis cette source.
- [DTF IDS Supply](https://dtf.ids.supply/) : GET redirige vers la connexion du portail.
  Couleurs et polices concordent avec le projet local. Aucune grille publique lisible.
- [Hairline, documentation et exemples](https://github.com/lucasmarkes/hairline) :
  exemple `exploded`, règles de sélection sur géométrie stable, ressorts continus,
  transitions discrètes et boucle partagée suspendue hors champ.
- [Epson, étapes DTFilm](https://epson.com/dtg-dtf-printers-for-makers) : film, encre
  couleur puis blanc, poudrage, polymérisation et transfert. Sert à vérifier l’ordre
  des matières, sans attribuer cette imprimante à IDS Supply.
- [CADlink, réglage du blanc et du choke](https://help.cadlink.com/website/digital_factory/en/production/menus/queue_menu_output.htm) :
  retrait du blanc et gestion des niveaux de blanc.
- [CADlink, gestion des transparences](https://marketing.cadlink.com/marketing/Brochures/DF11dtf_Letter_EN_Web.pdf) :
  description indexée des trames et du blanc dépendant de la transparence ; téléchargement
  direct du PDF indisponible au moment de la recherche.
- [SuperGamut, système à gamut étendu](https://supergamut.com/product/the-hydra/) :
  existence d’une configuration CMJN + orange, vert, rouge, bleu, et blanc distinct.
  Aucun pourcentage d’extension du gamut repris sur la landing.

Les caractéristiques de l’offre IDS (8 encres couleur, PET double face pelable à chaud,
consommables premium) proviennent du brief commercial fourni. Le modèle machine,
les références de consommables et des mesures réelles n’ont pas été vérifiés sur un
catalogue IDS public. À confirmer avant publication commerciale externe.

Aucun témoignage, photographie de production, résultat de lavage ou comparaison
colorimétrique chiffrée inventés. Les six emplacements de la galerie sont explicitement
marqués « Photo IDS Supply à venir ». L’aperçu modal et sa navigation sont fonctionnels.

## Illustrations et Hairline

Les skills `hairline-create` et `hairline-adopt` ont été installés avec la commande
`npx skills add lucasmarkes/hairline --agent codex --global --yes`.
`hairline-create` est utilisé pour une figure originale, pas pour embarquer `exploded`.

- Noyau inchangé : `static_src/vendor/hairline/kernel.js`, licence MIT adjacente.
  SHA indiqué dans l’en-tête du noyau : `346b48bdef2cdfafd5343eba01494255cf75f9c078e6fcd1aafc62bab62980a1`.
- Figure : `static_src/js/dtf-transfer.js`, moins de 200 lignes, contrat `hairline()`.
  Le pointeur sélectionne une matière sur des bandes stables ; les voisins s’écartent.
  Les entrées continues suivent un ressort et les changements de sélection un tween.
- Tour autonome de validation : haut du film → couche couleur → adhésif → repos.
  Il n’est pas lancé en boucle sur la landing.
- La figure autonome respecte les règles monochromes du skill. L’adaptateur et le
  CSS ajoutent les gradients matière et l’interpolation demandés par le brief utilisateur.
  L’animation ne modifie pas les couleurs de l’artwork original.
- `img/dtf/expression.svg` : illustration géométrique originale, courbes concentriques
  multicolores. Ce fichier est un graphisme de démonstration, pas une photo.
- `img/dtf/fabric-weave.svg` : texture textile schématique originale, explicitement
  utilisée dans des simulations. Aucun grain photographique généré.

Ordre avant pose, du film vers le textile : PET → couleur → blanc → adhésif.
Après pose, du textile vers l’extérieur : adhésif → blanc → couleur ; le PET est retiré.
Blanc et adhésif suivent le motif plutôt qu’une nappe pleine sur tout le film.
Épaisseurs exagérées à des fins pédagogiques.

## Préparation : limites des simulations

Aucun fichier utilisateur n’est téléversé ou analysé depuis la landing. Les hotspots
présentent des exemples. Les interventions restent décidées et contrôlées par l’atelier.

- Détails : comparaison clavier/tactile du trait original et d’un ajustement local.
  Aucun épaississement automatique de tous les éléments n’est promis.
- Contours A : dépassement du blanc exagéré pour montrer le liseré.
- Contours B : retrait intérieur de la géométrie blanche ; dessin couleur conservé.
- Contours C : éventuelle compensation des pixels de bord à la teinte du support,
  distincte du retrait du blanc. Une mauvaise couleur peut produire un contour ou
  faire disparaître des détails. La loupe agrandit réellement la même géométrie SVG.
- Sélecteur : noir, blanc, marine, gris, rouge, vert et teinte personnalisée ; la couleur
  affecte le textile et la compensation. Le bouton blanc révèle la sous-couche.
- Alpha : trois états représentatifs, sans algorithme universel ni garantie de reproduction
  parfaite de chaque pixel semi-transparent.

## Prix et parcours : source de vérité

Suite à la précision utilisateur, les montants ne sont **pas** codés depuis la grille
indicative du brief. `PublicDtfOfferService` lit exclusivement :

1. le service DTF par défaut, résolu par `OrderPricingService` avec la même priorité
   catalogue que la facturation ;
2. la laize de `DTF_LAIZE_CM` ;
3. les `DefaultCustomerVolumeDiscountTier` actifs ;
4. les dimensions globales du studio, sans créer de singleton sur GET.

Aucun tarif personnalisé, profil de facturation client, identifiant ou volume individuel
n’est chargé. Le petit paramètre `bootstrap=False` empêche de créer le catalogue depuis
l’accueil ; tous les appels de facturation existants gardent leur comportement.
Le prix indisponible ou une devise non EUR produisent un état de contact explicite.

La conversion est `tarif/m² × laize en mètres`. Dans la base locale inspectée :
25 €/m² × 0,55 m = 13,75 € HT/m, paliers 5/10/25 m et remises 10/20/25 %.
Ce sont des données de recette locales, pas une promesse de grille en production.
Les changements en base sont repris à la prochaine réponse de la page.

Le calcul navigateur utilise centimes et points de base, puis arrondit le total, et non
le prix unitaire arrondi multiplié par le volume. Il reste une estimation, hors préparation
et transport. La remise en encours est mensuelle ; au comptant elle n’est pas rétroactive.
L’économie présentée suppose le volume entier au même palier, ce qui est expliqué.

Mention demandée : « Un coût de traitement de 6 € HT pourra être appliqué si le ou les
fichiers fournis ne sont pas conformes. » Cette mention commerciale ne modifie pas le
forfait préparation existant ni le moteur de facturation. Aucun frais n’est débité ici.

CTA anonymes : `prospects:step1`. CTA authentifiés : `portal:login`, qui répartit
l’utilisateur vers son portail selon son rôle. Le premier accès est expliqué à proximité
des CTA ; aucun faux lien d’import direct ni identifiant client n’est embarqué.
Le parcours Gang Sheet est requis pour le compte comptant. La composition est libre
à l’intérieur de dimensions bornées, affichées depuis les réglages du studio.

La politique existante `MARKETING_HOME_REDIRECT_TO_LOGIN` est conservée : `/` est public
en local, mais reste redirigé vers la connexion en production par défaut. Une publication
future doit décider explicitement d’exposer la landing avec ce réglage désactivé.

## Recette

- Tests serveur : `tests/core/test_public_dtf_offer.py`, identité de la source par défaut,
  paliers actifs, conversion, modification en base, GET sans bootstrap, absence de fuite
  de données client, devise non EUR.
- Régressions : `tests/ui/`, catalogue et remises de commandes.
- Tests JS : `node --test tests/frontend/dtf-pricing.test.mjs`, seuils, montants, arrondis,
  grille DB différente du brief, absence de paliers et entrées invalides.
- QA navigateur : bureau et mobile, onglets/clavier, comparaison, textile, alpha, galerie,
  prix, liens locaux, 375/390/768/1024/1440 px et mouvement réduit.
- Artefacts locaux ignorés par Git : `output/playwright/`, captures, planche Hairline,
  page Hairline autonome et script de recette.
- Relecture indépendante `ids_security_reviewer` : aucun finding exploitable sur les prix
  publics, la sérialisation, l’isolation et l’absence d’écriture sur GET.
- Détecteur Impeccable : une alerte `width` concerne `stroke-width` SVG, sans animation
  de largeur de mise en page ; les chemins `{% static %}` ne sont pas résolus par l’outil.

Le comportement sans JavaScript conserve les textes, les liens, le dessin statique,
le prix de base et la grille lisible. Un message signale que le simulateur exige JavaScript.
Les animations respectent `prefers-reduced-motion` ; la boucle Hairline dort au repos
et hors champ. Le test Lighthouse mobile local final mesure 99 en performance, 100 en accessibilité
automatisée et 100 en SEO, avec LCP 2,0 s, TBT 0 ms et CLS 0. Le premier lancement
a échoué sur une trace navigateur `NO_NAVSTART` ; seule la mesure finale valide est
retenue. Aucun 60 FPS constant ni résultat équivalent en production n’est garanti.

### Résultat final de recette

139 tests pytest et 4 tests JS passent. Aucun échec ni erreur console pendant le parcours
Playwright complet. Aucun débordement à 375/390/768/1024/1440 px. Les vrais événements
tactiles ont été testés dans un contexte Chromium mobile. Les captures finales sont
`dtf-desktop-hero.png`, `dtf-desktop-full.png`, `dtf-mobile-hero.png`,
`dtf-mobile-full.png` et les détails techniques dans `output/playwright/`.
Le rapport Lighthouse final est `output/playwright/dtf-lighthouse-final.json`.

La comparaison ne repose pas sur une photographie avant/après ; elle compare deux
constructions vectorielles représentatives. La loupe du textile clone la géométrie
courante dans le SVG pour conserver exactement les traitements et styles du détail.
Le zoom multicolore fonctionne par bouton, au clavier et au toucher.

## Passe Impeccable demandée — identité et conversion B2B

Cette révision remplace la marque marketing séparée `dtf.` par le composant partagé
`components/brand/logo.html` : **Prenium DTF By IDS.Supply**. La casse « By IDS.Supply »
est conservée par le socle CSS commun. Landing et footer réutilisent le même include
que les headers services, auth, prospect et portail ; Studio hérite du header portail.
Aucune route de rôle ni permission n’est changée.

Tous les CTA de demande d’accès anonymes de la landing portent « Demander votre accès »,
y compris ceux des options fichier et Gang Sheet. Les services et la connexion reprennent
ce libellé ; le service exclusivement B2B est annoncé. Le libellé connecté reste contextuel.

Le hero et la figure originale représentent maintenant le film **en bas**, puis le motif
floral à huit pétales, une sous-couche blanche à silhouette identique et la poudre au-dessus.
Le blanc et la couleur utilisent exactement le même contour, sans enveloppe convexe qui
effacerait les creux entre pétales. La poudre comprend 466 grains fixes, déterministes,
à l’intérieur du motif. `flower-white.svg` et `flower-powder.svg` sont des SVG originaux,
pas des photographies de production.

Le survol teste les silhouettes réelles dans leur pose de référence, pas leur pose animée.
Chaque matière affiche une infobulle distincte et synchronise le panneau. L’infobulle
reste survolable, se ferme avec Échap et décrit le contrôle actif au clavier. Sur mobile,
elle apparaît dans le flux après le dessin pour préserver les cibles tactiles. Le moteur
Hairline et son noyau restent inchangés ; aucune boucle de particules permanente n’est ajoutée.

Validation de cette passe : 194 tests pytest réussis, incluant 4 tests d’intégration de
l’identité sur les pages publiques et les contrats du portail, plus 4 tests JavaScript.
Recette Playwright sans erreur sur les 4 pages publiques, les 4 survols matière, la
navigation clavier, l’association ARIA, la fermeture Échap et le mouvement réduit.
Zéro débordement à 375, 390, 768, 1024 et 1440 px. Les captures préfixées
`dtf-polish-` sont conservées dans `output/playwright/`.

Mesure Lighthouse mobile de la passe Impeccable : performance **99**, accessibilité
automatisée **100**, SEO **100** ; LCP 2,0 s, TBT 0 ms, CLS 0. Rapport local :
`output/playwright/dtf-polish-lighthouse.json`.
