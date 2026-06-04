import os
import re
import uuid
import datetime
import sqlite3
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, abort, session, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash
from database import init_db

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'nexora-kongo-annonces-2026-secret')

init_db()

DB_PATH = os.environ.get('DB_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'marketplace.db'))

PLAN_LIMITS  = {'starter': 5, 'pro': 20, 'premium': 9999, 'business': 9999}
PLANS_TARIFS = {
    'starter':  {'nom': 'Starter',  'prix': 2500,  'annonces': 5,    'photos': 3},
    'pro':      {'nom': 'Pro',      'prix': 6000,  'annonces': 20,   'photos': 8},
    'premium':  {'nom': 'Premium',  'prix': 12000, 'annonces': 9999, 'photos': 20},
    'business': {'nom': 'Business', 'prix': 50000, 'annonces': 9999, 'photos': 30},
}
BOOST_TARIF = 2000
EMPLACEMENTS_PUB = {
    'banniere_top': {'nom': 'Banniere Top',       'format': '680x90px',  'tarif': 25000},
    'sidebar':      {'nom': 'Rectangle Sidebar',  'format': '140x130px', 'tarif': 15000},
    'mid_page':     {'nom': 'Banniere Mid-page',  'format': '680x60px',  'tarif': 10000},
    'sponsorisee':  {'nom': 'Annonce Sponsorisee','format': 'Carte',     'tarif': 8000},
}

# ── Upload config ────────────────────────────────────────────────────
import uuid as _uuid
from PIL import Image as PILImage

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
ALLOWED_EXT   = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
MAX_WIDTH     = 1200
THUMB_SIZE    = (400, 300)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def save_image(file_obj):
    name = f"{_uuid.uuid4().hex}.jpg"
    path = os.path.join(UPLOAD_FOLDER, name)
    img  = PILImage.open(file_obj.stream).convert('RGB')

    # Redimensionner si trop large (image principale)
    if img.width > MAX_WIDTH:
        ratio = MAX_WIDTH / img.width
        img   = img.resize((MAX_WIDTH, int(img.height * ratio)), PILImage.LANCZOS)
    img.save(path, 'JPEG', quality=85, optimize=True)

    # Thumbnail : crop centré exactement 400x300 (ratio 4:3)
    thumb_w, thumb_h = THUMB_SIZE  # 400x300
    tw, th = img.size
    ratio_w = thumb_w / tw
    ratio_h = thumb_h / th
    scale = max(ratio_w, ratio_h)
    new_w = int(tw * scale)
    new_h = int(th * scale)
    img_resized = img.resize((new_w, new_h), PILImage.LANCZOS)
    # Crop centré
    left = (new_w - thumb_w) // 2
    top  = (new_h - thumb_h) // 2
    thumb = img_resized.crop((left, top, left + thumb_w, top + thumb_h))
    thumb_name = f"thumb_{name}"
    thumb.save(os.path.join(UPLOAD_FOLDER, thumb_name), 'JPEG', quality=80)
    return name

# ── Helpers DB ───────────────────────────────────────────────────────
def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def get_base_data():
    db = get_db()
    villes = db.execute('SELECT * FROM villes ORDER BY nom').fetchall()
    categories = db.execute('''
        SELECT c.*, COUNT(a.id) as nb_annonces
        FROM categories c
        LEFT JOIN annonces a ON a.categorie_id = c.id AND a.statut = "active"
        GROUP BY c.id ORDER BY c.ordre
    ''').fetchall()
    try:
        quartiers = db.execute('SELECT * FROM quartiers ORDER BY ville_id, nom').fetchall()
    except Exception:
        quartiers = []
    db.close()
    return villes, categories, quartiers

def slugify(text):
    text = text.lower().strip()
    for a, b in [('a','[aàáâ]'),('e','[eèéê]'),('i','[iîï]'),('o','[oôö]'),('u','[uûü]'),('c','[cç]')]:
        text = re.sub(b, a, text)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-')

def unique_slug(db, table, base):
    slug = base[:80]
    candidate = slug
    i = 1
    while db.execute(f'SELECT id FROM {table} WHERE slug=?', (candidate,)).fetchone():
        candidate = f'{slug}-{i}'
        i += 1
    return candidate

# ── Decorateurs ──────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'vendeur_id' not in session:
            flash('Connectez-vous pour acceder a cette page.', 'error')
            return redirect(url_for('connexion', next=request.path))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'vendeur_id' not in session:
            return redirect(url_for('connexion'))
        db = get_db()
        v = db.execute('SELECT is_admin FROM vendeurs WHERE id=?', (session['vendeur_id'],)).fetchone()
        db.close()
        if not v or not v['is_admin']:
            abort(403)
        return f(*args, **kwargs)
    return decorated

def current_vendeur():
    if 'vendeur_id' not in session:
        return None
    db = get_db()
    v = db.execute('SELECT * FROM vendeurs WHERE id=?', (session['vendeur_id'],)).fetchone()
    db.close()
    return v

# ── Context processors ───────────────────────────────────────────────
@app.context_processor
def inject_user():
    cv = current_vendeur()
    nb_non_lus = 0
    if cv:
        try:
            db = get_db()
            nb_non_lus = db.execute('''
                SELECT COUNT(*) FROM messages m
                JOIN conversations c ON m.conversation_id = c.id
                WHERE (c.destinataire_id=? OR c.expediteur_id=?)
                  AND m.auteur_id != ?
                  AND m.lu = 0
            ''', (cv['id'], cv['id'], cv['id'])).fetchone()[0]
            db.close()
        except Exception:
            pass
    return {'current_vendeur': cv, 'nb_messages_non_lus': nb_non_lus}

@app.context_processor
def inject_pub():
    try:
        return {
            'pub_top':         get_pub('banniere_top'),
            'pub_sidebar':     get_pub('sidebar'),
            'pub_mid':         get_pub('mid_page'),
            'pub_sponsorisee': get_pub('sponsorisee'),
        }
    except Exception:
        return {'pub_top': None, 'pub_sidebar': None, 'pub_mid': None, 'pub_sponsorisee': None}

def get_pub(emplacement):
    try:
        db = get_db()
        today = datetime.date.today().isoformat()
        pub = db.execute(
            'SELECT * FROM publicites WHERE statut="active" AND emplacement=? '
            'AND date_debut<=? AND date_fin>=? ORDER BY RANDOM() LIMIT 1',
            (emplacement, today, today)
        ).fetchone()
        if pub:
            db.execute('UPDATE publicites SET impressions=impressions+1 WHERE id=?', (pub['id'],))
            db.commit()
        db.close()
        return pub
    except Exception:
        return None

# ════════════════════════════════════════════════════════════════════
# ROUTES PUBLIQUES
# ════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    db = get_db()
    # ── Expiration automatique annonces Emploi (30 jours) ──
    db.execute('''UPDATE annonces SET statut="expiree"
        WHERE expire_at IS NOT NULL AND expire_at < datetime("now") AND statut="active"''')
    db.commit()
    villes, categories, quartiers = get_base_data()
    stats = {
        'total_annonces':  db.execute('SELECT COUNT(*) FROM annonces WHERE statut="active"').fetchone()[0],
        'total_boutiques': db.execute('SELECT COUNT(*) FROM boutiques WHERE actif=1').fetchone()[0],
        'total_villes':    db.execute('SELECT COUNT(*) FROM villes').fetchone()[0],
    }
    annonces = db.execute('''
        SELECT a.*, c.icon as cat_icon, v.nom as ville_nom, b.plan as boutique_plan,
               (SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url
        FROM annonces a
        JOIN categories c ON a.categorie_id = c.id
        JOIN villes v ON a.ville_id = v.id
        LEFT JOIN boutiques b ON a.boutique_id = b.id
        WHERE a.statut = "active"
        ORDER BY CASE WHEN b.plan="premium" THEN 0 WHEN b.plan="pro" THEN 1 ELSE 2 END, a.created_at DESC
        LIMIT 8
    ''').fetchall()
    boutiques = db.execute('''
        SELECT b.*, c.nom as cat_nom FROM boutiques b
        JOIN categories c ON b.categorie_id = c.id
        WHERE b.actif = 1
        ORDER BY CASE WHEN b.plan="premium" THEN 0 WHEN b.plan="pro" THEN 1 ELSE 2 END, b.badge_verifie DESC
        LIMIT 8
    ''').fetchall()
    mes_favoris_ids = set()
    if 'vendeur_id' in session:
        rows = db.execute('SELECT annonce_id FROM favoris WHERE vendeur_id=?', (session['vendeur_id'],)).fetchall()
        mes_favoris_ids = {r['annonce_id'] for r in rows}
    # Auto-expirer les bon plans dépassés
    db.execute('''UPDATE annonces SET bon_plan=0, bon_plan_expire=NULL
        WHERE bon_plan=1 AND bon_plan_expire IS NOT NULL AND bon_plan_expire < datetime("now")''')
    db.commit()
    bon_plan = db.execute('''
        SELECT a.*, c.nom as cat_nom, c.icon as cat_icon, v.nom as ville_nom,
               a.bon_plan_expire,
               (SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url
        FROM annonces a
        JOIN categories c ON a.categorie_id=c.id
        JOIN villes v ON a.ville_id=v.id
        JOIN boutiques b ON a.boutique_id=b.id
        WHERE a.bon_plan=1 AND a.statut="active"
          AND b.plan="premium"
          AND (a.bon_plan_expire IS NULL OR a.bon_plan_expire > datetime("now"))
        LIMIT 1
    ''').fetchone()
    db.close()
    return render_template('pages/index.html',
        villes=villes, categories=categories, stats=stats,
        annonces_recentes=annonces, boutiques_vedettes=boutiques,
        mes_favoris_ids=mes_favoris_ids, bon_plan=bon_plan)

@app.route('/recherche')
def recherche():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    q             = request.args.get('q', '').strip()
    ville_slug    = request.args.get('ville', '').strip()
    cat_slug      = request.args.get('categorie', '').strip()
    quartier_slug = request.args.get('quartier', '').strip()
    prix_min      = request.args.get('prix_min', '').strip()
    prix_max      = request.args.get('prix_max', '').strip()
    tri           = request.args.get('tri', 'recent')
    page          = max(1, int(request.args.get('page', 1)))
    per_page      = 12

    ville_nom     = next((v['nom'] for v in villes if v['slug'] == ville_slug), None)
    cat_row       = next((c for c in categories if c['slug'] == cat_slug), None)
    categorie_nom = cat_row['nom'] if cat_row else None
    quartier_row  = next((q2 for q2 in quartiers if q2['slug'] == quartier_slug), None)
    quartier_nom  = quartier_row['nom'] if quartier_row else None

    where, params = ['a.statut = "active"'], []
    if q:
        where.append('(a.titre LIKE ? OR a.description LIKE ?)')
        params += [f'%{q}%', f'%{q}%']
    if ville_slug:
        where.append('v.slug = ?'); params.append(ville_slug)
    if cat_slug:
        where.append('c.slug = ?'); params.append(cat_slug)
    if quartier_slug:
        where.append('qr.slug = ?'); params.append(quartier_slug)
    if prix_min:
        where.append('a.prix >= ?'); params.append(float(prix_min))
    if prix_max:
        where.append('a.prix <= ?'); params.append(float(prix_max))

    order = {
        'recent':    'CASE WHEN b.plan="premium" THEN 0 WHEN b.plan="pro" THEN 1 ELSE 2 END, a.created_at DESC',
        'prix-asc':  'a.prix ASC',
        'prix-desc': 'a.prix DESC',
        'vues':      'a.vues DESC',
    }.get(tri, 'a.created_at DESC')

    base = f'''
        FROM annonces a
        JOIN categories c ON a.categorie_id = c.id
        JOIN villes v ON a.ville_id = v.id
        LEFT JOIN boutiques b ON a.boutique_id = b.id
        LEFT JOIN quartiers qr ON a.quartier_id = qr.id
        WHERE {' AND '.join(where)}
    '''
    total  = db.execute(f'SELECT COUNT(*) {base}', params).fetchone()[0]
    offset = (page - 1) * per_page
    annonces = db.execute(f'''
        SELECT a.*, c.icon as cat_icon, c.slug as cat_slug, v.nom as ville_nom,
               b.plan as boutique_plan, qr.nom as quartier_nom,
               (SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url
        {base} ORDER BY {order} LIMIT ? OFFSET ?
    ''', params + [per_page, offset]).fetchall()
    db.close()
    return render_template('pages/recherche.html',
        villes=villes, categories=categories, quartiers=quartiers,
        annonces=annonces, total=total, page=page, per_page=per_page,
        q=q, ville_slug=ville_slug, ville_nom=ville_nom,
        categorie_slug=cat_slug, categorie_nom=categorie_nom,
        quartier_slug=quartier_slug, quartier_nom=quartier_nom,
        prix_min=prix_min, prix_max=prix_max, tri=tri)

@app.route('/annonce/<slug>')
def annonce(slug):
    db = get_db()
    villes, categories, quartiers = get_base_data()
    db.execute('UPDATE annonces SET vues = vues + 1 WHERE slug = ?', (slug,))
    today = datetime.date.today().isoformat()
    ann_id_row = db.execute('SELECT id FROM annonces WHERE slug=?', (slug,)).fetchone()
    if ann_id_row:
        db.execute('''INSERT INTO vues_journal (annonce_id, date, nb_vues) VALUES (?,?,1)
            ON CONFLICT(annonce_id, date) DO UPDATE SET nb_vues=nb_vues+1''',
            (ann_id_row['id'], today))
    db.commit()
    ann = db.execute('''
        SELECT a.*, c.nom as cat_nom, c.icon as cat_icon, c.slug as cat_slug, v.nom as ville_nom
        FROM annonces a
        JOIN categories c ON a.categorie_id = c.id
        JOIN villes v ON a.ville_id = v.id
        WHERE a.slug = ?
    ''', (slug,)).fetchone()
    if not ann:
        abort(404)
    photos = db.execute('SELECT * FROM photos WHERE annonce_id=? ORDER BY principale DESC', (ann['id'],)).fetchall()
    boutique = db.execute('SELECT * FROM boutiques WHERE id=?', (ann['boutique_id'],)).fetchone() if ann['boutique_id'] else None
    similaires = db.execute('''
        SELECT a.*, c.icon as cat_icon, c.slug as cat_slug, v.nom as ville_nom
        FROM annonces a JOIN categories c ON a.categorie_id=c.id JOIN villes v ON a.ville_id=v.id
        WHERE a.categorie_id=? AND a.slug!=? AND a.statut="active" LIMIT 4
    ''', (ann['categorie_id'], slug)).fetchall()
    est_favori = False
    if 'vendeur_id' in session:
        est_favori = bool(db.execute('SELECT id FROM favoris WHERE vendeur_id=? AND annonce_id=?',
                                     (session['vendeur_id'], ann['id'])).fetchone())
    db.close()
    return render_template('pages/annonce.html', annonce=ann, boutique=boutique,
        similaires=similaires, photos=photos, villes=villes, categories=categories,
        est_favori=est_favori)

@app.route('/boutique/<slug>')
def boutique(slug):
    db = get_db()
    villes, categories, quartiers = get_base_data()
    b = db.execute('''
        SELECT b.*, c.nom as cat_nom, v.nom as ville_nom
        FROM boutiques b JOIN categories c ON b.categorie_id=c.id JOIN villes v ON b.ville_id=v.id
        WHERE b.slug=? AND b.actif=1
    ''', (slug,)).fetchone()
    if not b:
        abort(404)
    annonces_b = db.execute('''
        SELECT a.*, c.icon as cat_icon, v.nom as ville_nom,
               (SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url
        FROM annonces a JOIN categories c ON a.categorie_id=c.id JOIN villes v ON a.ville_id=v.id
        WHERE a.boutique_id=? AND a.statut="active" ORDER BY a.created_at DESC
    ''', (b['id'],)).fetchall()
    stats = {'nb_annonces': len(annonces_b), 'total_vues': sum(a['vues'] for a in annonces_b)}
    avis_list = db.execute('''
        SELECT av.*, v.nom as auteur_nom FROM avis av
        JOIN vendeurs v ON av.auteur_id=v.id
        WHERE av.boutique_id=? ORDER BY av.created_at DESC
    ''', (b['id'],)).fetchall()
    note_moy = round(sum(a['note'] for a in avis_list) / len(avis_list), 1) if avis_list else None
    mon_avis = None
    if 'vendeur_id' in session:
        mon_avis = db.execute('SELECT note FROM avis WHERE auteur_id=? AND boutique_id=?',
                              (session['vendeur_id'], b['id'])).fetchone()
    db.close()
    return render_template('pages/boutique.html', boutique=b, annonces=annonces_b, stats=stats,
        avis_list=avis_list, note_moy=note_moy, mon_avis=mon_avis,
        villes=villes, categories=categories)

@app.route('/boutiques')
def boutiques():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    bouts = db.execute('''
        SELECT b.*, c.nom as cat_nom, COUNT(a.id) as nb_annonces
        FROM boutiques b JOIN categories c ON b.categorie_id=c.id
        LEFT JOIN annonces a ON a.boutique_id=b.id AND a.statut="active"
        WHERE b.actif=1 GROUP BY b.id
        ORDER BY CASE WHEN b.plan="premium" THEN 0 WHEN b.plan="pro" THEN 1 ELSE 2 END, b.badge_verifie DESC
    ''').fetchall()
    db.close()
    return render_template('pages/boutiques.html', boutiques=bouts, villes=villes, categories=categories)

@app.route('/entreprises')
def entreprises():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    entreprises_list = db.execute('''
        SELECT b.*, c.nom as cat_nom, v.nom as ville_nom,
               COUNT(a.id) as nb_annonces,
               ROUND(COALESCE(AVG(av.note), 0), 1) as note_moy,
               COUNT(av.id) as nb_avis
        FROM boutiques b
        JOIN categories c ON b.categorie_id=c.id
        JOIN villes v ON b.ville_id=v.id
        LEFT JOIN annonces a ON a.boutique_id=b.id AND a.statut="active"
        LEFT JOIN avis av ON av.boutique_id=b.id
        WHERE b.actif=1 AND b.is_entreprise=1 AND b.plan IN ("pro","premium")
        GROUP BY b.id
        ORDER BY b.badge_verifie DESC,
                 CASE WHEN b.plan="premium" THEN 0 ELSE 1 END,
                 b.created_at DESC
    ''').fetchall()
    db.close()
    return render_template('pages/entreprises.html',
        entreprises=entreprises_list, villes=villes, categories=categories)

@app.route('/boutique/<slug>/entreprise', methods=['GET', 'POST'])
@login_required
def gerer_profil_entreprise(slug):
    db = get_db()
    b = db.execute('SELECT * FROM boutiques WHERE slug=? AND vendeur_id=?',
                   (slug, session['vendeur_id'])).fetchone()
    if not b:
        db.close(); abort(404)
    if b['plan'] not in ('pro', 'premium'):
        flash("L'espace Entreprise Pro est réservé aux plans Pro et Premium.", 'error')
        db.close()
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        fields = {
            'is_entreprise': 1,
            'secteur':   request.form.get('secteur','').strip()[:100],
            'rccm':      request.form.get('rccm','').strip()[:80],
            'horaires':  request.form.get('horaires','').strip()[:300],
            'site_web':  request.form.get('site_web','').strip()[:200],
            'facebook':  request.form.get('facebook','').strip()[:200],
            'instagram': request.form.get('instagram','').strip()[:200],
        }
        db.execute('''UPDATE boutiques SET is_entreprise=:is_entreprise,
            secteur=:secteur, rccm=:rccm, horaires=:horaires,
            site_web=:site_web, facebook=:facebook, instagram=:instagram
            WHERE slug=?''', (*fields.values(), slug))
        db.commit()
        flash('Profil entreprise mis à jour.', 'success')
        db.close()
        return redirect(url_for('boutique', slug=slug))
    villes, categories, quartiers = get_base_data()
    db.close()
    return render_template('pages/profil_entreprise.html', boutique=b,
                           villes=villes, categories=categories)

@app.route('/annonces')
def annonces():
    return redirect(url_for('recherche'))

@app.route('/categories')
def categories_page():
    villes, categories, quartiers = get_base_data()
    return render_template('pages/recherche.html',
        villes=villes, categories=categories, quartiers=quartiers,
        annonces=[], total=0, page=1, per_page=12,
        q='', ville_slug='', ville_nom=None,
        categorie_slug='', categorie_nom=None,
        quartier_slug='', quartier_nom=None,
        prix_min='', prix_max='', tri='recent')

@app.route('/bon-plan')
def bon_plan():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    db.execute('''UPDATE annonces SET bon_plan=0, bon_plan_expire=NULL
        WHERE bon_plan=1 AND bon_plan_expire IS NOT NULL AND bon_plan_expire < datetime("now")''')
    db.commit()
    annonce_bp = db.execute('''
        SELECT a.*, c.nom as cat_nom, c.icon as cat_icon, v.nom as ville_nom,
               a.bon_plan_expire,
               (SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url
        FROM annonces a
        JOIN categories c ON a.categorie_id=c.id
        JOIN villes v ON a.ville_id=v.id
        JOIN boutiques b ON a.boutique_id=b.id
        WHERE a.bon_plan=1 AND a.statut="active"
          AND b.plan="premium"
          AND (a.bon_plan_expire IS NULL OR a.bon_plan_expire > datetime("now"))
        LIMIT 1
    ''').fetchone()
    db.close()
    return render_template('pages/bon_plan.html', annonce=annonce_bp,
        villes=villes, categories=categories)

@app.route('/contact')
def contact():
    villes, categories, quartiers = get_base_data()
    return render_template('pages/contact.html', villes=villes, categories=categories)

@app.route('/a-propos')
def a_propos():
    villes, categories, quartiers = get_base_data()
    return render_template('pages/a_propos.html', villes=villes, categories=categories)

@app.route('/cgu')
def cgu():
    villes, categories, quartiers = get_base_data()
    return render_template('pages/cgu.html', villes=villes, categories=categories)

# ════════════════════════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════════════════════════

@app.route('/inscription', methods=['GET', 'POST'])
def inscription():
    if 'vendeur_id' in session:
        return redirect(url_for('dashboard'))
    villes, categories, quartiers = get_base_data()
    form = {}
    if request.method == 'POST':
        form = {k: v.strip() for k, v in request.form.items()}
        nom, email = form.get('nom', ''), form.get('email', '').lower()
        telephone  = form.get('telephone', '')
        password, password2 = form.get('password', ''), form.get('password2', '')
        plan = form.get('plan', 'pro')
        errors = []
        if len(nom) < 2:           errors.append('Le nom est trop court.')
        if '@' not in email:        errors.append('Email invalide.')
        if len(telephone) < 8:      errors.append('Numero de telephone invalide.')
        if len(password) < 6:       errors.append('Mot de passe trop court (min. 6 caracteres).')
        if password != password2:   errors.append('Les mots de passe ne correspondent pas.')
        if plan not in PLAN_LIMITS: errors.append('Plan invalide.')
        if not errors:
            db = get_db()
            if db.execute('SELECT id FROM vendeurs WHERE email=?', (email,)).fetchone():
                flash('Email deja utilise. Connectez-vous.', 'error')
                db.close()
            else:
                db.execute('INSERT INTO vendeurs (nom,email,telephone,password_hash) VALUES (?,?,?,?)',
                           (nom, email, telephone, generate_password_hash(password)))
                db.commit()
                v = db.execute('SELECT * FROM vendeurs WHERE email=?', (email,)).fetchone()
                db.close()
                session.update({'vendeur_id': v['id'], 'vendeur_nom': v['nom'], 'vendeur_plan': plan})
                flash(f'Bienvenue {nom} ! Creez votre boutique.', 'success')
                return redirect(url_for('creer_boutique'))
        for e in errors:
            flash(e, 'error')
    return render_template('pages/inscription.html', villes=villes, categories=categories, form=form)

@app.route('/connexion', methods=['GET', 'POST'])
def connexion():
    if 'vendeur_id' in session:
        return redirect(url_for('dashboard'))
    villes, categories, quartiers = get_base_data()
    next_url = request.args.get('next', '')
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        next_url = request.form.get('next', '')
        db = get_db()
        v = db.execute('SELECT * FROM vendeurs WHERE email=?', (email,)).fetchone()
        if v and check_password_hash(v['password_hash'], password):
            b = db.execute('SELECT * FROM boutiques WHERE vendeur_id=?', (v['id'],)).fetchone()
            db.close()
            session.update({
                'vendeur_id':    v['id'],
                'vendeur_nom':   v['nom'],
                'boutique_id':   b['id']   if b else None,
                'boutique_slug': b['slug'] if b else None,
                'is_admin':      v['is_admin'] if 'is_admin' in v.keys() else 0,
            })
            flash(f'Bienvenue {v["nom"]} !', 'success')
            if v['is_admin']:
                return redirect(url_for('admin'))
            return redirect(next_url or url_for('dashboard'))
        db.close()
        flash('Email ou mot de passe incorrect.', 'error')
    return render_template('pages/connexion.html', villes=villes, categories=categories, next=next_url)

@app.route('/deconnexion')
def deconnexion():
    session.clear()
    flash('Vous etes deconnecte.', 'success')
    return redirect(url_for('index'))

# ════════════════════════════════════════════════════════════════════
# BOUTIQUE
# ════════════════════════════════════════════════════════════════════

@app.route('/creer-boutique', methods=['GET', 'POST'])
@login_required
def creer_boutique():
    # Admin n'a pas de boutique — rediriger vers panel admin
    if session.get('is_admin'):
        return redirect(url_for('admin'))
    db = get_db()
    villes, categories, quartiers = get_base_data()
    vendeur = db.execute('SELECT * FROM vendeurs WHERE id=?', (session['vendeur_id'],)).fetchone()
    if db.execute('SELECT id FROM boutiques WHERE vendeur_id=?', (session['vendeur_id'],)).fetchone():
        db.close()
        return redirect(url_for('dashboard'))
    form = {}
    if request.method == 'POST':
        form = {k: v.strip() for k, v in request.form.items()}
        nom      = form.get('nom', '')
        desc     = form.get('description', '')
        cat_id   = form.get('categorie_id', '')
        ville_id = form.get('ville_id', '')
        tel      = form.get('telephone', '')
        wa       = form.get('whatsapp', tel)
        plan     = session.get('vendeur_plan', 'pro')
        errors   = []
        if len(nom) < 2:   errors.append('Nom de boutique trop court.')
        if len(desc) < 20: errors.append('Description trop courte (min. 20 caracteres).')
        if not cat_id:      errors.append('Choisissez une categorie.')
        if not ville_id:    errors.append('Choisissez une ville.')
        if len(tel) < 8:    errors.append('Telephone invalide.')
        if not errors:
            slug = unique_slug(db, 'boutiques', slugify(nom))
            actif_initial = 0 if plan == 'starter' else 1
            db.execute('''INSERT INTO boutiques
                (slug,nom,description,categorie_id,ville_id,telephone,whatsapp,email,plan,vendeur_id,actif)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (slug, nom, desc, cat_id, ville_id, tel, wa, vendeur['email'], plan,
                 session['vendeur_id'], actif_initial))
            db.commit()
            b = db.execute('SELECT * FROM boutiques WHERE slug=?', (slug,)).fetchone()
            db.close()
            session.update({'boutique_id': b['id'], 'boutique_slug': b['slug']})
            if plan == 'starter':
                flash('Boutique creee ! Finalisez votre abonnement Starter pour l activer.', 'success')
                return redirect(url_for('paiement_abonnement', plan='starter'))
            flash('Boutique creee ! Deposez votre premiere annonce.', 'success')
            return redirect(url_for('deposer_annonce'))
        for e in errors:
            flash(e, 'error')
    db.close()
    return render_template('pages/creer_boutique.html',
        villes=villes, categories=categories, vendeur=vendeur, form=form)

# ════════════════════════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════════════════════════

@app.route('/dashboard')
@login_required
def dashboard():
    # Admin redirige vers panel admin
    if session.get('is_admin'):
        return redirect(url_for('admin'))
    db = get_db()
    villes, categories, quartiers = get_base_data()
    vendeur = db.execute('SELECT * FROM vendeurs WHERE id=?', (session['vendeur_id'],)).fetchone()
    b = db.execute('''
        SELECT b.*, c.nom as cat_nom, v.nom as ville_nom
        FROM boutiques b JOIN categories c ON b.categorie_id=c.id JOIN villes v ON b.ville_id=v.id
        WHERE b.vendeur_id=?
    ''', (session['vendeur_id'],)).fetchone()
    if not b:
        db.close()
        return redirect(url_for('creer_boutique'))
    annonces_list = db.execute('''
        SELECT a.*, c.nom as cat_nom, v.nom as ville_nom
        FROM annonces a JOIN categories c ON a.categorie_id=c.id JOIN villes v ON a.ville_id=v.id
        WHERE a.boutique_id=? ORDER BY a.created_at DESC
    ''', (b['id'],)).fetchall()
    limite = PLAN_LIMITS.get(b['plan'], 5)
    nb_actives = sum(1 for a in annonces_list if a['statut'] == 'active')
    stats = {
        'nb_annonces': len(annonces_list),
        'nb_actives':  nb_actives,
        'total_vues':  sum(a['vues'] for a in annonces_list),
        'limite':      limite,
        'restantes':   max(0, limite - nb_actives),
    }
    db.close()
    return render_template('pages/dashboard.html',
        vendeur=vendeur, boutique=b, annonces=annonces_list, stats=stats,
        villes=villes, categories=categories, plans_tarifs=PLANS_TARIFS)

@app.route('/stats')
@login_required
def stats():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    b = db.execute('SELECT * FROM boutiques WHERE vendeur_id=?', (session['vendeur_id'],)).fetchone()
    if not b:
        db.close()
        return redirect(url_for('creer_boutique'))
    annonces_list = db.execute('''
        SELECT a.*, c.nom as cat_nom
        FROM annonces a JOIN categories c ON a.categorie_id=c.id
        WHERE a.boutique_id=? ORDER BY a.vues DESC
    ''', (b['id'],)).fetchall()
    # Vues des 30 derniers jours
    vues_30j = db.execute('''
        SELECT vj.date, SUM(vj.nb_vues) as total
        FROM vues_journal vj
        JOIN annonces a ON vj.annonce_id = a.id
        WHERE a.boutique_id=?
          AND vj.date >= date('now', '-30 days')
        GROUP BY vj.date ORDER BY vj.date
    ''', (b['id'],)).fetchall()
    stats_data = {
        'total_vues':     sum(a['vues'] for a in annonces_list),
        'total_annonces': len(annonces_list),
        'nb_actives':     sum(1 for a in annonces_list if a['statut'] == 'active'),
    }
    db.close()
    return render_template('pages/stats.html',
        boutique=b, annonces=annonces_list, vues_30j=vues_30j, stats=stats_data,
        villes=villes, categories=categories)

# ════════════════════════════════════════════════════════════════════
# ANNONCES
# ════════════════════════════════════════════════════════════════════

@app.route('/deposer', methods=['GET', 'POST'])
@login_required
def deposer():
    return redirect(url_for('deposer_annonce'))

@app.route('/deposer-annonce', methods=['GET', 'POST'])
@login_required
def deposer_annonce():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    b = db.execute('SELECT * FROM boutiques WHERE vendeur_id=?', (session['vendeur_id'],)).fetchone()
    if not b:
        db.close()
        flash("Creez d abord votre boutique.", 'error')
        return redirect(url_for('creer_boutique'))
    if not b['actif']:
        db.close()
        flash("Activez votre boutique en finalisant votre paiement.", 'error')
        return redirect(url_for('paiement_abonnement', plan=b['plan']))
    nb = db.execute('SELECT COUNT(*) FROM annonces WHERE boutique_id=? AND statut="active"', (b['id'],)).fetchone()[0]
    limite    = PLAN_LIMITS.get(b['plan'], 5)
    restantes = max(0, limite - nb)
    plan_photos = {'starter': 3, 'pro': 8, 'premium': 20, 'business': 30}
    max_photos  = plan_photos.get(b['plan'], 3)
    form = {}
    if request.method == 'POST':
        form = {k: v.strip() for k, v in request.form.items() if isinstance(v, str)}
        titre       = form.get('titre', '')
        desc        = form.get('description', '')
        prix        = float(form.get('prix', '0') or 0)
        prix_type   = form.get('prix_type', 'fixe')
        cat_id      = form.get('categorie_id', str(b['categorie_id']))
        ville_id    = form.get('ville_id', str(b['ville_id']))
        quartier_id = form.get('quartier_id') or None
        files       = request.files.getlist('photos')
        errors = []
        # Champs spécifiques Emploi
        emploi_type    = form.get('emploi_type', '') or None
        emploi_secteur = form.get('emploi_secteur', '') or None
        emploi_salaire = form.get('emploi_salaire', '') or None
        # Vérifier si catégorie emploi
        cat_emploi = db.execute('SELECT id FROM categories WHERE slug="emploi"').fetchone()
        is_emploi = cat_emploi and str(cat_id) == str(cat_emploi['id'])
        if is_emploi:
            if not emploi_type:    errors.append('Précisez si c\'est une offre ou une recherche d\'emploi.')
            if not emploi_secteur: errors.append('Le secteur d\'activité est obligatoire pour une annonce Emploi.')
        if len(titre) < 5:  errors.append('Titre trop court (min. 5 caracteres).')
        if len(desc) < 20:  errors.append('Description trop courte (min. 20 caracteres).')
        if not cat_id:       errors.append('Categorie manquante.')
        if not ville_id:     errors.append('Ville manquante.')
        if restantes <= 0:   errors.append(f'Limite atteinte ({limite} annonces). Passez au plan superieur.')
        valid_files = [f for f in files if f and f.filename and allowed_file(f.filename)]
        # Limite photos : 2 max pour Emploi
        max_photos_emploi = 2 if is_emploi else max_photos
        if len(valid_files) > max_photos_emploi:
            errors.append(f'Maximum {max_photos_emploi} photos pour les annonces Emploi.')
        if not errors:
            slug = unique_slug(db, 'annonces', slugify(titre))
            # Expiration 30 jours pour Emploi
            expire_at = None
            if is_emploi:
                import datetime
                expire_at = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
            db.execute('''INSERT INTO annonces
                (slug,titre,description,prix,prix_type,categorie_id,ville_id,boutique_id,quartier_id,
                 emploi_type,emploi_secteur,emploi_salaire,expire_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (slug, titre, desc, prix, prix_type, cat_id, ville_id, b['id'], quartier_id,
                 emploi_type, emploi_secteur, emploi_salaire, expire_at))
            db.commit()
            ann_id = db.execute('SELECT id FROM annonces WHERE slug=?', (slug,)).fetchone()['id']
            for i, f in enumerate(valid_files[:max_photos]):
                try:
                    fname = save_image(f)
                    db.execute('INSERT INTO photos (annonce_id, url, principale) VALUES (?,?,?)',
                               (ann_id, fname, 1 if i == 0 else 0))
                except Exception as e:
                    print(f'Photo error: {e}')
            db.commit()
            db.close()
            flash('Annonce publiee avec succes !', 'success')
            return redirect(url_for('dashboard'))
        for e in errors:
            flash(e, 'error')
    db.close()
    return render_template('pages/deposer_annonce.html',
        villes=villes, categories=categories, quartiers=quartiers, boutique=b,
        annonces_restantes=restantes, max_photos=max_photos, form=form)

@app.route('/modifier-annonce/<slug>', methods=['GET', 'POST'])
@login_required
def modifier_annonce(slug):
    db = get_db()
    villes, categories, quartiers = get_base_data()
    v = db.execute('SELECT is_admin FROM vendeurs WHERE id=?', (session['vendeur_id'],)).fetchone()
    is_admin = v and v['is_admin']
    if is_admin:
        a = db.execute('SELECT a.* FROM annonces a WHERE a.slug=?', (slug,)).fetchone()
        if not a:
            db.close(); abort(404)
        b = db.execute('SELECT * FROM boutiques WHERE id=?', (a['boutique_id'],)).fetchone()
    else:
        b = db.execute('SELECT * FROM boutiques WHERE vendeur_id=?', (session['vendeur_id'],)).fetchone()
        if not b:
            db.close(); return redirect(url_for('dashboard'))
        a = db.execute('SELECT a.* FROM annonces a WHERE a.slug=? AND a.boutique_id=?', (slug, b['id'])).fetchone()
    if not a:
        db.close(); abort(404)
    plan_photos = {'starter': 3, 'pro': 8, 'premium': 20, 'business': 30}
    max_photos  = plan_photos.get(b['plan'], 3)
    photos      = db.execute('SELECT * FROM photos WHERE annonce_id=? ORDER BY principale DESC', (a['id'],)).fetchall()
    errors = []
    if request.method == 'POST':
        titre       = request.form.get('titre', '').strip()
        desc        = request.form.get('description', '').strip()
        prix        = float(request.form.get('prix', '0') or 0)
        prix_type   = request.form.get('prix_type', 'fixe')
        cat_id      = request.form.get('categorie_id', str(a['categorie_id']))
        ville_id    = request.form.get('ville_id', str(a['ville_id']))
        quartier_id = request.form.get('quartier_id') or None
        suppr_ids   = request.form.getlist('supprimer_photo')
        new_files   = request.files.getlist('photos')
        if len(titre) < 5:  errors.append('Titre trop court.')
        if len(desc) < 20:  errors.append('Description trop courte.')
        if not errors:
            db.execute('''UPDATE annonces SET titre=?, description=?, prix=?, prix_type=?,
                categorie_id=?, ville_id=?, quartier_id=? WHERE id=?''',
                (titre, desc, prix, prix_type, cat_id, ville_id, quartier_id, a['id']))
            for pid in suppr_ids:
                db.execute('DELETE FROM photos WHERE id=? AND annonce_id=?', (pid, a['id']))
            nb_act = db.execute('SELECT COUNT(*) FROM photos WHERE annonce_id=?', (a['id'],)).fetchone()[0]
            valid_files = [f for f in new_files if f and f.filename and allowed_file(f.filename)]
            places = max(0, max_photos - nb_act)
            for f in valid_files[:places]:
                try:
                    fname = save_image(f)
                    db.execute('INSERT INTO photos (annonce_id, url, principale) VALUES (?,?,?)',
                               (a['id'], fname, 1 if nb_act == 0 else 0))
                    nb_act += 1
                except Exception as e:
                    print(f'Photo error: {e}')
            db.commit()
            db.close()
            flash('Annonce modifiee avec succes !', 'success')
            return redirect(url_for('admin') if is_admin else url_for('dashboard'))
        for e in errors:
            flash(e, 'error')
    db.close()
    return render_template('pages/modifier_annonce.html',
        a=a, b=b, villes=villes, categories=categories, quartiers=quartiers,
        photos=photos, max_photos=max_photos, errors=errors)

@app.route('/renouveler-annonce/<slug>', methods=['POST'])
@login_required
def renouveler_annonce(slug):
    db = get_db()
    b = db.execute('SELECT id FROM boutiques WHERE vendeur_id=?', (session['vendeur_id'],)).fetchone()
    if not b:
        db.close(); return redirect(url_for('dashboard'))
    a = db.execute('SELECT id, renewed_at FROM annonces WHERE slug=? AND boutique_id=?', (slug, b['id'])).fetchone()
    if not a:
        db.close(); abort(404)
    if a['renewed_at']:
        last = datetime.datetime.fromisoformat(a['renewed_at'])
        if (datetime.datetime.now() - last).total_seconds() < 86400:
            db.close()
            flash('Vous pouvez renouveler cette annonce une seule fois toutes les 24h.', 'error')
            return redirect(url_for('dashboard'))
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute('UPDATE annonces SET created_at=?, renewed_at=? WHERE id=?', (now, now, a['id']))
    db.commit()
    db.close()
    flash('Annonce remise en avant avec succes !', 'success')
    return redirect(url_for('dashboard'))

@app.route('/supprimer-annonce/<slug>')
@login_required
def supprimer_annonce(slug):
    db = get_db()
    b = db.execute('SELECT id FROM boutiques WHERE vendeur_id=?', (session['vendeur_id'],)).fetchone()
    if b:
        db.execute('UPDATE annonces SET statut="supprime" WHERE slug=? AND boutique_id=?', (slug, b['id']))
        db.commit()
        flash('Annonce supprimee.', 'success')
    db.close()
    return redirect(url_for('dashboard'))

# ════════════════════════════════════════════════════════════════════
# FAVORIS
# ════════════════════════════════════════════════════════════════════

@app.route('/favori/<int:annonce_id>', methods=['POST'])
@login_required
def toggle_favori(annonce_id):
    db = get_db()
    existing = db.execute('SELECT id FROM favoris WHERE vendeur_id=? AND annonce_id=?',
                          (session['vendeur_id'], annonce_id)).fetchone()
    if existing:
        db.execute('DELETE FROM favoris WHERE vendeur_id=? AND annonce_id=?',
                   (session['vendeur_id'], annonce_id))
        action = 'retire'
    else:
        db.execute('INSERT OR IGNORE INTO favoris (vendeur_id, annonce_id) VALUES (?,?)',
                   (session['vendeur_id'], annonce_id))
        action = 'ajoute'
    db.commit()
    db.close()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'action': action})
    flash('Favori mis a jour.', 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/mes-favoris')
@login_required
def mes_favoris():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    favoris = db.execute('''
        SELECT a.*, c.icon as cat_icon, c.slug as cat_slug, v.nom as ville_nom,
               (SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url
        FROM favoris f
        JOIN annonces a ON f.annonce_id = a.id
        JOIN categories c ON a.categorie_id = c.id
        JOIN villes v ON a.ville_id = v.id
        WHERE f.vendeur_id=? AND a.statut="active"
        ORDER BY f.created_at DESC
    ''', (session['vendeur_id'],)).fetchall()
    db.close()
    return render_template('pages/mes_favoris.html', favoris=favoris,
        villes=villes, categories=categories)

# ════════════════════════════════════════════════════════════════════
# MESSAGERIE
# ════════════════════════════════════════════════════════════════════

@app.route('/messages')
@login_required
def messagerie():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    convs = db.execute('''
        SELECT c.*,
               a.titre as annonce_titre, a.slug as annonce_slug,
               exped.nom as expediteur_nom, dest.nom as destinataire_nom,
               (SELECT contenu FROM messages WHERE conversation_id=c.id ORDER BY created_at DESC LIMIT 1) as dernier_msg,
               (SELECT created_at FROM messages WHERE conversation_id=c.id ORDER BY created_at DESC LIMIT 1) as dernier_msg_at,
               (SELECT COUNT(*) FROM messages WHERE conversation_id=c.id AND auteur_id != ? AND lu=0) as nb_non_lus
        FROM conversations c
        JOIN annonces a ON c.annonce_id = a.id
        JOIN vendeurs exped ON c.expediteur_id = exped.id
        JOIN vendeurs dest  ON c.destinataire_id = dest.id
        WHERE c.expediteur_id=? OR c.destinataire_id=?
        ORDER BY dernier_msg_at DESC
    ''', (session['vendeur_id'], session['vendeur_id'], session['vendeur_id'])).fetchall()
    db.close()
    return render_template('pages/messagerie.html', conversations=convs,
        villes=villes, categories=categories)

@app.route('/messages/<int:conv_id>', methods=['GET', 'POST'])
@login_required
def conversation(conv_id):
    db = get_db()
    villes, categories, quartiers = get_base_data()
    conv = db.execute('''
        SELECT c.*, a.titre as annonce_titre, a.slug as annonce_slug,
               exped.nom as expediteur_nom, dest.nom as destinataire_nom
        FROM conversations c
        JOIN annonces a ON c.annonce_id = a.id
        JOIN vendeurs exped ON c.expediteur_id = exped.id
        JOIN vendeurs dest  ON c.destinataire_id = dest.id
        WHERE c.id=? AND (c.expediteur_id=? OR c.destinataire_id=?)
    ''', (conv_id, session['vendeur_id'], session['vendeur_id'])).fetchone()
    if not conv:
        db.close(); abort(404)
    # Marquer comme lus
    db.execute('UPDATE messages SET lu=1 WHERE conversation_id=? AND auteur_id != ?',
               (conv_id, session['vendeur_id']))
    db.commit()
    if request.method == 'POST':
        contenu = request.form.get('contenu', '').strip()
        if contenu:
            db.execute('INSERT INTO messages (conversation_id, auteur_id, contenu) VALUES (?,?,?)',
                       (conv_id, session['vendeur_id'], contenu))
            db.execute('UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?', (conv_id,))
            db.commit()
            flash('Message envoye.', 'success')
        return redirect(url_for('conversation', conv_id=conv_id))
    msgs = db.execute('''
        SELECT m.*, v.nom as auteur_nom FROM messages m
        JOIN vendeurs v ON m.auteur_id = v.id
        WHERE m.conversation_id=? ORDER BY m.created_at ASC
    ''', (conv_id,)).fetchall()
    db.close()
    return render_template('pages/conversation.html', conversation=conv, messages=msgs,
        villes=villes, categories=categories)

@app.route('/messages/contacter/<int:annonce_id>', methods=['GET', 'POST'])
@login_required
def contacter(annonce_id):
    db = get_db()
    ann = db.execute('''
        SELECT a.*, b.vendeur_id as proprietaire_id FROM annonces a
        JOIN boutiques b ON a.boutique_id = b.id
        WHERE a.id=?
    ''', (annonce_id,)).fetchone()
    if not ann:
        db.close(); abort(404)
    if ann['proprietaire_id'] == session['vendeur_id']:
        db.close()
        flash("Vous ne pouvez pas vous contacter vous-meme.", 'error')
        return redirect(url_for('annonce', slug=ann['slug']))
    # Verifier si conversation existante
    existing = db.execute('''
        SELECT id FROM conversations
        WHERE annonce_id=? AND expediteur_id=? AND destinataire_id=?
    ''', (annonce_id, session['vendeur_id'], ann['proprietaire_id'])).fetchone()
    if existing:
        db.close()
        return redirect(url_for('conversation', conv_id=existing['id']))
    if request.method == 'POST':
        contenu = request.form.get('contenu', '').strip()
        if contenu:
            db.execute('''INSERT INTO conversations (annonce_id, expediteur_id, destinataire_id)
                VALUES (?,?,?)''', (annonce_id, session['vendeur_id'], ann['proprietaire_id']))
            db.commit()
            conv_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
            db.execute('INSERT INTO messages (conversation_id, auteur_id, contenu) VALUES (?,?,?)',
                       (conv_id, session['vendeur_id'], contenu))
            db.commit()
            db.close()
            flash('Message envoye !', 'success')
            return redirect(url_for('conversation', conv_id=conv_id))
    villes, categories, quartiers = get_base_data()
    db.close()
    return render_template('pages/contacter.html', annonce=ann,
        villes=villes, categories=categories)

# ════════════════════════════════════════════════════════════════════
# ALERTES
# ════════════════════════════════════════════════════════════════════

@app.route('/alertes')
@login_required
def alertes():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    mes_alertes = db.execute('''
        SELECT al.*, c.nom as cat_nom, v.nom as ville_nom
        FROM alertes al
        LEFT JOIN categories c ON al.categorie_id = c.id
        LEFT JOIN villes v ON al.ville_id = v.id
        WHERE al.vendeur_id=? ORDER BY al.created_at DESC
    ''', (session['vendeur_id'],)).fetchall()
    db.close()
    return render_template('pages/alertes.html', alertes=mes_alertes,
        villes=villes, categories=categories)

@app.route('/alertes/creer', methods=['GET', 'POST'])
@login_required
def creer_alerte():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    if request.method == 'POST':
        nom        = request.form.get('nom', '').strip()
        cat_id     = request.form.get('categorie_id') or None
        ville_id   = request.form.get('ville_id') or None
        prix_min   = request.form.get('prix_min') or None
        prix_max   = request.form.get('prix_max') or None
        mots_cles  = request.form.get('mots_cles', '').strip() or None
        if nom:
            db.execute('''INSERT INTO alertes
                (vendeur_id, nom, categorie_id, ville_id, prix_min, prix_max, mots_cles)
                VALUES (?,?,?,?,?,?,?)''',
                (session['vendeur_id'], nom, cat_id, ville_id, prix_min, prix_max, mots_cles))
            db.commit()
            db.close()
            flash('Alerte creee avec succes !', 'success')
            return redirect(url_for('alertes'))
        flash('Donnez un nom a votre alerte.', 'error')
    db.close()
    return render_template('pages/alertes.html', alertes=[],
        villes=villes, categories=categories, creer=True)

@app.route('/alertes/depuis-recherche')
@login_required
def alerte_depuis_recherche():
    db = get_db()
    q        = request.args.get('q', '').strip()
    ville_id = request.args.get('ville_id') or None
    cat_id   = request.args.get('cat_id') or None
    nom      = f"Alerte : {q or 'Toutes annonces'}"
    db.execute('''INSERT INTO alertes
        (vendeur_id, nom, categorie_id, ville_id, mots_cles)
        VALUES (?,?,?,?,?)''',
        (session['vendeur_id'], nom, cat_id, ville_id, q or None))
    db.commit()
    db.close()
    flash('Alerte creee ! Vous serez notifie des nouvelles annonces.', 'success')
    return redirect(url_for('alertes'))

@app.route('/alertes/<int:alerte_id>/supprimer', methods=['POST'])
@login_required
def supprimer_alerte(alerte_id):
    db = get_db()
    db.execute('DELETE FROM alertes WHERE id=? AND vendeur_id=?', (alerte_id, session['vendeur_id']))
    db.commit()
    db.close()
    flash('Alerte supprimee.', 'success')
    return redirect(url_for('alertes'))

# ════════════════════════════════════════════════════════════════════
# PAIEMENTS
# ════════════════════════════════════════════════════════════════════

@app.route('/paiement/abonnement/<plan>', methods=['GET'])
@login_required
def paiement_abonnement(plan):
    if plan not in PLANS_TARIFS:
        abort(404)
    db = get_db()
    b = db.execute('SELECT * FROM boutiques WHERE vendeur_id=?', (session['vendeur_id'],)).fetchone()
    db.close()
    if not b:
        return redirect(url_for('creer_boutique'))
    tarif = PLANS_TARIFS[plan]
    return render_template('pages/paiement.html',
        type='abonnement', plan=plan, tarif=tarif, boutique=b,
        montant=tarif['prix'],
        description=f"Abonnement {tarif['nom']} - {tarif['prix']:,} FCFA/mois")

@app.route('/paiement/upgrade/<plan>', methods=['GET'])
@login_required
def paiement_upgrade(plan):
    if plan not in PLANS_TARIFS:
        abort(404)
    db = get_db()
    b = db.execute('SELECT * FROM boutiques WHERE vendeur_id=?', (session['vendeur_id'],)).fetchone()
    db.close()
    if not b:
        flash("Creez d abord votre boutique.", 'error')
        return redirect(url_for('creer_boutique'))
    tarif = PLANS_TARIFS[plan]
    return render_template('pages/paiement.html',
        type='upgrade', plan=plan, tarif=tarif, boutique=b,
        montant=tarif['prix'], description=f"Upgrade vers plan {tarif['nom']}")

@app.route('/paiement/boost/<int:annonce_id>', methods=['GET'])
@login_required
def paiement_boost(annonce_id):
    db = get_db()
    a = db.execute('''SELECT a.*, b.vendeur_id FROM annonces a
        JOIN boutiques b ON a.boutique_id=b.id WHERE a.id=?''', (annonce_id,)).fetchone()
    db.close()
    if not a or a['vendeur_id'] != session['vendeur_id']:
        abort(403)
    return render_template('pages/paiement.html',
        type='boost', annonce=a, montant=BOOST_TARIF,
        description=f"Boost annonce : {a['titre'][:40]}")

@app.route('/paiement/initier', methods=['POST'])
@login_required
def paiement_initier():
    operateur  = request.form.get('operateur', '')
    telephone  = request.form.get('telephone', '').strip()
    type_pmt   = request.form.get('type', '')
    montant    = float(request.form.get('montant', 0))
    plan_cible = request.form.get('plan', None)
    annonce_id = request.form.get('annonce_id', None)
    if operateur not in ('mtn', 'airtel'):
        flash('Operateur invalide.', 'error')
        return redirect(url_for('dashboard'))
    if not telephone or len(telephone) < 8:
        flash('Numero invalide.', 'error')
        return redirect(url_for('dashboard'))
    db = get_db()
    b = db.execute('SELECT * FROM boutiques WHERE vendeur_id=?', (session['vendeur_id'],)).fetchone()
    ref = 'KA-' + uuid.uuid4().hex[:8].upper()
    db.execute('''INSERT INTO paiements
        (reference,vendeur_id,boutique_id,annonce_id,type,montant,operateur,telephone,statut,plan_cible)
        VALUES (?,?,?,?,?,?,?,?,?,?)''',
        (ref, session['vendeur_id'], b['id'] if b else None, annonce_id,
         type_pmt, montant, operateur, telephone, 'en_attente', plan_cible))
    db.commit()
    db.close()
    return render_template('pages/paiement_attente.html',
        reference=ref, operateur=operateur, telephone=telephone,
        montant=montant, type_pmt=type_pmt, plan_cible=plan_cible, annonce_id=annonce_id)

@app.route('/paiement/confirmer/<reference>', methods=['POST'])
@login_required
def paiement_confirmer(reference):
    db = get_db()
    p = db.execute('SELECT * FROM paiements WHERE reference=? AND vendeur_id=?',
                   (reference, session['vendeur_id'])).fetchone()
    if not p or p['statut'] != 'en_attente':
        db.close()
        flash('Paiement introuvable.', 'error')
        return redirect(url_for('dashboard'))
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute('UPDATE paiements SET statut="confirme", confirmed_at=? WHERE reference=?', (now, reference))
    if p['type'] in ('upgrade', 'abonnement') and p['plan_cible']:
        if p['plan_cible'] == 'business':
            db.execute('UPDATE boutiques SET plan=?, actif=1, is_entreprise=1, badge_verifie=1 WHERE vendeur_id=?',
                       (p['plan_cible'], session['vendeur_id']))
        else:
            db.execute('UPDATE boutiques SET plan=?, actif=1 WHERE vendeur_id=?',
                       (p['plan_cible'], session['vendeur_id']))
    elif p['type'] == 'boost' and p['annonce_id']:
        db.execute('UPDATE annonces SET statut="boosted" WHERE id=? AND boutique_id=?',
                   (p['annonce_id'], p['boutique_id']))
    db.commit()
    db.close()
    flash('Paiement confirme !', 'success')
    return redirect(url_for('paiement_succes', reference=reference))

@app.route('/paiement/succes/<reference>')
@login_required
def paiement_succes(reference):
    db = get_db()
    p = db.execute('SELECT * FROM paiements WHERE reference=?', (reference,)).fetchone()
    db.close()
    if not p:
        abort(404)
    return render_template('pages/paiement_succes.html', p=p, plans_tarifs=PLANS_TARIFS)

# ════════════════════════════════════════════════════════════════════
# PUBLICITES
# ════════════════════════════════════════════════════════════════════

@app.route('/pub/clic/<int:pub_id>')
def pub_clic(pub_id):
    db = get_db()
    p = db.execute('SELECT * FROM publicites WHERE id=?', (pub_id,)).fetchone()
    if p:
        db.execute('UPDATE publicites SET clics=clics+1 WHERE id=?', (pub_id,))
        db.commit()
        lien = p['lien']
        db.close()
        return redirect(lien)
    db.close()
    return redirect(url_for('index'))

# ════════════════════════════════════════════════════════════════════
# ADMIN
# ════════════════════════════════════════════════════════════════════

@app.route('/admin')
@admin_required
def admin():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    stats = {
        'nb_vendeurs':   db.execute('SELECT COUNT(*) FROM vendeurs WHERE is_admin=0').fetchone()[0],
        'nb_boutiques':  db.execute('SELECT COUNT(*) FROM boutiques').fetchone()[0],
        'nb_annonces':   db.execute('SELECT COUNT(*) FROM annonces WHERE statut="active"').fetchone()[0],
        'nb_paiements':  db.execute('SELECT COUNT(*) FROM paiements WHERE statut="confirme"').fetchone()[0],
        'ca_total':      db.execute('SELECT COALESCE(SUM(montant),0) FROM paiements WHERE statut="confirme"').fetchone()[0],
        'nb_signalements': db.execute('SELECT COUNT(DISTINCT annonce_id) FROM signalements WHERE annonce_id IN (SELECT id FROM annonces WHERE statut="masquee")').fetchone()[0],
        'nb_pro':        db.execute('SELECT COUNT(*) FROM boutiques WHERE plan="pro"').fetchone()[0],
        'nb_premium':    db.execute('SELECT COUNT(*) FROM boutiques WHERE plan="premium"').fetchone()[0],
        'nb_business':   db.execute('SELECT COUNT(*) FROM boutiques WHERE plan="business"').fetchone()[0],
    }
    vendeurs = db.execute('''
        SELECT v.*, COUNT(b.id) as nb_boutiques
        FROM vendeurs v LEFT JOIN boutiques b ON b.vendeur_id=v.id
        WHERE v.is_admin=0 GROUP BY v.id ORDER BY v.created_at DESC LIMIT 20
    ''').fetchall()
    boutiques_all = db.execute('''
        SELECT b.*, v.nom as vendeur_nom, v.email as vendeur_email,
               COUNT(av.id) as nb_avis,
               ROUND(COALESCE(AVG(av.note), 0), 1) as note_moy
        FROM boutiques b
        JOIN vendeurs v ON b.vendeur_id=v.id
        LEFT JOIN avis av ON av.boutique_id=b.id
        GROUP BY b.id
        ORDER BY
            CASE WHEN COUNT(av.id) >= 5 AND AVG(av.note) < 2.5 THEN 0
                 WHEN COUNT(av.id) >= 3 AND AVG(av.note) < 3.0 THEN 1
                 ELSE 2 END,
            b.created_at DESC
        LIMIT 50
    ''').fetchall()
    annonces_all = db.execute('''
        SELECT a.*, c.nom as cat_nom, v2.nom as ville_nom, b.nom as boutique_nom
        FROM annonces a JOIN categories c ON a.categorie_id=c.id
        JOIN villes v2 ON a.ville_id=v2.id JOIN boutiques b ON a.boutique_id=b.id
        ORDER BY a.created_at DESC LIMIT 30
    ''').fetchall()
    paiements_all = db.execute('''
        SELECT p.*, v.nom as vendeur_nom, b.nom as boutique_nom
        FROM paiements p JOIN vendeurs v ON p.vendeur_id=v.id
        LEFT JOIN boutiques b ON p.boutique_id=b.id
        ORDER BY p.created_at DESC LIMIT 20
    ''').fetchall()
    db.close()
    return render_template('pages/admin.html', stats=stats, vendeurs=vendeurs,
        boutiques=boutiques_all, annonces=annonces_all, paiements=paiements_all,
        villes=villes, categories=categories)

@app.route('/admin/annonce/<slug>/statut', methods=['POST'])
@admin_required
def admin_annonce_statut(slug):
    statut = request.form.get('statut', 'active')
    db = get_db()
    db.execute('UPDATE annonces SET statut=? WHERE slug=?', (statut, slug))
    db.commit()
    db.close()
    flash(f'Annonce mise a jour : {statut}', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/paiement/<reference>/confirmer', methods=['POST'])
@admin_required
def admin_paiement_confirmer(reference):
    db = get_db()
    p = db.execute('SELECT * FROM paiements WHERE reference=?', (reference,)).fetchone()
    if p and p['statut'] == 'en_attente':
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.execute('UPDATE paiements SET statut="confirme", confirmed_at=? WHERE reference=?', (now, reference))
        if p['type'] in ('upgrade', 'abonnement') and p['plan_cible']:
            if p['plan_cible'] == 'business':
                db.execute('UPDATE boutiques SET plan=?, actif=1, is_entreprise=1, badge_verifie=1 WHERE vendeur_id=?',
                           (p['plan_cible'], p['vendeur_id']))
            else:
                db.execute('UPDATE boutiques SET plan=?, actif=1 WHERE vendeur_id=?',
                           (p['plan_cible'], p['vendeur_id']))
        db.commit()
        flash('Paiement confirme par admin.', 'success')
    db.close()
    return redirect(url_for('admin'))

@app.route('/admin/boutique/<int:boutique_id>/set-plan', methods=['POST'])
@admin_required
def admin_boutique_set_plan(boutique_id):
    plan = request.form.get('plan', 'starter')
    if plan not in PLANS_TARIFS:
        flash('Plan invalide.', 'error')
        return redirect(url_for('admin') + '#boutiques')
    db = get_db()
    extra = ''
    if plan == 'business':
        extra = ', is_entreprise=1, badge_verifie=1'
    db.execute(f'UPDATE boutiques SET plan=?, actif=1{extra} WHERE id=?', (plan, boutique_id))
    db.commit()
    db.close()
    flash(f'Plan mis à jour : {plan}.', 'success')
    return redirect(url_for('admin') + '#boutiques')

@app.route('/admin/boutique/<int:boutique_id>/toggle-badge', methods=['POST'])
@admin_required
def admin_boutique_toggle_badge(boutique_id):
    db = get_db()
    b = db.execute('SELECT badge_verifie FROM boutiques WHERE id=?', (boutique_id,)).fetchone()
    if b:
        nouveau = 0 if b['badge_verifie'] else 1
        db.execute('UPDATE boutiques SET badge_verifie=? WHERE id=?', (nouveau, boutique_id))
        db.commit()
        flash('Badge mis à jour.', 'success')
    db.close()
    return redirect(url_for('admin') + '#boutiques')

@app.route('/admin/vendeur/<int:vendeur_id>/toggle', methods=['POST'])
@admin_required
def admin_vendeur_toggle(vendeur_id):
    db = get_db()
    v = db.execute('SELECT actif FROM vendeurs WHERE id=?', (vendeur_id,)).fetchone()
    if v:
        db.execute('UPDATE vendeurs SET actif=? WHERE id=?', (0 if v['actif'] else 1, vendeur_id))
        db.commit()
    db.close()
    flash('Vendeur mis a jour.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/publicites')
@admin_required
def admin_publicites():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    pubs = db.execute('SELECT * FROM publicites ORDER BY created_at DESC').fetchall()
    db.close()
    return render_template('pages/admin_publicites.html', publicites=pubs,
        emplacements=EMPLACEMENTS_PUB, villes=villes, categories=categories)

@app.route('/admin/publicites/ajouter', methods=['GET', 'POST'])
@admin_required
def admin_pub_ajouter():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    if request.method == 'POST':
        annonceur  = request.form.get('annonceur', '').strip()
        image_url  = request.form.get('image_url', '').strip()
        lien       = request.form.get('lien', '').strip()
        titre      = request.form.get('titre', '').strip()
        emplacement= request.form.get('emplacement', 'banniere_top')
        date_debut = request.form.get('date_debut', '')
        date_fin   = request.form.get('date_fin', '')
        montant    = float(request.form.get('montant', 0) or 0)
        if annonceur and image_url and lien and date_debut and date_fin:
            db.execute('''INSERT INTO publicites
                (annonceur, image_url, lien, titre, emplacement, date_debut, date_fin, montant)
                VALUES (?,?,?,?,?,?,?,?)''',
                (annonceur, image_url, lien, titre, emplacement, date_debut, date_fin, montant))
            db.commit()
            db.close()
            flash('Publicite ajoutee avec succes !', 'success')
            return redirect(url_for('admin_publicites'))
        flash('Tous les champs obligatoires doivent etre remplis.', 'error')
    db.close()
    return render_template('pages/admin_pub_ajouter.html',
        emplacements=EMPLACEMENTS_PUB, villes=villes, categories=categories)

@app.route('/admin/publicites/<int:pub_id>/toggle', methods=['POST'])
@admin_required
def admin_pub_toggle(pub_id):
    db = get_db()
    p = db.execute('SELECT statut FROM publicites WHERE id=?', (pub_id,)).fetchone()
    if p:
        new_statut = 'inactive' if p['statut'] == 'active' else 'active'
        db.execute('UPDATE publicites SET statut=? WHERE id=?', (new_statut, pub_id))
        db.commit()
    db.close()
    flash('Publicite mise a jour.', 'success')
    return redirect(url_for('admin_publicites'))

# ════════════════════════════════════════════════════════════════════
# ERREURS
# ════════════════════════════════════════════════════════════════════

@app.route('/admin/annonce/<slug>/bon-plan', methods=['POST'])
@admin_required
def admin_bon_plan(slug):
    action = request.form.get('action', 'activer')
    db = get_db()
    ann = db.execute('''
        SELECT a.id, b.plan FROM annonces a
        JOIN boutiques b ON a.boutique_id=b.id
        WHERE a.slug=?
    ''', (slug,)).fetchone()
    if not ann:
        db.close(); abort(404)
    if action == 'activer':
        if ann['plan'] != 'premium':
            db.close()
            flash('Le bon plan est reserve aux boutiques Premium.', 'error')
            return redirect(url_for('admin'))
        expire = (datetime.datetime.now() + datetime.timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
        # Désactiver l'ancien bon plan
        db.execute('UPDATE annonces SET bon_plan=0, bon_plan_expire=NULL WHERE bon_plan=1')
        # Activer le nouveau
        db.execute('UPDATE annonces SET bon_plan=1, bon_plan_expire=? WHERE id=?', (expire, ann['id']))
        flash('Bon plan active pour 24h !', 'success')
    else:
        db.execute('UPDATE annonces SET bon_plan=0, bon_plan_expire=NULL WHERE id=?', (ann['id'],))
        flash('Bon plan desactive.', 'success')
    db.commit()
    db.close()
    return redirect(url_for('admin'))


@app.errorhandler(404)
def not_found(e):
    return render_template('pages/404.html'), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('pages/403.html'), 403


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050, debug=False)

@app.route('/supprimer-photo/<int:photo_id>', methods=['POST'])
@login_required
def supprimer_photo(photo_id):
    db = get_db()
    b = db.execute('SELECT id FROM boutiques WHERE vendeur_id=?', (session['vendeur_id'],)).fetchone()
    v = db.execute('SELECT is_admin FROM vendeurs WHERE id=?', (session['vendeur_id'],)).fetchone()
    is_admin = v and v['is_admin']
    if is_admin:
        p = db.execute('SELECT * FROM photos WHERE id=?', (photo_id,)).fetchone()
    elif b:
        p = db.execute(
            'SELECT p.* FROM photos p JOIN annonces a ON p.annonce_id=a.id '
            'WHERE p.id=? AND a.boutique_id=?', (photo_id, b['id'])).fetchone()
    else:
        p = None
    if p:
        annonce = db.execute('SELECT slug FROM annonces WHERE id=?', (p['annonce_id'],)).fetchone()
        for prefix in ['', 'thumb_']:
            fpath = os.path.join(UPLOAD_FOLDER, prefix + p['url'])
            try:
                if os.path.exists(fpath): os.remove(fpath)
            except Exception:
                pass
        db.execute('DELETE FROM photos WHERE id=?', (photo_id,))
        db.commit()
        flash('Photo supprimee.', 'success')
        db.close()
        return redirect(url_for('modifier_annonce', slug=annonce['slug']) if annonce else url_for('dashboard'))
    else:
        flash('Photo introuvable.', 'error')
    db.close()
    return redirect(url_for('dashboard'))

@app.route('/signaler/<int:annonce_id>', methods=['POST'])
def signaler_annonce(annonce_id):
    db = get_db()
    a = db.execute('SELECT id, statut FROM annonces WHERE id=?', (annonce_id,)).fetchone()
    if not a or a['statut'] != 'active':
        db.close(); abort(404)
    raison = request.form.get('raison', '').strip()[:200]
    vendeur_id = session.get('vendeur_id')
    try:
        db.execute('INSERT INTO signalements (annonce_id, vendeur_id, raison) VALUES (?,?,?)',
                   (annonce_id, vendeur_id, raison or None))
        db.commit()
        # Masquage automatique à 3 signalements
        nb = db.execute('SELECT COUNT(*) FROM signalements WHERE annonce_id=?', (annonce_id,)).fetchone()[0]
        if nb >= 3:
            db.execute('UPDATE annonces SET statut="masquee" WHERE id=?', (annonce_id,))
            db.commit()
        flash('Merci pour votre signalement. Notre équipe va vérifier cette annonce.', 'success')
    except Exception:
        flash('Vous avez déjà signalé cette annonce.', 'error')
    db.close()
    return redirect(request.referrer or url_for('index'))

@app.route('/boutique/<slug>/avis', methods=['POST'])
@login_required
def soumettre_avis(slug):
    db = get_db()
    b = db.execute('SELECT id FROM boutiques WHERE slug=? AND actif=1', (slug,)).fetchone()
    if not b:
        db.close(); abort(404)
    boutique_id = b['id']
    auteur_id   = session['vendeur_id']
    # Empêcher le vendeur de noter sa propre boutique
    own = db.execute('SELECT id FROM boutiques WHERE id=? AND vendeur_id=?',
                     (boutique_id, auteur_id)).fetchone()
    if own:
        flash("Vous ne pouvez pas noter votre propre boutique.", 'error')
        db.close()
        return redirect(url_for('boutique', slug=slug))
    try:
        note = int(request.form.get('note', 0))
        assert 1 <= note <= 5
    except Exception:
        flash("Note invalide.", 'error')
        db.close()
        return redirect(url_for('boutique', slug=slug))
    commentaire = request.form.get('commentaire', '').strip()[:500]
    try:
        db.execute(
            'INSERT INTO avis (auteur_id, boutique_id, note, commentaire) VALUES (?,?,?,?)',
            (auteur_id, boutique_id, note, commentaire or None))
        db.commit()
        flash('Merci pour votre avis !', 'success')
    except Exception:
        flash("Vous avez déjà laissé un avis pour cette boutique.", 'error')
    db.close()
    return redirect(url_for('boutique', slug=slug))
