import sqlite3
import os

DB_PATH = os.environ.get('DB_PATH',
    os.path.join(os.path.dirname(__file__), 'data', 'marketplace.db'))

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            nom TEXT NOT NULL,
            icon TEXT NOT NULL,
            ordre INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS villes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            nom TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS quartiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            nom TEXT NOT NULL,
            ville_id INTEGER NOT NULL,
            FOREIGN KEY (ville_id) REFERENCES villes(id)
        );
        CREATE TABLE IF NOT EXISTS boutiques (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            nom TEXT NOT NULL,
            description TEXT,
            categorie_id INTEGER,
            ville_id INTEGER,
            telephone TEXT,
            whatsapp TEXT,
            email TEXT,
            logo TEXT,
            banniere TEXT,
            plan TEXT DEFAULT "starter",
            badge_verifie INTEGER DEFAULT 0,
            actif INTEGER DEFAULT 1,
            vendeur_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (categorie_id) REFERENCES categories(id),
            FOREIGN KEY (ville_id) REFERENCES villes(id)
        );
        CREATE TABLE IF NOT EXISTS annonces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            titre TEXT NOT NULL,
            description TEXT,
            prix REAL,
            prix_type TEXT DEFAULT "fixe",
            categorie_id INTEGER,
            ville_id INTEGER,
            boutique_id INTEGER,
            statut TEXT DEFAULT "active",
            vues INTEGER DEFAULT 0,
            contacts INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (categorie_id) REFERENCES categories(id),
            FOREIGN KEY (ville_id) REFERENCES villes(id),
            FOREIGN KEY (boutique_id) REFERENCES boutiques(id)
        );
        CREATE TABLE IF NOT EXISTS vendeurs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            email TEXT UNIQUE,
            telephone TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            actif INTEGER DEFAULT 1,
            is_admin INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            annonce_id INTEGER,
            url TEXT NOT NULL,
            principale INTEGER DEFAULT 0,
            FOREIGN KEY (annonce_id) REFERENCES annonces(id)
        );
        CREATE TABLE IF NOT EXISTS vues_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            annonce_id INTEGER NOT NULL,
            date DATE NOT NULL,
            nb_vues INTEGER DEFAULT 1,
            UNIQUE(annonce_id, date),
            FOREIGN KEY (annonce_id) REFERENCES annonces(id)
        );
        CREATE TABLE IF NOT EXISTS alertes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendeur_id INTEGER NOT NULL,
            nom TEXT NOT NULL,
            categorie_id INTEGER,
            ville_id INTEGER,
            quartier_id INTEGER,
            prix_min REAL,
            prix_max REAL,
            mots_cles TEXT,
            actif INTEGER DEFAULT 1,
            derniere_verif DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vendeur_id) REFERENCES vendeurs(id)
        );
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            annonce_id INTEGER NOT NULL,
            expediteur_id INTEGER NOT NULL,
            destinataire_id INTEGER NOT NULL,
            lu_expediteur INTEGER DEFAULT 1,
            lu_destinataire INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (annonce_id) REFERENCES annonces(id),
            FOREIGN KEY (expediteur_id) REFERENCES vendeurs(id),
            FOREIGN KEY (destinataire_id) REFERENCES vendeurs(id)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            auteur_id INTEGER NOT NULL,
            contenu TEXT NOT NULL,
            lu INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id),
            FOREIGN KEY (auteur_id) REFERENCES vendeurs(id)
        );
        CREATE TABLE IF NOT EXISTS favoris (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendeur_id INTEGER NOT NULL,
            annonce_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(vendeur_id, annonce_id),
            FOREIGN KEY (vendeur_id) REFERENCES vendeurs(id),
            FOREIGN KEY (annonce_id) REFERENCES annonces(id)
        );
        CREATE TABLE IF NOT EXISTS publicites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            annonceur TEXT NOT NULL,
            image_url TEXT NOT NULL,
            lien TEXT NOT NULL,
            titre TEXT,
            emplacement TEXT DEFAULT "banniere_top",
            date_debut DATE NOT NULL,
            date_fin DATE NOT NULL,
            montant REAL DEFAULT 0,
            statut TEXT DEFAULT "active",
            clics INTEGER DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS paiements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT UNIQUE NOT NULL,
            vendeur_id INTEGER NOT NULL,
            boutique_id INTEGER,
            annonce_id INTEGER,
            type TEXT NOT NULL,
            montant REAL NOT NULL,
            operateur TEXT NOT NULL,
            telephone TEXT NOT NULL,
            statut TEXT DEFAULT "en_attente",
            plan_cible TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            confirmed_at DATETIME,
            FOREIGN KEY (vendeur_id) REFERENCES vendeurs(id),
            FOREIGN KEY (boutique_id) REFERENCES boutiques(id),
            FOREIGN KEY (annonce_id) REFERENCES annonces(id)
        );
        CREATE TABLE IF NOT EXISTS avis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auteur_id INTEGER NOT NULL,
            boutique_id INTEGER NOT NULL,
            note INTEGER NOT NULL CHECK(note BETWEEN 1 AND 5),
            commentaire TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(auteur_id, boutique_id),
            FOREIGN KEY (auteur_id) REFERENCES vendeurs(id),
            FOREIGN KEY (boutique_id) REFERENCES boutiques(id)
        );
    ''')

    # Seed categories
    cats = [
        ('immobilier',      'Immobilier',          'building',        1),
        ('vehicules',       'Vehicules',           'car',             2),
        ('telephones',      'Telephones',          'device-mobile',   3),
        ('electronique',    'Electronique',        'plug',            4),
        ('electromenager',  'Electromenager',      'wash-machine',    5),
        ('informatique',    'Informatique',        'device-laptop',   6),
        ('mode',            'Mode & Beaute',       'shirt',           7),
        ('maison',          'Maison & Deco',       'sofa',            8),
        ('livres',          'Livres & Ebooks',     'book',            9),
        ('alimentation',    'Alimentation',        'salad',          10),
        ('services',        'Services',            'tool',           11),
        ('emploi',          'Emploi',              'briefcase',      12),
        ('loisirs',         'Loisirs & Sport',     'ball-football',  13),
        ('enfants',         'Enfants & Bebes',     'baby-carriage',  14),
        ('animaux',         'Animaux',             'paw',            15),
        ('autres',          'Autres',              'dots',           16),
    ]
    for slug, nom, icon, ordre in cats:
        c.execute('INSERT OR IGNORE INTO categories (slug, nom, icon, ordre) VALUES (?,?,?,?)',
                  (slug, nom, icon, ordre))

    # Seed villes
    villes = [
        ('brazzaville', 'Brazzaville'),
        ('pointe-noire', 'Pointe-Noire'),
        ('dolisie', 'Dolisie'),
        ('nkayi', 'Nkayi'),
        ('ouesso', 'Ouesso'),
    ]
    for slug, nom in villes:
        c.execute('INSERT OR IGNORE INTO villes (slug, nom) VALUES (?,?)', (slug, nom))

    # Seed boutiques demo
    boutiques_demo = [
        ('agence-natacha-immo', 'Agence Natacha Immo',
         'Specialiste de l immobilier residentiel et commercial a Pointe-Noire depuis 2018.',
         1, 2, '(+242) 06 XXX XX XX', '(+242) 06 XXX XX XX', 'natacha@immo-pnr.cg', 'pro', 1),
        ('electro-congo', 'ElectroCongo',
         'Vente de telephones, accessoires et electronique a Brazzaville. Produits garantis.',
         3, 1, '(+242) 05 XXX XX XX', '(+242) 05 XXX XX XX', 'electro@congo.cg', 'pro', 1),
        ('btp-propre-services', 'BTP Propre Services',
         'Services de nettoyage professionnel fin de chantier, bureaux et residences.',
         5, 1, '(+242) 06 XXX XX XX', '(+242) 06 XXX XX XX', 'btp@propre.cg', 'starter', 0),
        ('auto-prestige-pnr', 'Auto Prestige Pointe-Noire',
         "Vente et location de vehicules neufs et d occasion a Pointe-Noire.",
         2, 2, '(+242) 05 XXX XX XX', '(+242) 05 XXX XX XX', 'auto@prestige.cg', 'premium', 1),
        ('mode-tendance-bzv', 'Mode Tendance Brazzaville',
         'Vetements, chaussures et accessoires pour femmes et hommes.',
         7, 1, '(+242) 06 XXX XX XX', '(+242) 06 XXX XX XX', 'mode@tendance.cg', 'starter', 0),
    ]
    for slug, nom, desc, cat, ville, tel, wa, email, plan, verifie in boutiques_demo:
        c.execute('''INSERT OR IGNORE INTO boutiques
            (slug, nom, description, categorie_id, ville_id, telephone, whatsapp, email, plan, badge_verifie)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (slug, nom, desc, cat, ville, tel, wa, email, plan, verifie))

    # Seed annonces demo
    import random
    annonces_demo = [
        ('villa-f4-meublee-ngoyo', 'Villa F4 meublee Ngoyo',
         'Belle villa 4 pieces entierement meublee, gardiennage 24h, parking, quartier calme.',
         250000, 'mois', 1, 2, 1),
        ('appartement-f3-lumumba', 'Appartement F3 Lumumba',
         'Appartement 3 pieces en bon etat, cuisine equipee, salle de bain moderne.',
         8500000, 'fixe', 1, 2, 1),
        ('local-commercial-centre', 'Local commercial centre-ville',
         'Local commercial 80m2 idealement situe au centre de Pointe-Noire.',
         180000, 'mois', 1, 2, 1),
        ('terrain-500m2-tie-tie', 'Terrain 500m2 Tie-Tie',
         'Terrain constructible 500m2 avec titre foncier, electricite et eau en bordure.',
         3200000, 'fixe', 1, 2, 1),
        ('samsung-galaxy-s24-ultra', 'Samsung Galaxy S24 Ultra 256 Go',
         'Telephone en parfait etat, boite et accessoires d origine, garantie 6 mois.',
         420000, 'fixe', 3, 2, 2),
        ('iphone-12-128go', 'iPhone 12 128 Go Noir',
         'iPhone 12 debloque tous operateurs, batterie 95%, sans rayure.',
         185000, 'fixe', 3, 1, 2),
        ('toyota-hilux-2022', 'Toyota Hilux 2022 double cabine',
         '4x4 Toyota Hilux double cabine, 45 000 km, premiere main.',
         12500000, 'fixe', 2, 2, 4),
        ('renault-duster-2020', 'Renault Duster 2020 Gris',
         'SUV en excellent etat, climatisation, direction assistee, 4 pneus neufs.',
         6800000, 'fixe', 2, 2, 4),
        ('nettoyage-canape-matelas', 'Nettoyage canape et matelas a domicile',
         'Service professionnel de nettoyage textile. Canape, matelas, tapis.',
         10000, 'fixe', 5, 1, 3),
        ('plomberie-electricite-bzv', 'Plomberie et electricite Brazzaville',
         'Interventions rapides plomberie et electricite, devis gratuit, 7j/7.',
         0, 'negociable', 5, 1, 3),
        ('robe-longue-tendance', 'Robe longue tendance plusieurs couleurs',
         'Robe longue elegante en 6 couleurs, tailles S a XXL, livraison possible.',
         18000, 'fixe', 7, 1, 5),
        ('salon-complet-3pieces', 'Salon complet 3 pieces cuir',
         'Beau salon en cuir veritable, tres bon etat, couleur marron.',
         450000, 'fixe', 8, 1, 5),
    ]
    for slug, titre, desc, prix, prix_type, cat, ville, boutique in annonces_demo:
        c.execute('''INSERT OR IGNORE INTO annonces
            (slug, titre, description, prix, prix_type, categorie_id, ville_id, boutique_id, vues)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (slug, titre, desc, prix, prix_type, cat, ville, boutique,
             random.randint(20, 400)))

    # Migrations (colonnes ajoutees progressivement)
    migrations = [
        "ALTER TABLE vendeurs ADD COLUMN is_admin INTEGER DEFAULT 0",
        "ALTER TABLE publicites ADD COLUMN emplacement TEXT DEFAULT 'banniere_top'",
        "ALTER TABLE annonces ADD COLUMN quartier_id INTEGER",
        "ALTER TABLE annonces ADD COLUMN renewed_at DATETIME",
        "ALTER TABLE annonces ADD COLUMN bon_plan INTEGER DEFAULT 0",
        "ALTER TABLE annonces ADD COLUMN bon_plan_expire DATETIME",
        # Signalements
        '''CREATE TABLE IF NOT EXISTS signalements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            annonce_id INTEGER NOT NULL,
            vendeur_id INTEGER,
            raison TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(annonce_id, vendeur_id),
            FOREIGN KEY (annonce_id) REFERENCES annonces(id)
        )''',
        # Champs Emploi
        "ALTER TABLE annonces ADD COLUMN emploi_type TEXT",
        "ALTER TABLE annonces ADD COLUMN emploi_secteur TEXT",
        "ALTER TABLE annonces ADD COLUMN emploi_salaire TEXT",
        "ALTER TABLE annonces ADD COLUMN expire_at DATETIME",
        # Espace Entreprise Pro
        "ALTER TABLE boutiques ADD COLUMN horaires TEXT",
        "ALTER TABLE boutiques ADD COLUMN site_web TEXT",
        "ALTER TABLE boutiques ADD COLUMN rccm TEXT",
        "ALTER TABLE boutiques ADD COLUMN facebook TEXT",
        "ALTER TABLE boutiques ADD COLUMN instagram TEXT",
        "ALTER TABLE boutiques ADD COLUMN is_entreprise INTEGER DEFAULT 0",
        "ALTER TABLE boutiques ADD COLUMN secteur TEXT",
        "ALTER TABLE vendeurs ADD COLUMN parrain_code TEXT",
        "ALTER TABLE vendeurs ADD COLUMN parrain_id INTEGER",
        "ALTER TABLE annonces ADD COLUMN immo_type TEXT",
        "ALTER TABLE annonces ADD COLUMN immo_superficie INTEGER",
        "ALTER TABLE annonces ADD COLUMN immo_chambres INTEGER",
        "ALTER TABLE annonces ADD COLUMN immo_transaction TEXT",
        "CREATE TABLE IF NOT EXISTS reset_tokens (id INTEGER PRIMARY KEY AUTOINCREMENT, vendeur_id INTEGER NOT NULL, token TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT (datetime(\'now\')), FOREIGN KEY (vendeur_id) REFERENCES vendeurs(id))",

        "ALTER TABLE boutiques ADD COLUMN adresse TEXT",
        "ALTER TABLE boutiques ADD COLUMN fermeture_message TEXT",
        "ALTER TABLE boutiques ADD COLUMN disponibilite_type TEXT",
        "ALTER TABLE boutiques ADD COLUMN adresse TEXT",
        "ALTER TABLE boutiques ADD COLUMN fermeture_message TEXT",
        "ALTER TABLE boutiques ADD COLUMN disponibilite_type TEXT",
        "ALTER TABLE boutiques ADD COLUMN adresse TEXT",
        "ALTER TABLE boutiques ADD COLUMN fermeture_message TEXT",
        "ALTER TABLE boutiques ADD COLUMN disponibilite_type TEXT",
        "ALTER TABLE boutiques ADD COLUMN adresse TEXT",
        "ALTER TABLE boutiques ADD COLUMN fermeture_message TEXT",
        "ALTER TABLE boutiques ADD COLUMN disponibilite_type TEXT",
        "ALTER TABLE boutiques ADD COLUMN adresse TEXT",
        "ALTER TABLE boutiques ADD COLUMN fermeture_message TEXT",
        "ALTER TABLE boutiques ADD COLUMN disponibilite_type TEXT",
    ]
    for sql in migrations:
        try:
            c.execute(sql)
        except Exception:
            pass

    # Seed quartiers
    quartiers = [
        ('tie-tie', 'Tie-Tie', 2), ('fond-tie-tie', 'Fond Tie-Tie', 2),
        ('siafoumou', 'Siafoumou', 2), ('tchialy', 'Tchialy', 2),
        ('mawata', 'Mawata', 2), ('ngoyo', 'Ngoyo', 2),
        ('mpita', 'Mpita', 2), ('tchimbamba', 'Tchimbamba', 2),
        ('grand-marche-pnr', 'Grand Marche', 2), ('centre-ville-pnr', 'Centre-ville', 2),
        ('lumumba', 'Lumumba', 2), ('mvoumvou', 'Mvoumvou', 2),
        ('loandjili', 'Loandjili', 2), ('mongo-mpoukou', 'Mongo Mpoukou', 2),
        ('km4', 'Km4', 2), ('boscongo', 'Boscongo', 2),
        ('mpaka', 'Mpaka', 2), ('wharf', 'Wharf', 2),
        ('sangolo', 'Sangolo', 2), ('la-base', 'La Base', 2),
        ('patra', 'Patra', 2), ('malala', 'Malala', 2),
        ('aeroport-pnr', 'Aeroport', 2),
        ('poto-poto', 'Poto-Poto', 1), ('bacongo', 'Bacongo', 1),
        ('makelelele', 'Makelelele', 1), ('moungali', 'Moungali', 1),
        ('och', 'OCH', 1), ('talangai', 'Talangai', 1),
        ('ngamaba', 'Ngamaba', 1), ('madibou', 'Madibou', 1),
        ('plateau-15-ans', 'Plateau des 15 ans', 1), ('djiri', 'Djiri', 1),
    ]
    for slug, nom, ville_id in quartiers:
        c.execute('INSERT OR IGNORE INTO quartiers (slug, nom, ville_id) VALUES (?,?,?)',
                  (slug, nom, ville_id))

    # Compte vendeur Dony (compte de test)
    from werkzeug.security import generate_password_hash
    pwd_dony = generate_password_hash('devousLR2026')
    c.execute('''INSERT OR IGNORE INTO vendeurs (nom, email, telephone, password_hash, actif)
        VALUES (?,?,?,?,1)''',
        ('Dony TCHICAYA', 'ddieuval15@gmail.com', '+242060612350', pwd_dony))

    # Compte admin
    pwd = generate_password_hash('Admin@2026')
    c.execute('''INSERT OR IGNORE INTO vendeurs
        (nom, email, telephone, password_hash, actif, is_admin)
        VALUES (?,?,?,?,?,?)''',
        ('Administrateur', 'admin@kongoannonces.cg', '+242000000000', pwd, 1, 1))
    c.execute(
        "UPDATE vendeurs SET is_admin=1, password_hash=?, actif=1 WHERE email='admin@kongoannonces.cg'",
        (pwd,))

    conn.commit()
    conn.close()
    print("DB initialisee.")

if __name__ == '__main__':
    init_db()
