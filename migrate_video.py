import sqlite3

conn = sqlite3.connect('/home/donytchicaya/hellobiz/data/marketplace.db')
c = conn.cursor()

try:
    c.execute('ALTER TABLE annonces ADD COLUMN video_url TEXT')
    print('✓ Colonne video_url ajoutée')
except Exception as e:
    print(f'Info: {e}')

conn.commit()
conn.close()
print('Migration terminée !')
