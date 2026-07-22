"""
Script à exécuter dans la console Bash de PythonAnywhere :
  cd /home/donytchicaya/hellobiz
  python insert_realisations_photos.py
"""
import sqlite3
import os

DB_PATH = '/home/donytchicaya/hellobiz/data/marketplace.db'
UPLOADS_DIR = '/home/donytchicaya/hellobiz/static/uploads/'

# Photos à insérer : slug annonce → nom de fichier image
photos = {
    'realisation-clinique-provet':     'realisation_clinique_provet.jpg',
    'realisation-roselyne-aissi':      'realisation_roselyne_aissi.jpg',
    'realisation-pump-oil-nexora':     'realisation_devousamoijobbing.jpg',
}

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

for slug, filename in photos.items():
    # Vérifier que l'image existe
    filepath = os.path.join(UPLOADS_DIR, filename)
    if not os.path.exists(filepath):
        print(f'⚠️  Fichier manquant : {filepath}')
        continue

    # Récupérer l'ID de l'annonce
    c.execute('SELECT id, titre FROM annonces WHERE slug = ?', (slug,))
    row = c.fetchone()
    if not row:
        print(f'❌ Annonce non trouvée : {slug}')
        continue

    annonce_id, titre = row

    # Supprimer les photos existantes pour cette annonce
    c.execute('DELETE FROM photos WHERE annonce_id = ?', (annonce_id,))

    # Insérer la nouvelle photo
    url = f'/static/uploads/{filename}'
    c.execute(
        "INSERT INTO photos (annonce_id, url, principale, created_at) VALUES (?, ?, 1, datetime('now'))",
        (annonce_id, url)
    )
    print(f'✓ [{annonce_id}] {titre}  →  {url}')

conn.commit()
conn.close()
print('\n✅ Terminé — rechargez la page boutique NEXORA pour voir les images.')
