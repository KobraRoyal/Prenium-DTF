# Micro-lot 11.3 — Audit frontend P1 (wording, guidance, conversion, shipping staff)

> Ce micro-lot applique les corrections P1 les plus visibles issues de l'audit frontend,
> sans ouvrir de nouveau domaine métier et sans modifier la sécurité backend.

## Objectif
Améliorer la clarté produit et la perception premium sur les surfaces existantes :
- wording portail client/staff plus produit ;
- détail commande client plus explicite ;
- entrée conversion landing/services clarifiée ;
- checkout plus guidé ;
- panneau shipping staff réorganisé.

## Périmètre livré
- [x] libellés portail harmonisés (`Accueil client`, `Accueil staff`, `Fichiers`, `Contrôle fichiers`, `Expédition`, `Facturation`)
- [x] détail commande client enrichi par une promesse de suivi plus explicite
- [x] panneau client inspection clarifié (validés / à surveiller / à corriger)
- [x] panneaux client production / shipping plus pédagogiques
- [x] checkout client plus guidé (parcours, réassurance, CTA mieux nommés)
- [x] landing `/` et page services `/services/` clarifient mieux les entrées prospect vs client existant
- [x] panneau staff shipping recomposé en 3 zones : état actuel, actualisation du suivi, création d'envoi

## Hors périmètre confirmé
- nouveau domaine métier
- nouvelle règle de pricing, production, shipping ou billing
- modification des permissions
- changement de logique métier backend
- refonte structurelle du portail

## Exigences sécurité appliquées
- aucune modification du scope client/staff
- aucune modification des permissions backend
- aucune exposition nouvelle de données sensibles
- routes et services métier existants réutilisés tels quels

## Tests exécutés
- [x] non-régression UI portail sur navigation/login client
- [x] non-régression pages marketing/services
- [x] non-régression parcours checkout jusqu'à la fiche commande

## Validation exécutée
- [x] `python -m pytest tests/ui/test_portal_ui.py tests/ui/test_shop_checkout_ui.py -q`

## Checklist de clôture
- [x] code implémenté
- [x] tests ajustés
- [x] permissions vérifiées (inchangées)
- [x] logique métier inchangée
- [x] documentation micro-lot ajoutée
