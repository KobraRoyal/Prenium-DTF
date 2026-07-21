# Micro-lot 11.9 — Landing conversion ultra

> Refonte de la page publique `/` en continuité directe avec le tunnel de demande
> d’accès professionnel. Aucun changement de logique métier ou de permission.

## Objectif

- clarifier la promesse DTF B2B dès le premier écran ;
- concentrer la conversion sur une seule action : ouvrir un accès professionnel ;
- prouver le sérieux du service par le workflow réel, sans témoignage ni chiffre inventé ;
- garantir une expérience cohérente à 375, 768 et 1440 px ;
- supprimer le formulaire public qui dupliquait la première étape du tunnel sécurisé.

## Hypothèses validées

- la conversion principale est `prospects:step1` ;
- l’accès reste réservé aux professionnels et validé humainement ;
- le délai communiqué reste de 1 à 2 jours ouvrés ;
- le SIREN est requis pour la France et le numéro de TVA intracommunautaire pour les sociétés étrangères concernées ;
- le responsable d’organisation pourra inviter ses collaborateurs dans le workflow prévu.

## Audit avant refonte

Score : **61/100 — non premium**.

| Axe | Score | Constat |
| --- | ---: | --- |
| Clarté de la promesse | 15/20 | univers distinctif, mais bénéfice dilué par deux niveaux de slogan |
| Structure et rythme | 8/15 | neuf sections, répétitions et longueur excessive |
| Crédibilité | 11/20 | expertise présente, preuve produit peu visible |
| Différenciation | 11/15 | identité forte et contrôle prépresse pertinent |
| CTA et conversion | 8/20 | formulaire dupliqué, CTA concurrents et CTA secondaire illisible sur mobile |
| Qualité visuelle et mobile | 8/10 | direction forte, mais P1 responsive au-dessus de la ligne de flottaison |

## Architecture livrée

1. promesse et aperçu du suivi B2B ;
2. preuves avant / pendant / après production ;
3. transformation métier et deux offres lisibles ;
4. parcours en quatre étapes avec validation du profil ;
5. preuve produit par une vue de suivi sans données client ;
6. cas d’usage par typologie professionnelle ;
7. objections fréquentes et CTA final unique.

## Audit après refonte

Score : **92/100 — premium**.

| Axe | Score | Résultat |
| --- | ---: | --- |
| Clarté de la promesse | 19/20 | activité, bénéfice et cible visibles dans le premier écran |
| Structure et rythme | 14/15 | sept blocs avec progression conversion-first |
| Crédibilité | 17/20 | preuves fondées sur le workflow et l’isolation des données |
| Différenciation | 14/15 | signature atelier éditoriale cohérente avec le tunnel |
| CTA et conversion | 19/20 | trois rappels cohérents vers une route unique, sans formulaire parallèle |
| Qualité visuelle et mobile | 9/10 | grilles dédiées desktop/mobile, focus visible et mouvement réduit respecté |

## Backlog audit

### P1

- [x] Corriger la superposition du mockup sur le hero mobile.
- [x] Rendre les deux CTA du hero lisibles et tactiles.
- [x] Supprimer le formulaire dupliqué et les CTA finaux concurrents.
- [x] Éliminer tout débordement horizontal à 375 px.

### P2

- [ ] Ajouter des preuves clients vérifiables seulement après accord écrit et validation juridique.
- [ ] Instrumenter les clics CTA et l’abandon par section avec une solution analytics respectueuse du consentement.

### P3

- [ ] Tester deux variantes de promesse principale sur un volume de trafic suffisant.
- [ ] Mesurer les Core Web Vitals sur l’environnement de production.

## Sécurité et performance

- aucune donnée réelle, référence de commande ou identité client dans les mockups ;
- aucune route backend, règle métier ou permission modifiée ;
- aucun formulaire ou traitement sensible ajouté à la page publique ;
- illustration du portail réalisée en HTML/CSS, sans image hero lourde ;
- `content-visibility`, dimensions intrinsèques et `prefers-reduced-motion` conservés ;
- CTA vers l’URL serveur existante `prospects:step1`.

## Validation exécutée

- [x] `npm run build:css`
- [x] `collectstatic` et redémarrage du service web
- [x] 38 tests UI ciblés passés
- [x] rendu vérifié à 375, 768 et 1440 px
- [x] aucun overflow horizontal aux trois largeurs
- [x] menu mobile ouvert / fermé au clavier et au clic
- [x] accordéon FAQ vérifié
- [x] aucun formulaire dans la landing
- [x] aucune erreur console observée

## Hardening Impeccable — 2026-07-21

Le nouvel audit Impeccable est passé de **14/20 à 19/20 — excellent**. Les familles
Space Grotesk et DM Sans sont conservées comme identité existante ; le détecteur
typographique ne remonte plus aucune anomalie actionnable.

- [x] contraste du CTA principal corrigé de `1,1:1` à `17,15:1` ;
- [x] cibles de navigation et d’action portées à au moins `44 px` ;
- [x] échelle des titres resserrée à `6rem` maximum, interlettrage à `-0,035em` maximum ;
- [x] textes mobiles du hero et de la FAQ maintenus à `1rem` ;
- [x] grilles décoratives, kickers répétés et index non signifiants supprimés ;
- [x] logo du header réduit à une cible sémantique unique ;
- [x] version du bundle CSS portée à `20260721b` pour invalider le cache navigateur ;
- [x] contrôles réels dans Docker à `1280`, `375` et `320 px`, sans overflow ;
- [x] menu mobile validé (`aria-expanded`, libellé et cinq liens) ;
- [x] aucune erreur ni alerte console ;
- [x] `479` tests complets et `39` tests UI ciblés passés ;
- [x] lint, format ciblé, check Django, migrations et contrats des six agents validés.

## Définition de terminé

- [x] code implémenté
- [x] tests ajoutés et exécutés
- [x] permissions vérifiées : inchangées
- [x] aucune donnée inter-tenant exposée
- [x] audit/log métier non requis : aucun événement métier nouveau
- [x] documentation et checklist mises à jour
