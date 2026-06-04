# KongoAnnonces — Marketplace Congo

Plateforme marketplace opérée par NEXORA Digital Solutions.
Développée avec Flask (Python) + SQLite.

---

## Lancement en local

```bash
# 1. Installer les dépendances
pip install flask

# 2. Lancer l'application
python app.py
```

L'app démarre sur → http://localhost:5050

---

## Pages disponibles

| URL | Description |
|-----|-------------|
| `/` | Homepage — recherche, catégories, annonces récentes |
| `/recherche?q=...&ville=...&categorie=...` | Recherche filtrée |
| `/annonce/<slug>` | Détail d'une annonce |
| `/boutique/<slug>` | Vitrine d'un vendeur |
| `/boutiques` | Liste de toutes les boutiques |

---

## Structure du projet

```
marketplace/
├── app.py              # Application Flask — toutes les routes
├── database.py         # Initialisation & seed de la base SQLite
├── data/               # Fichier SQLite (créé automatiquement)
├── templates/
│   ├── base.html       # Layout commun (navbar, footer)
│   └── pages/
│       ├── index.html      # Homepage
│       ├── recherche.html  # Page de résultats
│       ├── annonce.html    # Détail annonce
│       ├── boutique.html   # Vitrine vendeur
│       ├── boutiques.html  # Liste boutiques
│       └── 404.html
└── static/
    ├── css/style.css   # Tous les styles
    └── js/main.js      # JavaScript
```

---

## Stack technique

- **Backend** : Python 3 + Flask
- **Base de données** : SQLite (fichier local, zéro config)
- **Frontend** : HTML/CSS natif + Jinja2 templates
- **Icons** : Tabler Icons (CDN)
- **Déploiement** : N'importe quel VPS avec Python installé

---

## Déploiement production (VPS)

```bash
pip install flask gunicorn
gunicorn -w 4 -b 0.0.0.0:80 app:app
```

---

## Prochaines étapes de développement

1. Inscription & espace vendeur (dashboard)
2. Formulaire dépôt d'annonce avec upload photos
3. Intégration paiement Mobile Money (MTN / Airtel)
4. Dashboard admin NEXORA
5. Système de notifications (email / WhatsApp)

---

Développé par **NEXORA Digital Solutions** — Pointe-Noire, Congo
