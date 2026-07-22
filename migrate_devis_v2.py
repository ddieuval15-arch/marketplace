"""
Migration devis v2 — ajoute les colonnes manquantes.
Exécuter UNE SEULE FOIS dans la console Bash PythonAnywhere :
  python3 /home/donytchicaya/hellobiz/migrate_devis_v2.py
"""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), 'data', 'marketplace.db')
db = sqlite3.connect(DB)

migrations = [
    "ALTER TABLE devis ADD COLUMN date_emission TEXT",
    "ALTER TABLE devis ADD COLUMN sous_total REAL DEFAULT 0",
    "ALTER TABLE devis ADD COLUMN remise_pct REAL DEFAULT 0",
    "ALTER TABLE devis ADD COLUMN montant_lettres TEXT",
]

for sql in migrations:
    try:
        db.execute(sql)
        print('OK :', sql)
    except sqlite3.OperationalError as e:
        print('Skip (déjà existant) :', e)

# Remplir date_emission pour les enregistrements existants
db.execute("UPDATE devis SET date_emission = date_creation WHERE date_emission IS NULL")
db.execute("UPDATE devis SET sous_total = total WHERE sous_total = 0 OR sous_total IS NULL")
db.execute("UPDATE devis SET remise_pct = 0 WHERE remise_pct IS NULL")

db.commit()
db.close()
print('\nMigration terminée.')
