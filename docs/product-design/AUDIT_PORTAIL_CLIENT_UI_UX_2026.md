# Audit UI/UX — Portail client Prenium DTF

**Date de rédaction :** avril 2026  
**Périmètre :** templates `portal/client/*`, composants associés (navigation, onglets commande, tableaux, checkout B2B), impacts backend listés pour cohérence produit.  
**Objectif cible :** expérience **moderne**, **intuitive**, **pixel-perfect** pour un portail pro B2B.

---

## Mise à jour — 21 juillet 2026

La navigation authentifiée client et Atelier utilise désormais un shell SaaS commun plus sobre. Les entrées principales restent visibles, les fonctions Atelier secondaires sont regroupées sous `Outils`, l’action `Créer une commande` est distinguée des liens de consultation et le compte connecté est identifiable.

Points contrôlés :

- [x] état actif avec `aria-current="page"` ;
- [x] menu client limité aux fonctions réellement éligibles ;
- [x] outils Atelier filtrés par permissions existantes ;
- [x] menu mobile pleine largeur sans débordement du header à 375 px ;
- [x] navigation clavier et fermeture `Escape` ;
- [x] aucun changement de route, de scope client ou de permission serveur.

---

## Mise à jour — 13 juin 2026

| Indicateur | Valeur |
|------------|--------|
| **Score de cohérence UI/UX ciblée** | **100 / 100** |
| **Périmètre validé** | Landing, services, tunnel prospect, login, portail client, checkout, fiches commandes client/staff, panneaux HTMX uploads/billing. |
| **Validation** | `manage.py check`, tests `apps.portal.tests apps.prospects.tests`, audit navigateur desktop/mobile sur landing/prospect/checkout, rendu serveur client/staff des fiches commande. |

Checklist clôturée :

- [x] Breadcrumbs profonds migrés vers `nav.ui-breadcrumb` avec `aria-current`.
- [x] Login aligné sur les surfaces `product-shell`, sans conteneur glass legacy.
- [x] Checkout et panels ciblés sans `shadow-xl`, `backdrop-blur-sm`, `bg-white/5` ni `role="feed"`.
- [x] Stepper checkout clarifié : l’avancement réel n’est plus sur-vendu.
- [x] Onglets commande renforcés : `tablist`, `tab`, `tabpanel`, `aria-selected`, `aria-busy`, lien panel/tab et navigation clavier.
- [x] Menu mobile public doté du même hook fallback JS que le portail.
- [x] Formulaire prospect étape 1 avec labels visibles sur les champs texte/select.

Note : ce score couvre la cohérence UI/UX de la refonte et les écarts listés lors de la revue du 13 juin 2026. Les sujets métier hors UI, sécurité avancée ou intégrations externes restent évalués par leurs checklists dédiées.

---

## 1. Synthèse exécutive

| Indicateur | Valeur |
|------------|--------|
| **Score global indicatif** | **~54 / 100** |
| **Verdict** | Fonctionnel et orienté conversion sur le **checkout B2B**, mais **pas encore** au niveau premium unifié : double langage visuel, onglets trompeurs, microcopy FR à corriger, informations métier (facturation différée, prix) sous-exposées sur liste et fiche commande. |

**Axes notés (indicatif) :**

| Axe | Poids | Note | Commentaire |
|-----|-------|------|-------------|
| Clarté & hiérarchie | 20 % | 58 | Titres OK ; double système UI (legacy vs DaisyUI) ; infos B2B incomplètes au bon endroit. |
| Navigation & orientation | 20 % | 52 | Onglets HTMX sans état actif réel après clic ; chips d’étapes décoratives et redondantes. |
| Cohérence visuelle & design system | 15 % | 48 | Checkout `dui-*` vs fiches `card` / `panel` / `alert--*` ; login `landing_*` vs shell portail. |
| Feedback & confiance | 15 % | 62 | Badges statut ; manque progression et alignement liste ↔ détail sur le prix. |
| Contenu & microcopy FR | 10 % | 45 | Accents et formulations à harmoniser partout. |
| Accessibilité & sémantique | 10 % | 55 | KPI en `<h2>` pour valeurs chiffrées ; onglets sans `tablist` / `aria-selected`. |
| Mobile & densité | 10 % | 58 | `flex-wrap` présent ; tableaux denses sans variante mobile type « cards ». |

---

## 2. Fichiers et zones audités

### Templates portail client

| Fichier | Rôle |
|---------|------|
| `templates/portal/layout.html` | Shell : `portal_header`, `main`, indicateur HTMX |
| `templates/portal/client/dashboard.html` | Dashboard, KPI, dernières commandes |
| `templates/portal/client/orders_list.html` | Liste des commandes |
| `templates/portal/client/order_detail.html` | Résumé + onglets |
| `templates/portal/client/checkout.html` | Tunnel B2B |
| `templates/portal/client/partials/checkout_*.html` | Uploads, résumé |
| `templates/portal/client/panels/*.html` | Uploads, inspection, production, shipping, facture |
| `templates/portal/login.html` | Connexion (hors `portal/layout`) |
| `templates/components/nav/portal_header.html` | Nav client / staff |
| `templates/components/order/order_tabs.html` | Onglets HTMX + chips |
| `templates/components/tables/orders_table.html` | Tableau commandes |
| `templates/components/tables/kpi_grid.html` | Grille KPI |
| `templates/components/ui/empty_state.html` | États vides |
| `templates/components/portal/page_head.html` | Titres de page |

### Code applicatif lié (référence)

- `apps/portal/templatetags/order_tags.py` — `order_htmx_tabs` (état actif des onglets)
- Vues portail : contexte `order`, `customer`, panneaux HTMX

---

## 3. Points forts (à préserver)

1. **Shell portail** : structure claire (header, `main`, indicateur HTMX global).
2. **Checkout B2B** : étapes lisibles, ton aligné facturation différée, usage possible de **DaisyUI** (`dui-*`) pour une direction UI moderne.
3. **Fil d’Ariane** fiche commande (`client_order_detail.html`) : orientation utile.
4. **Onglets HTMX** : chargement partiel sans rechargement complet de page.
5. **Tableau commandes** : colonnes lisibles, lien « Ouvrir », badges de statut.

---

## 4. Problèmes et bugs identifiés

### 4.1 Cohérence visuelle & design system

- **Double langage** : checkout (cartes DaisyUI, steps) vs dashboard / liste / détail / panneaux (`card`, `panel`, `badge`, `alert--*`).
- **Login** : `landing_header` alors que le portail authentifié utilise `portal_header` → rupture de continuité marque / navigation.

### 4.2 Navigation commande (onglets)

- **État actif incorrect** : dans `order_tags.order_htmx_tabs`, `tab["active"] = i == 0` pour chaque rendu. Après clic sur un autre onglet, le **surlignage reste sur le premier** (Uploads) → comportement non intuitif, manque de confiance.
- **Chips « Uploads / Inspection / Production / Shipping / Facture »** : doublon sémantique avec les boutons d’onglets ; non cliquables, non synchronisées avec l’onglet réellement affiché.

### 4.3 Fiche commande (`order_detail.html`)

- Carte résumé limitée à : statut, prix (ou « Après contrôle atelier »), date.
- **Manque** pour le B2B : mode facturation (`billing_mode`), statut tarifaire (`pricing_status`), signal **encours** (`credit_hold_status`) si pertinent.

### 4.4 Liste commandes (`orders_table.html`)

- Colonne « Total » : affichage **0,00 EUR** pour commandes **draft** ou **non tarifées** → ambiguïté (montant définitif vs en attente).
- Pas de distinction visuelle explicite selon `pricing_status` / `billing_mode`.

### 4.5 Panneau uploads (fiche) vs checkout

- Checkout : quantité, couleur, tableau enrichi.
- Panneau `panels/uploads.html` : pas de colonnes **quantité**, **couleur**, **métrage / prix** après calcul → **décalage** parcours dépôt ↔ suivi.

### 4.6 Microcopy & orthographe (FR)

Exemples relevés dans les templates :

- « Dernieres commandes » → **Dernières**
- « Creee le » → **Créée le**
- « Demarrer » → **Démarrer**
- « des leur creation » → **dès leur création**
- « Detail commande » (titre) → **Détail commande**
- Panneaux : « Synthese », « realises », « apres », « controle », « recus », etc.

→ Impact direct sur la perception **premium / soignée**.

### 4.7 Accessibilité & sémantique

- **KPI** (`kpi_grid.html`) : valeur métier (ex. `0`) dans un **`<h2>`** alors que le titre principal de page est le `<h1>` du `page_head` → hiérarchie de titres fragile pour lecteurs d’écran.
- Onglets : boutons sans rôle **`tablist` / `tab` / `aria-selected`** explicite.

### 4.8 Mobile

- Tableaux larges sans variante **cartes empilées** → risque de scroll horizontal peu confortable sur mobile pro.

### 4.9 Panneau facture

- Mélange de classes legacy (`alert`, `empty-state`) et logique B2B récente : densité et ton à harmoniser avec le checkout.

---

## 5. Impacts backend (leviers)

| Sujet | Détail |
|--------|--------|
| **Onglet actif** | Aujourd’hui aucune logique ne passe un `active_tab` selon l’URL ou le panneau chargé. Correction UI = **paramètre** ou **événement HTMX** (`afterSwap`) pour mettre à jour la classe `is-active`. |
| **Contexte fiche** | Les champs B2B existent sur `Order` ; les vues peuvent enrichir le contexte pour affichage sans changer la logique métier. |
| **Liste commandes** | Affichage conditionnel du montant : templatetag ou filtre template `order_money_display` selon `pricing_status` / `billing_mode`. |
| **Panneau uploads** | Exposer dans le contexte / queryset les champs `OrderUpload` (quantité, couleur, métrage, ligne) déjà présents côté modèle. |

---

## 6. Backlog priorisé

### P1 — Bloquant perception « pro » ou compréhension

| ID | Action |
|----|--------|
| P1-1 | Corriger **toutes** les chaînes FR visibles (accents, formulations) dans les templates client et les `<title>`. |
| P1-2 | **Onglets HTMX** : synchroniser l’état actif (clic / chargement) — `aria-selected`, classe `is-active` sur le bon onglet, ou réponse partielle dédiée. |
| P1-3 | **Liste commandes** : ne pas présenter « 0,00 EUR » comme total définitif si prix non figé (`pricing_status`, `billing_mode`). |
| P1-4 | **Carte résumé** fiche commande : afficher **statut prix**, **mode facturation**, **alerte encours** si applicable. |

### P2 — Impact fort (modernité & cohérence)

| ID | Action |
|----|--------|
| P2-1 | **Unifier le design system** portail client (migrer écrans legacy vers DaisyUI + tokens, ou documenter un seul langage imposé). |
| P2-2 | Supprimer les chips redondantes ou les **relier** à l’étape / onglet actif. |
| P2-3 | **Panneau uploads** : colonnes alignées avec le checkout (qté, couleur, métrage/prix). |
| P2-4 | **Login** : aligner header / coquille sur le portail (`portal_header` ou variante documentée). |
| P2-5 | **KPI** : retirer les `<h2>` sur les seules valeurs chiffrées ; préserver une hiérarchie de titres logique. |

### P3 — Polish pixel-perfect

| ID | Action |
|----|--------|
| P3-1 | Tables : variante **mobile** (lignes type cards). |
| P3-2 | Tailles fichiers : **Ko / Mo** lisibles. |
| P3-3 | Micro-interactions : focus visible sur onglets, transitions légères (voir stack Tailwind + DaisyUI du projet). |
| P3-4 | Harmoniser le **ton** facturation entre checkout et panneau Facture. |

---

## 7. Références internes

- Stack UI : `.agents/skills/skill-ids-hub-frontend-stack/SKILL.md`
- Audit landing (méthodologie) : `.agents/skills/skill-landing-audit-pixel-perfect/SKILL.md`
- Métier commandes B2B : `docs/architecture/B2B_DEFERRED_BILLING.md`
- Guide UX front existant : `docs/product-design/UX_FRONT_GUIDE.md`

---

## 8. Prochaine revue

- Re-scorer après traitement des **P1** et au moins **2 items P2** (design system + onglets).
- Cible indicative : **≥ 75/100** pour qualifier l’espace client de « premium » au sens de ce document.

---

## 9. Mise à jour — système de boutons

Lot du 2026-06-14 :

- Ajout d’une couche commune `components/buttons.css` pour unifier les actions SaaS (`ui-btn`, `ui-btn-primary`, `ui-btn-secondary`, `ui-btn-ghost`, `ui-btn-danger`, `ui-btn-sm`, `ui-btn-wide`, `ui-btn-block`).
- Tokens d’action ajoutés dans `tokens.css` : hauteur minimale, bordure, ombre dure, transition, couleurs primaire/secondaire.
- Portail client/staff, checkout, login, empty states, tunnel prospect et actions staff migrés vers les classes sémantiques `ui-btn`.
- Conservation du style landing brutaliste via `agency-button` et du CTA nav marketing, mais avec la même exigence de cible tactile et hiérarchie.
- Tests de cohérence ajoutés pour empêcher le retour de boutons métier en `.btn` brut ou en `dui-btn` forcé.

## 10. Mise à jour — audit global des vues

Lot du 2026-06-14 :

- Audit global ajouté : `docs/product-design/AUDIT_GLOBAL_UI_UX_VUES_2026-06-14.md`.
- Orchestration avec 3 sous-agents : surfaces publiques/prospect, portail client/staff, scan statique transverse.
- P1 onglets HTMX traité par persistance `?panel=...`, `hx-push-url` et chargement initial du panneau actif.
- Header landing et portail harmonisés : suppression des anciens boutons `.btn` dans les templates de navigation, mode `auth` neutre sur login, libellés staff FR.
- États vides client/staff rendus actionnables.
- Panneau shipping staff aligné avec le payload backend déjà accepté.

## 11. Mise à jour — polish Impeccable de la fiche commande

Lot du 2026-07-21 :

- résumé restructuré en faits sémantiques (`Statut`, `Commande soumise`, `Tarification`) avec prise en charge explicite de l’alerte encours ;
- note client isolée sous le libellé `Informations transmises`, sans modifier sa donnée métier ;
- référence client contextualisée dans le titre et breadcrumb raccourci sur mobile ;
- onglets HTMX portés à une cible tactile de `44 px`, état actif et URL `?panel=` conservés ;
- quatre niveaux de cadres/ombres imbriqués ramenés à une seule surface de workflow ;
- panneaux Visuels, Avancement, Expédition et Facture alignés sur une classe client commune ;
- noms de fichiers longs, cartes mobiles et boutons contenus dans la largeur utile ;
- recette authentifiée à `1280 × 900` et `375 × 812`, sans overflow ni erreur console ;
- sécurité inchangée : routes UUID, scope client et distinction membre/propriétaire conservés ;
- validation : `480` tests complets, `60` tests ciblés, Ruff, Django et migrations conformes.

## 12. Mise à jour — header SaaS et menu profil

Lot du 2026-07-21 :

- compte connecté regroupé sous une entrée compacte `initiale + Mon compte`, sans nom, prénom ni e-mail dans le déclencheur ;
- rôle et espace courant explicités dans le panneau, avec une page `Mes informations` dédiée à la modification du prénom et du nom ;
- e-mail de connexion conservé en lecture seule pour éviter un changement d’identifiant insuffisamment sécurisé ;
- raccourcis contextualisés : gestion d’équipe pour les rôles autorisés et bascule Atelier pour les comptes hybrides ;
- raccourci `Voir le site` supprimé car sans utilité dans ce parcours authentifié ;
- déconnexion POST avec jeton CSRF conservée et isolée des actions de navigation ;
- composant progressif basé sur `details/summary`, complété par fermeture mutuelle, clic extérieur et restitution du focus sur `Escape` ;
- menu mobile intégré au flux, largeur bornée et cibles tactiles d’au moins `44 px` ;
- ajout de la route authentifiée `/account/profile/`, sans changement de scope client ni de permission objet.

Complément du même lot :

- libellé `Dashboard` adopté dans les navigations client et Atelier ;
- résolution du rôle centralisée pour supprimer l’affichage intermittent de `Gérer l’équipe` entre les vues ;
- action `Créer une commande` transformée en menu progressif avec deux intentions explicites : fichiers prêts à produire ou Gang Sheet ;
- option Gang Sheet masquée si le flag global ou l’éligibilité du client ne l’autorise pas ;
- lien autonome `Planches DTF` retiré du header afin de garder une seule entrée de création ;
- fermeture mutuelle des menus `Créer`, `Outils` et `Mon compte`, avec support `Escape` et clic extérieur.

## 13. Mise à jour — centre de compte et bibliothèque Gang Sheets

Lot du 2026-07-21 :

- page `Mon compte` distillée en une seule surface de formulaire, avec identité et navigation contextuelle séparées du contenu éditable ;
- bouton d’enregistrement désactivé tant qu’aucune modification n’est détectée, avec repli progressif si JavaScript est indisponible ;
- confirmation après sauvegarde diffusée dans le système de toast commun, sans déplacement de la mise en page ;
- accès Owner à `Gérer l’équipe` conservé dans le rail du compte ;
- liste Gang Sheets transformée en bibliothèque visuelle : titre compact, CTA `Nouvelle planche`, filtres de statut, recherche locale et cartes adaptées aux statuts métier ;
- parcours explicatif en quatre étapes retiré de la liste et conservé dans le studio, où il accompagne réellement l’utilisateur ;
- formulaire de création déplacé dans un dialogue accessible, automatiquement rouvert avec l’erreur inline en cas de validation serveur ;
- vrais aperçus servis en disposition inline par la route authentifiée et scopée existante ;
- suppression reléguée dans un menu secondaire, puis confirmée par le dialogue sécurisé existant ;
- recette réelle desktop/mobile sans débordement, y compris toolbar défilante à `375 px`.

## 14. Mise à jour — studio Gang Sheet premium

Lot du 2026-07-21 :

- hiérarchie recentrée sur le travail de composition : identité compacte, indicateurs utiles et canevas dominant ;
- planche longue contenue dans un espace de travail dimensionné au viewport, avec défilement interne au lieu d’allonger toute la page ;
- bibliothèque et inspecteur rendus indépendants afin de conserver les outils visibles pendant la composition ;
- progression synchronisée avec les statuts `draft`, `rendering`, `ready` et `validated` ;
- modifications locales signalées explicitement, bouton d’enregistrement contextualisé et prévention d’une sortie accidentelle ;
- zoom accessible à `50`, `75`, `100`, `125` et `150 %`, sans modifier les coordonnées ni les dimensions métier ;
- expérience mobile convertie en navigation par sections, `Composition` étant la tâche affichée par défaut ;
- contrôles de production regroupés et reformulés sans exposer le PDF HD protégé ;
- endpoints, permissions multi-tenant et règles de validation inchangés.
