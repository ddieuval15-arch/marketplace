"""
Script de migration — Module Devis & Factures helloBiz
À exécuter UNE seule fois dans la console Bash PythonAnywhere :
  cd /home/donytchicaya/hellobiz
  python migrate_devis.py
"""
import sqlite3, os

DB_PATH = os.environ.get('DB_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'marketplace.db'))

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# ── 1. Profil entreprise pour les documents ──────────────────────────
c.execute('''
CREATE TABLE IF NOT EXISTS devis_profil (
    id          INTEGER PRIMARY KEY,
    boutique_id INTEGER UNIQUE NOT NULL,
    nom         TEXT,
    rccm        TEXT,
    adresse     TEXT,
    telephone   TEXT,
    email       TEXT,
    banque      TEXT,
    conditions  TEXT DEFAULT 'Paiement par Mobile Money (MTN MoMo / Airtel Money) ou espèces.',
    logo_path   TEXT,
    FOREIGN KEY (boutique_id) REFERENCES boutiques(id)
)
''')
print('✓ Table devis_profil')

# ── 2. Devis & Factures ──────────────────────────────────────────────
c.execute('''
CREATE TABLE IF NOT EXISTS devis (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    boutique_id     INTEGER NOT NULL,
    numero          TEXT NOT NULL,
    type            TEXT DEFAULT 'devis',
    client_nom      TEXT NOT NULL,
    client_contact  TEXT,
    date_creation   TEXT DEFAULT (date('now')),
    date_validite   TEXT,
    statut          TEXT DEFAULT 'brouillon',
    notes           TEXT,
    conditions      TEXT,
    total           REAL DEFAULT 0,
    devis_source_id INTEGER,
    FOREIGN KEY (boutique_id) REFERENCES boutiques(id)
)
''')
print('✓ Table devis')

# ── 3. Lignes de devis ───────────────────────────────────────────────
c.execute('''
CREATE TABLE IF NOT EXISTS devis_lignes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    devis_id      INTEGER NOT NULL,
    description   TEXT NOT NULL,
    quantite      REAL DEFAULT 1,
    prix_unitaire REAL DEFAULT 0,
    total         REAL DEFAULT 0,
    FOREIGN KEY (devis_id) REFERENCES devis(id) ON DELETE CASCADE
)
''')
print('✓ Table devis_lignes')

conn.commit()
conn.close()
print('\n✅ Migration terminée — le module Devis & Factures est prêt.')
