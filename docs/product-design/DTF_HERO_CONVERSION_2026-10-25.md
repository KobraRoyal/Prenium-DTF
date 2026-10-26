# Tarif et conversion dès le hero — 25 octobre 2026

## Intention

La demande est de rendre le prix visible dès le hero, avec une flèche dans l’esprit de l’accueil Odoo. Le fond crème, le corail, les titres Caveat et le transfert Hairline sont conservés. Cette passe est limitée à la décision initiale : comprendre l’offre, connaître le tarif et demander un accès professionnel.

Le texte devient « Des transferts 8 couleurs, préparés pour votre textile. » puis « Au mètre, sans format de planche imposé. ». Les dimensions utiles et limites de la plateforme restent détaillées dans la section commande.

## Offre et parcours

Le prix utilise exclusivement `dtf_offer.price_per_m`, déjà calculé par le service public à partir du catalogue et de la largeur configurée. Il s’agit du **tarif de base**, pas d’un prix minimum après remise. La largeur et l’exclusion du transport et de la préparation accompagnent le prix. La dégressivité est liée au volume mensuel, sans inventer de palier. Si le catalogue manque ou n’est pas en euros, aucun montant ni flèche de prix n’est affiché.

La flèche SVG originale relie visuellement le bouton et le tarif, sans reprendre un actif Odoo. Elle est ignorée par les lecteurs d’écran. Le lien « Simuler mon tarif » mène au simulateur existant. Le CTA conserve la demande d’accès B2B et le parcours de validation existant ; pour une personne connectée, il conserve l’accès à son espace.

Sur grand écran, le prix est à droite du bouton. Sur téléphone, il précède le bouton dans la lecture et dans la composition. Le prix reste visible sans JavaScript ; l’arrivée animée réutilise le système existant, avec respect du mouvement réduit. Aucun nouveau script, dépendance, calcul métier ou accès aux données privées n’est ajouté.

## Hypothèses et limites

- Le catalogue public reste l’autorité pour les prix. La valeur observée pendant cette passe est 13,75 € HT/m sur 55 cm ; elle n’est pas codée en dur dans le hero.
- Les frais conditionnels de traitement de 6 € HT et les modalités de remise restent dans la section tarifs et la FAQ.
- Les photographies de production restent en attente, comme demandé. Aucun avis ni résultat commercial n’est inventé.
- La composition améliore la visibilité de l’offre ; aucune hausse de conversion n’est annoncée sans mesure de fréquentation et de demandes d’accès.
- Référence : le HTML de l’[accueil Odoo](https://www.odoo.com/) a été consulté ; la version française a renvoyé un délai dépassé. La référence place un prix annoté avec une flèche près des actions du hero. Aucun texte ni actif Odoo n’est incorporé.

## Validation

- 37 tests Python ciblés réussis : offre publique, contenu, marque / accès, parcours public et checkout. Les nouveaux cas couvrent 13,75 € sur 55 cm, 16,50 € sur 55 cm et 15,00 € sur 60 cm ; la même valeur apparaît dans le hero et le simulateur. Les cas catalogue absent et devise étrangère restent sans prix dans le hero.
- Ruff et `git diff --check` réussis ; scan Impeccable vide, aucune règle masquée. Lint Taste du hero : zéro FAIL et zéro WARN.
- Chrome : 320, 375, 390, 600, 768, 1024 et 1440 px, zéro débordement. Titres sur une ou deux lignes, prix et CTA dans le premier écran testé, cibles de 44 px minimum. Le débordement de la flèche à 320 px a été corrigé dans la seule passe de réparation.
- Prix identique au simulateur, lien vers les tarifs fonctionnel et destination de demande d’accès en HTTP 200. Les quatre couches et leurs infobulles s’ouvrent et se referment. Prix, CTA et schéma restent consultables sans JavaScript.
- Aucune erreur JS ni violation automatique Axe dans le hero. L’analyse de contraste du titre sur son pseudo-élément reste à appréciation manuelle : texte sur crème 15,57:1, texte secondaire sur crème 4,96:1, texte sur corail 7,57:1. Ces vérifications ciblées ne constituent pas une certification complète d’accessibilité.
- Palette mesurée inchangée et police locale Caveat chargée. L’arrivée du groupe prix / actions réutilise le mouvement existant, sans boucle ajoutée.
- Inspection Taste finale : zéro FAIL, neuf WARN expliqués ci-dessous ; les dix captures finales ont été examinées. La correction mobile ne change ni le reste de la page ni les interactions.

Preuves locales ignorées par Git : `output/playwright/hero-conversion/report.json`, captures avant / après et sans JavaScript ; `.taste-skill/hero-conversion-final/report.json` et planches de lecture. Inspection bornée : une série desktop / tablette / mobile, une correction du placement de flèche, une confirmation.

## Lecture critique

ROUND 2 — confirmation

Seen in one second: le DTF professionnel, puis le prix et l’action corail.

Idea (one sentence): rendre le coût d’entrée du DTF aussi facile à comprendre que sa préparation par couches.

Live thing: transfert Hairline explorable, simulateur tarifaire relié à la grille publique.

Layout words by section: hero=centré avec annotation / résultats=galerie / couleurs=schéma et média / préparation=carrousel / atelier=photos et texte / commande=captures à onglets / tarifs=simulateur / FAQ=liste / accès=appel final.

Scores: design 6,5 · usability 8,5 · creativity 7 · content 5 → overall 7,1/10. Appréciation visuelle subjective de la page entière, pas une mesure de conversion.

Caps applied: photographies réelles indisponibles et réservations photo demandées ; ces limites abaissent les notes d’image et de contenu. La composition reprend volontairement la direction Odoo existante, sans nouveau tirage Taste.

Top three problems (most visible first), each with the screenshot it shows in and the fix:

1. `mobile-page-01.jpg` : les réservations photo ne prouvent pas encore la qualité imprimée. Remplacer les douze cadres par les véritables photos IDS.Supply à leur disponibilité ; aucune image fictive ajoutée.
2. `desktop-fold.jpg` : l’espace au-dessus du transfert compact réserve son ouverture en couches et repousse une partie du film sous le premier écran. Ce comportement Hairline existant est conservé ; prix et accès passent avant l’exploration technique.
3. `after-320.png` initial : la flèche dépassait de 8 px. Son ancrage mobile a été rapproché du bouton ; aucun débordement à la confirmation.

Huit avertissements reprennent ceux de la composition existante : crème explicitement conservé, trois polices en comptant la marque et les repères techniques, échelle incluant contrôles / SVG / prix, absence de film réel, deux carrousels intentionnels, petit texte interne au SVG et deux mesures de composition incluant des diapositives hors champ. Le neuvième, `still-page`, relève 15 éléments mobiles pendant cet échantillon, au lieu de 20 lors du premier passage : le transfert attend l’interaction et les scènes s’arrêtent hors champ. Aucun mouvement supplémentaire n’a été ajouté pour satisfaire cette mesure. Les seules exceptions d’inspection restent `few-pictures` et `eyebrow`, pour les photographies indisponibles et le bandeau demandé. Aucune nouvelle exception ajoutée.
