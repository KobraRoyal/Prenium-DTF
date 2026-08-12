# Sprint 35 — Durcissement frontend Impeccable

Date : 2026-08-12
Statut : **terminé**

## Objectif

Exécuter le backlog de l’audit frontend général sans redesign de l’identité
« atelier brutaliste » : accessibilité du Studio, lisibilité, cache déterministe,
assets par surface et parcours orientés vers la prochaine action utile.

## Livrables

- [x] Raccourcis du Studio limités au canvas, sans interception des boutons,
  liens, champs, contenus éditables ou dialogues.
- [x] Canvas exposé comme région et onglets mobiles conformes au modèle ARIA,
  avec focus itinérant et navigation clavier.
- [x] Date picker complété avec grille ARIA, focus restauré et navigation par
  jour, semaine et mois.
- [x] Plancher typographique de 12 px pour les métadonnées et 14 px pour les
  actions du Studio ; microtextes critiques du portail normalisés.
- [x] Mouvement réduit sélectif : déplacements décoratifs désactivés sans
  supprimer les retours de couleur, de focus et de validation.
- [x] Accents latéraux épais remplacés par des accents horizontaux ou des fonds
  d’état cohérents.
- [x] `ManifestStaticFilesStorage` activé en production et versions manuelles
  retirées des points d’entrée statiques des templates.
- [x] CSS découpé en `app.css`, `marketing.css`, `portal.css` et `studio.css`.
- [x] Studio recentré sur Importer → Composer → Contrôler → Valider, avec outils
  avancés révélés à la demande.
- [x] Dashboards client et Atelier centrés sur un prochain geste réel, sans KPI
  de retard inventé faute de règle SLA.
- [x] Landing mobile raccourcie par les espacements, CTA « Accès pro » explicite
  et FAQ repliée par défaut.
- [x] Tests de structure, accessibilité, responsive, bundles et fingerprint
  ajoutés.
- [x] Matrice navigateur 320 / 375 / 768 / 1440 px sans débordement global ni
  erreur console.
- [x] Audit Impeccable final : aucun défaut réel ; l’image d’aperçu sans `src`
  initial reste un faux positif car elle est cachée puis alimentée par JS.
- [x] Import Gang Sheet durci : limite de 20 Mo annoncée et contrôlée avant
  aperçu, lots limités à 60 Mo, rejet serveur atomique et marge proxy bornée
  pour éviter les pages Nginx `413` opaques ; rafales bornées par utilisateur
  et client via le cache partagé.

## Mesures assets

| Surface | Charge gzip après | Écart face au bundle monolithique (~67,7 Ko) |
| --- | ---: | ---: |
| Marketing (`app + marketing`) | ~25,8 Ko | −61,8 % |
| Portail / prospect (`app + portal`) | ~55,4 Ko | −18,1 % |
| Studio (`app + portal + studio`) | ~61,4 Ko | −9,3 % |

Le manifest Django produit des noms fingerprintés en production. Les suffixes
des imports de modules enfants JavaScript sont conservés temporairement : le
stockage manifest stable de Django ne réécrit pas ces imports ES modules.

## Hypothèses et limites

- Le KPI « retard » reste hors périmètre tant qu’une échéance et une règle SLA
  (pause client, fuseau, priorité) ne sont pas définies par le métier.
- Le bundle portail reste volontairement mutualisé entre portail, tunnel
  prospect et bibliothèque Gang Sheet ; il pourra être subdivisé si son poids
  recommence à croître.
- Une validation sur lecteur d’écran et appareil physique complète utilement la
  couverture automatisée clavier et navigateur.

## Checklist de validation

- [x] Build Tailwind des quatre bundles.
- [x] Tests ciblés UI, architecture, production et statiques.
- [x] `manage.py check` et compilation Python / JavaScript.
- [x] `collectstatic` avec stockage manifest en configuration production.
- [x] Navigation clavier du Studio et du date picker.
- [x] Aucun overflow global sur les breakpoints représentatifs.
- [x] Console navigateur propre.
- [x] Détecteur Impeccable exécuté après les corrections.
- [x] Graphe d’architecture rafraîchi.
