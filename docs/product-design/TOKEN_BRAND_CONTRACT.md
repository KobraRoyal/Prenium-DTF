# Contrat tokens & identité Atelier

Document de référence pour garder une UI cohérente **et** permettre à un administrateur Atelier de changer les couleurs d’action sans toucher au CSS.

## Ce qui est déjà en place

La vue dédiée existe : **Identité visuelle** → `/staff/settings/branding/` (`portal:staff-brand-settings`).

Ce n’est pas `/admin/` Django, ni le profil compte. C’est un écran Operate Atelier, permission `branding.view_brandthemesettings` (lecture) / `branding.change_brandthemesettings` (écriture). Singleton global (`BrandThemeSettings.singleton_key = 1`) : une palette pour tout le site, tous les clients.

Champs configurables aujourd’hui :

| Champ formulaire | Token CSS runtime | Rôle |
|---|---|---|
| Couleur primaire | `--brand`, `--brand-strong`, `--brand-soft`, `--action-text` | Bouton primaire, lockup, sélection Studio |
| Couleur secondaire | `--accent`, `--accent-strong`, `--accent-soft`, `--accent-text` | Accents, focus, repères |

Les dérivés (`-strong`, `-soft`, encre lisible) sont calculés par `apps.branding.services.build_brand_theme` (contraste WCAG). L’administrateur ne choisit **que** primaire et secondaire.

## Architecture trois couches

```
Primitive (DB)     BrandThemeSettings.primary_color / secondary_color
        ↓
Sémantique (CSS)   --brand / --accent  (injectés sur <html> dans base.html)
        ↓
Composant          --ui-action-primary-bg: var(--brand)
                   .ui-btn-primary { background: var(--ui-action-primary-bg) }
```

1. **Défauts compile-time** : `backend/static_src/css/tokens.css` = DESIGN.md (`#ff8775` / `#a83bc4`).
2. **Surcharge runtime** : `style="--brand: …"` sur `<html>` depuis `site_brand_theme`.
3. **Composants** : uniquement `var(--brand)`, `var(--accent)`, `var(--ui-action-*)`. Jamais un hex corail/violet recopié dans un composant.

Tailwind `theme.extend.colors.brand` pointe vers `var(--brand)` pour suivre la palette live. Le thème DaisyUI `prenium` garde un **snapshot hex** des défauts (Daisy ne résout pas les custom properties dans sa config). Daisy est préfixé `dui-` et **n’est pas** le design system : le markup utilise `ui-btn`, pas `dui-btn`.

## Non configurable (volontaire)

Neutres (crème, encre, ligne), statuts (succès / warning / danger), typo (Space Grotesk / DM Sans), rayons, ombres sticker. Les changer casserait la lisibilité Operate et le contrat WCAG des badges métier.

## Règles pour tout nouveau CSS

- Action / sélection / focus marque → `var(--brand)` ou `var(--ui-action-*)`.
- Accent / anneau clavier → `var(--accent)` / `var(--accent-strong)`.
- Surface / texte / bordure → `var(--bg)`, `var(--surface)`, `var(--ink)`, `var(--line)`.
- Interdit : `#8f3d1f`, `#6f2f17` (ancien brun), hex corail copié dans un composant.
- Test : `tests/ui/test_brand_token_contract.py`.

## Vue Identité visuelle — contrat UX (ne pas casser)

Mode **Operate**. Une tâche : choisir primaire + secondaire, prévisualiser, enregistrer.

- Sélecteur couleur **et** champ hex (les deux synchronisés Alpine).
- Aperçu immédiat (carte Client) avant enregistrement.
- Une action primaire : « Appliquer aux deux espaces ».
- Secondaire : « Restaurer la palette claire ».
- Lecture seule pour le staff sans `change_brandthemesettings`.
- Toast de confirmation. Audit `branding.theme.updated`.

**Prochaine feature (hors ce lot)** : enrichir **cette même vue**, pas un second écran. Candidates possibles, seulement si un token sémantique existe déjà : aperçu Atelier à côté de l’aperçu Client, validation contrast live plus visible. Ne pas exposer les neutres ni les statuts sans décision produit.

## Fichiers propriétaires

| Fichier | Responsabilité |
|---|---|
| `backend/static_src/css/tokens.css` | Défauts + alias `--ui-brand` |
| `backend/templates/base.html` | Injection runtime |
| `backend/apps/branding/` | Modèle, service, form, permissions |
| `backend/templates/portal/staff/settings/branding.html` | Vue Atelier |
| `backend/tailwind.config.js` | Snapshot Daisy + `brand: var(--brand)` |
| `DESIGN.md` | Identité visuelle normative |

## Hors scope

Studio canvas, gang-sheet editor, configurateur B2B : chrome `var(--brand)`, logique métier inchangée. labb / django-cotton : pas dans ce contrat.
