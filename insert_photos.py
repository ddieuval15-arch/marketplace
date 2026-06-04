import sqlite3

photos = {
    'toyota-hilux-2022': [
        'https://images.unsplash.com/photo-1559416523-140ddc3d238c?w=800',
        'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800',
    ],
    'renault-duster-2020': [
        'https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?w=800',
    ],
    'villa-f4-meublee-ngoyo': [
        'https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=800',
        'https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800',
    ],
    'appartement-f3-lumumba': [
        'https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=800',
        'https://images.unsplash.com/photo-1554995207-c18c203602cb?w=800',
    ],
    'local-commercial-centre': [
        'https://images.unsplash.com/photo-1497366216548-37526070297c?w=800',
    ],
    'terrain-500m2-tie-tie': [
        'https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=800',
    ],
    'samsung-galaxy-s24-ultra': [
        'https://images.unsplash.com/photo-1610945265064-0e34e5519bbf?w=800',
        'https://images.unsplash.com/photo-1585060544812-6b45742d762f?w=800',
    ],
    'iphone-12-128go': [
        'https://images.unsplash.com/photo-1591337676887-a217a6970a8a?w=800',
        'https://images.unsplash.com/photo-1565849904461-04a58ad377e0?w=800',
    ],
}

conn = sqlite3.connect('/home/donytchicaya/hellobiz/data/hellobiz.db')
c = conn.cursor()

for slug, urls in photos.items():
    c.execute('SELECT id FROM annonces WHERE slug = ?', (slug,))
    row = c.fetchone()
    if not row:
        print(f'Annonce non trouvée : {slug}')
        continue
    annonce_id = row[0]
    c.execute('DELETE FROM photos WHERE annonce_id = ?', (annonce_id,))
    for i, url in enumerate(urls):
        principale = 1 if i == 0 else 0
        c.execute('INSERT INTO photos (annonce_id, url, principale) VALUES (?,?,?)',
                  (annonce_id, url, principale))
    print(f'✓ {slug} — {len(urls)} photo(s) ajoutée(s)')

conn.commit()
conn.close()
print('\nTerminé !')
