"""
Script d'insertion des annonces de démo — helloBiz
Exécuter UNE SEULE FOIS sur PythonAnywhere via la console :
  python insert_annonces_demo.py
"""
import sqlite3, os, re, unicodedata

DB_PATH = os.environ.get('DB_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'marketplace.db'))

def slugify(text):
    text = unicodedata.normalize('NFD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\w\s-]', '', text.lower())
    text = re.sub(r'[\s_-]+', '-', text).strip('-')
    return text

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# ── Récupérer IDs catégories et villes ─────────────────────────────
cats  = {r['slug']: r['id'] for r in c.execute("SELECT id, slug FROM categories")}
villes = {r['slug']: r['id'] for r in c.execute("SELECT id, slug FROM villes")}
boutiques = {r['slug']: r['id'] for r in c.execute("SELECT id, slug FROM boutiques")}

# ── Créer des boutiques de démo si nécessaire ───────────────────────
nouvelles_boutiques = [
    {
        'slug': 'techshop-pnr',
        'nom': 'TechShop Pointe-Noire',
        'description': 'Votre spécialiste en électronique, informatique et accessoires tech à Pointe-Noire.',
        'categorie': 'electronique',
        'ville': 'pointe-noire',
        'telephone': '06 000 00 01',
        'whatsapp': '06 000 00 01',
        'plan': 'pro',
        'badge_verifie': 1,
        'vendeur_id': 1,
    },
    {
        'slug': 'saveurs-congo',
        'nom': 'Saveurs du Congo',
        'description': 'Produits alimentaires frais, épices et spécialités congolaises livrés à domicile.',
        'categorie': 'alimentation',
        'ville': 'brazzaville',
        'telephone': '06 000 00 02',
        'whatsapp': '06 000 00 02',
        'plan': 'starter',
        'badge_verifie': 0,
        'vendeur_id': 1,
    },
    {
        'slug': 'services-pro-cg',
        'nom': 'Services Pro Congo',
        'description': 'Plomberie, électricité, climatisation, peinture — tous vos travaux à domicile.',
        'categorie': 'services',
        'ville': 'pointe-noire',
        'telephone': '06 000 00 03',
        'whatsapp': '06 000 00 03',
        'plan': 'pro',
        'badge_verifie': 1,
        'vendeur_id': 1,
    },
]

for b in nouvelles_boutiques:
    if b['slug'] not in boutiques:
        c.execute("""INSERT INTO boutiques
            (slug, nom, description, categorie_id, ville_id, telephone, whatsapp, plan, badge_verifie, actif, vendeur_id)
            VALUES (?,?,?,?,?,?,?,?,?,1,?)""",
            (b['slug'], b['nom'], b['description'],
             cats.get(b['categorie']), villes.get(b['ville']),
             b['telephone'], b['whatsapp'], b['plan'],
             b['badge_verifie'], b['vendeur_id']))
        boutiques[b['slug']] = c.lastrowid
        print(f"  ✅ Boutique créée : {b['nom']}")
    else:
        print(f"  ⏭️  Boutique déjà existante : {b['nom']}")

conn.commit()

# ── Annonces de démo par catégorie vide ────────────────────────────
annonces = [

    # ÉLECTRONIQUE
    {'titre': 'Télévision Samsung 55 pouces 4K Smart TV',
     'description': 'TV Samsung 55" 4K UHD Smart TV avec WiFi intégré, HDR, Netflix et YouTube. Neuf, garantie 1 an.',
     'prix': 285000, 'prix_type': 'fixe',
     'categorie': 'electronique', 'ville': 'pointe-noire', 'boutique': 'techshop-pnr'},

    {'titre': 'Climatiseur Midea 1.5 CV split reversible',
     'description': 'Climatiseur Midea 12000 BTU split réversible chaud/froid, faible consommation. Livraison et installation possible.',
     'prix': 195000, 'prix_type': 'fixe',
     'categorie': 'electronique', 'ville': 'pointe-noire', 'boutique': 'techshop-pnr'},

    {'titre': 'Groupe électrogène Honda 3.5 KVA',
     'description': 'Groupe électrogène Honda 3500W, silencieux, économique. Idéal maison et bureau. Bon état.',
     'prix': 320000, 'prix_type': 'fixe',
     'categorie': 'electronique', 'ville': 'brazzaville', 'boutique': 'techshop-pnr'},

    # INFORMATIQUE
    {'titre': 'Laptop HP ProBook 450 G8 Core i5 16Go RAM',
     'description': 'Ordinateur portable HP ProBook 450 G8, Core i5-11ème gen, 16Go RAM, SSD 512Go, écran 15.6". Neuf sous emballage.',
     'prix': 380000, 'prix_type': 'fixe',
     'categorie': 'informatique', 'ville': 'pointe-noire', 'boutique': 'techshop-pnr'},

    {'titre': 'Imprimante Canon PIXMA multifonction WiFi',
     'description': 'Canon PIXMA TS3440 multifonction (impression, scan, copie), WiFi, compatible mobile. Neuf avec cartouches.',
     'prix': 65000, 'prix_type': 'fixe',
     'categorie': 'informatique', 'ville': 'brazzaville', 'boutique': 'techshop-pnr'},

    {'titre': 'Disque dur externe 2To Seagate USB 3.0',
     'description': 'Disque dur externe Seagate 2 To, USB 3.0, portable, compatible Windows et Mac. Neuf.',
     'prix': 35000, 'prix_type': 'fixe',
     'categorie': 'informatique', 'ville': 'pointe-noire', 'boutique': 'techshop-pnr'},

    # ALIMENTATION
    {'titre': 'Livraison paniers de légumes frais Brazzaville',
     'description': 'Paniers de légumes frais du marché livrés à domicile à Brazzaville. Tomates, oignons, poivrons, manioc, plantains. Commande minimum 5 000 FCFA.',
     'prix': 5000, 'prix_type': 'fixe',
     'categorie': 'alimentation', 'ville': 'brazzaville', 'boutique': 'saveurs-congo'},

    {'titre': 'Poisson fumé du Congo — vente en gros et détail',
     'description': 'Poisson fumé de qualité, conditionné hygiéniquement. Vente au kilo ou en gros. Livraison possible Brazzaville.',
     'prix': 4500, 'prix_type': 'fixe',
     'categorie': 'alimentation', 'ville': 'brazzaville', 'boutique': 'saveurs-congo'},

    {'titre': 'Huile de palme rouge artisanale 5 litres',
     'description': 'Huile de palme rouge pure, production artisanale, sans additifs. Bidon de 5 litres. Disponible à Brazzaville.',
     'prix': 8000, 'prix_type': 'fixe',
     'categorie': 'alimentation', 'ville': 'brazzaville', 'boutique': 'saveurs-congo'},

    # SERVICES
    {'titre': 'Plombier professionnel — intervention rapide Pointe-Noire',
     'description': 'Plombier qualifié disponible 7j/7 à Pointe-Noire. Fuite, installation, réparation, débouchage. Devis gratuit. Intervention en moins de 2h.',
     'prix': 15000, 'prix_type': 'a-partir-de',
     'categorie': 'services', 'ville': 'pointe-noire', 'boutique': 'services-pro-cg'},

    {'titre': 'Électricien agréé — Installation et dépannage',
     'description': 'Électricien certifié pour installation tableau électrique, dépannage, mise aux normes, câblage maison et bureau. Pointe-Noire et environs.',
     'prix': 20000, 'prix_type': 'a-partir-de',
     'categorie': 'services', 'ville': 'pointe-noire', 'boutique': 'services-pro-cg'},

    {'titre': 'Peinture intérieure et extérieure — Devis gratuit',
     'description': 'Équipe de peintres professionnels pour travaux intérieurs et extérieurs. Maisons, bureaux, appartements. Fourniture peinture incluse sur devis.',
     'prix': 0, 'prix_type': 'sur-devis',
     'categorie': 'services', 'ville': 'pointe-noire', 'boutique': 'services-pro-cg'},

    # EMPLOI
    {'titre': 'Recherche comptable expérimenté — CDI Pointe-Noire',
     'description': 'Entreprise de commerce recherche un(e) comptable avec minimum 3 ans d\'expérience, maîtrise du logiciel SAGE, bonne connaissance fiscalité congolaise. CV à envoyer par WhatsApp.',
     'prix': 0, 'prix_type': 'sur-devis',
     'categorie': 'emploi', 'ville': 'pointe-noire', 'boutique': 'services-pro-cg'},

    {'titre': 'Offre d\'emploi : Technicien informatique Brazzaville',
     'description': 'Société IT recherche technicien informatique (maintenance, réseau, support). Bac+2 minimum, 2 ans d\'expérience. Salaire négociable selon profil.',
     'prix': 0, 'prix_type': 'sur-devis',
     'categorie': 'emploi', 'ville': 'brazzaville', 'boutique': 'techshop-pnr'},

    # LOISIRS & SPORT
    {'titre': 'Vélo VTT 26 pouces 21 vitesses — comme neuf',
     'description': 'VTT adulte 26 pouces, 21 vitesses Shimano, freins à disque, cadre aluminium. Très bon état, utilisé quelques fois. Pointe-Noire.',
     'prix': 55000, 'prix_type': 'fixe',
     'categorie': 'loisirs', 'ville': 'pointe-noire', 'boutique': 'mode-tendance-bzv'},

    {'titre': 'Table de ping-pong pliable avec accessoires',
     'description': 'Table de tennis de table pliable, standard compétition. Inclus 4 raquettes et 12 balles. Bon état. Brazzaville.',
     'prix': 85000, 'prix_type': 'fixe',
     'categorie': 'loisirs', 'ville': 'brazzaville', 'boutique': 'mode-tendance-bzv'},

    # ANIMAUX
    {'titre': 'Chiots Labrador à vendre — 2 mois',
     'description': 'Adorables chiots Labrador Retriever, 2 mois, vaccinés et vermifugés. Parents visibles sur place. Pointe-Noire.',
     'prix': 35000, 'prix_type': 'fixe',
     'categorie': 'animaux', 'ville': 'pointe-noire', 'boutique': 'autres-pnr'},

    {'titre': 'Vente de poules pondeuses — race améliorée',
     'description': 'Poules pondeuses race améliorée, 5-6 mois, entrée en ponte. Lot de 10 minimum. Brazzaville, livraison possible.',
     'prix': 8000, 'prix_type': 'fixe',
     'categorie': 'animaux', 'ville': 'brazzaville', 'boutique': 'saveurs-congo'},

    # LIVRES & EBOOKS
    {'titre': 'Lot de livres scolaires — Lycée Congo programmes officiels',
     'description': 'Lot de manuels scolaires lycée (Terminale et Première) : Maths, Physique, SVT, Histoire-Géo. Programmes officiels Congo. Bon état.',
     'prix': 12000, 'prix_type': 'fixe',
     'categorie': 'livres', 'ville': 'brazzaville', 'boutique': 'services-pro-cg'},

    {'titre': 'Formation en ligne : Créer sa boutique e-commerce',
     'description': 'Ebook + vidéos : Comment créer et gérer sa boutique en ligne au Congo. 80 pages + 5h de vidéos. Livraison par email.',
     'prix': 5000, 'prix_type': 'fixe',
     'categorie': 'livres', 'ville': 'brazzaville', 'boutique': 'techshop-pnr'},

    # MAISON & DÉCO
    {'titre': 'Canapé 3 places + 2 places tissu gris anthracite',
     'description': 'Salon 3+2 places en tissu gris anthracite, très bon état, peu utilisé. Pieds bois naturel. Pointe-Noire, à enlever sur place.',
     'prix': 95000, 'prix_type': 'fixe',
     'categorie': 'maison', 'ville': 'pointe-noire', 'boutique': 'mode-tendance-bzv'},

    # ENFANTS & BÉBÉS
    {'titre': 'Poussette bébé pliable légère — 0 à 36 mois',
     'description': 'Poussette bébé ultra-légère pliable en un geste, avec pare-soleil, panier rangement, ceinture sécurité 5 points. Très bon état.',
     'prix': 25000, 'prix_type': 'fixe',
     'categorie': 'enfants', 'ville': 'pointe-noire', 'boutique': 'mode-tendance-bzv'},
]

# Récupérer boutiques fraîchement créées
boutiques = {r['slug']: r['id'] for r in c.execute("SELECT id, slug FROM boutiques")}

print(f"\n📦 Insertion des annonces de démo...\n")
inseres = 0
ignores = 0

for a in annonces:
    boutique_id = boutiques.get(a.get('boutique'))
    if not boutique_id:
        print(f"  ⚠️  Boutique introuvable : {a.get('boutique')} — annonce ignorée : {a['titre'][:40]}")
        ignores += 1
        continue

    slug = slugify(a['titre'])
    # Vérifier doublon
    existing = c.execute("SELECT id FROM annonces WHERE slug = ?", (slug,)).fetchone()
    if existing:
        print(f"  ⏭️  Déjà existante : {a['titre'][:50]}")
        ignores += 1
        continue

    c.execute("""INSERT INTO annonces
        (slug, titre, description, prix, prix_type, categorie_id, ville_id, boutique_id, statut)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (slug, a['titre'], a['description'], a['prix'], a['prix_type'],
         cats.get(a['categorie']), villes.get(a['ville']),
         boutique_id, 'active'))
    inseres += 1
    print(f"  ✅ {a['titre'][:55]}")

conn.commit()
conn.close()

print(f"\n{'='*55}")
print(f"✅ {inseres} annonces insérées")
print(f"⏭️  {ignores} ignorées (doublons ou boutique manquante)")
print(f"{'='*55}")
print("\n🚀 Rechargez votre site — les annonces sont en ligne !")
EOF