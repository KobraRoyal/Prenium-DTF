# Modèle de matrice de tests

| ID | Domaine | Scénario | Type | Rôle | Précondition | Résultat attendu | Sécurité |
|---|---|---|---|---|---|---|---|
| T-001 | Orders | Client voit sa commande | Intégration | Client | Commande existante | 200 + bonne donnée | Oui |
| T-002 | Orders | Client A tente commande Client B | Intégration | Client | Deux clients | 403/404 | Oui |
