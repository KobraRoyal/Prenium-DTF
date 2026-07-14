# Audit frontend Atelier et Admin — 14 juillet 2026

## Verdict

**Score global : 86 / 100.** Le portail Atelier est cohérent, responsive et adapté au pilotage opérationnel. Le Django Admin reste volontairement une surface technique superuser : il est fonctionnel et responsive, mais son vocabulaire et son identité visuelle ne doivent pas être utilisés pour les réglages métier.

| Surface | Score | Verdict |
| --- | ---: | --- |
| Portail Atelier | **94 / 100** | Hiérarchie claire, actions lisibles, responsive 375 px sans débordement, console propre |
| Django Admin | **70 / 100** | Correct comme outil technique, mais modèles majoritairement nommés en anglais et identité distincte du portail produit |
| Éditeur d’e-mails | **94 / 100** | Intégré au portail Atelier, permissions fines, aperçu, tags contrôlés et audit des modifications |

## Périmètre contrôlé

- `/staff/` : dashboard Atelier, navigation, KPI et file commandes.
- `/staff/orders/` : liste desktop/mobile et cartes responsive.
- `/staff/orders/<uuid>/` : fiche commande, résumé, workflow et panneaux.
- `/admin/` : connexion, index desktop/mobile et séparation superuser.
- `/staff/settings/email-templates/` : liste des messages client/interne.
- éditeur d’un modèle : objet, corps, activation, insertion de tags et aperçu.

## Résultats navigateur

| Contrôle | Atelier | Admin |
| --- | :---: | :---: |
| Desktop 1440 × 1000 | ✓ | ✓ |
| Mobile 375 × 812 | ✓ | ✓ |
| Débordement horizontal | aucun | aucun |
| Console applicative | 0 erreur / 0 avertissement | 1 erreur favicon 404 sur la page de connexion |
| Navigation clavier / repères ARIA | conforme | standard Django conforme |

Captures de recette dans `output/playwright/` : dashboard Atelier, fiche commande mobile, Admin desktop/mobile et éditeur d’e-mails.

## Corrections livrées pendant l’audit

- Vocabulaire visible harmonisé autour de **l’Atelier** : suppression du mélange « staff / ops / Atelier » sur dashboard, titres et fils d’Ariane.
- Accents restaurés dans les KPI et états d’accès.
- Libellés métier français pour fichiers, expédition et facturation.
- Entrée **E-mails** ajoutée à la navigation uniquement pour les rôles autorisés.
- Éditeur produit créé dans le portail Atelier plutôt que dans le Django Admin technique.
- Interface responsive : messages clients et internes séparés, état actif, version, aperçu et insertion au curseur.

## Sécurité et cohérence métier

- Routes protégées par `accounts.access_staff_portal` puis permissions `notifications.view_emailtemplate` et `notifications.change_emailtemplate`.
- Aucun ID incrémental exposé : les routes utilisent les enums stables événement/audience.
- Le contenu enregistré n’est jamais exécuté comme template Django.
- Seuls les tags de la liste blanche sont remplacés ; `{% ... %}`, `{# ... #}`, tags inconnus et objet multi-ligne sont rejetés.
- Chaque modification est versionnée et tracée dans `AuditLogEntry`, sans recopier le contenu du message dans les métadonnées d’audit.
- La configuration est globale à Prenium DTF : aucune donnée client ou frontière `Customer` n’est stockée dans le modèle de configuration.

## Backlog

### P1

Aucun défaut bloquant restant sur le périmètre audité.

### P2

- Localiser les `verbose_name` encore anglais dans le Django Admin (`Accounts`, `Customers`, `Orders`, etc.).
- Ajouter un favicon au shell Django Admin pour supprimer le 404 de connexion.
- Ajouter une action « envoyer un e-mail de test » vers une adresse contrôlée, distincte d’un envoi métier réel.
- Ajouter un historique consultable avec restauration d’une version antérieure.
- Journaliser les résultats de livraison par audience pour faciliter le support SMTP.

### P3

- Créer une page « Réglages Atelier » si d’autres réglages métier rejoignent les e-mails.
- Étudier une version HTML de marque uniquement avec composants prédéfinis et sanitation stricte ; le lot actuel reste volontairement en texte brut.

## Checklist de validation

- [x] Atelier desktop et mobile vérifié.
- [x] Admin desktop et mobile vérifié.
- [x] Aucun overflow horizontal à 375 px.
- [x] Navigation et vocabulaire Atelier harmonisés.
- [x] Éditeur réservé par permissions serveur.
- [x] Tags inconnus et syntaxe Django rejetés.
- [x] Envois client/interne séparés.
- [x] Audit des modifications sans contenu sensible.
- [x] Tests service, permissions, rendu et intégration ajoutés.
