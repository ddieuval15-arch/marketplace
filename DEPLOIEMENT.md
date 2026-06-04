# Déploiement helloBiz — Guide rapide

## Option 1 : Démos terrain avec ngrok (gratuit, immédiat)

**Étapes :**
1. Télécharger ngrok : https://ngrok.com/download
2. Créer un compte gratuit sur ngrok.com
3. Lancer helloBiz normalement avec LANCER.bat
4. Dans un autre terminal, lancer : `ngrok http 5050`
5. Copier le lien `https://xxxx.ngrok-free.app` → partager aux prospects

**Avantage :** Zéro configuration, fonctionne en 2 minutes.
**Limite :** Le lien change à chaque session ngrok.

---

## Option 2 : PythonAnywhere (gratuit permanent)

**URL finale :** `https://votre_username.pythonanywhere.com`

### Étape 1 — Créer un compte
→ https://www.pythonanywhere.com (plan "Beginner" = gratuit)

### Étape 2 — Uploader le code
Dans la console PythonAnywhere (Bash) :
```bash
git clone https://github.com/votre_username/hellobiz.git
cd hellobiz
pip install -r requirements.txt
python database.py
```

### Étape 3 — Configurer l'app Web
- Aller dans "Web" → "Add a new web app"
- Choisir "Manual configuration" → Python 3.10
- Source code : `/home/votre_username/hellobiz`
- WSGI file : pointer vers `wsgi.py` du projet
- Dans wsgi.py, remplacer `votre_username` par votre vrai username

### Étape 4 — Dossiers statiques
Dans la config Web, ajouter :
- URL : `/static/` → Directory : `/home/votre_username/hellobiz/static`

### Étape 5 — Lancer
Cliquer "Reload" → votre app est en ligne !

---

## Option 3 : GitHub (sauvegarde du code)

```bash
git init
git add .
git commit -m "helloBiz v1 - marketplace Congo"
git remote add origin https://github.com/votre_username/hellobiz.git
git push -u origin main
```

**Important :** Le .gitignore exclut la base de données et les uploads.
