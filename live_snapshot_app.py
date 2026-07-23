import os
import re
import uuid
import datetime
import sqlite3
from functools import wraps
from authlib.integrations.flask_client import OAuth
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, abort, session, jsonify, send_file)
from werkzeug.security import generate_password_hash, check_password_hash
from database import init_db

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.secret_key = os.environ.get('SECRET_KEY', 'nexora-kongo-annonces-2026-secret')

init_db()

@app.before_request
def auto_publier_articles():
    """Auto-publie les articles planifies dont la date est atteinte."""
    try:
        db = get_db()
        db.execute(
            "UPDATE blog_articles SET statut='publie' "
            "WHERE statut IN ('brouillon','planifie') "
            "AND published_at IS NOT NULL "
            "AND published_at <= datetime('now', '+1 hour')"
        )
        db.commit()
        db.close()
    except Exception:
        pass


@app.before_request
def tracker_visites():
    import datetime
    skip = ['/static', '/favicon', '/robots', '/sitemap', '/admin', '/api']
    if any(request.path.startswith(s) for s in skip):
        return
    try:
        db = get_db()
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.execute(
            "INSERT INTO site_visits (path, ip, user_agent, visited_at) VALUES (?,?,?,?)",
            (request.path,
             request.headers.get('X-Forwarded-For', request.remote_addr),
             request.user_agent.string[:200],
             now)
        )
        db.commit()
        db.close()
    except Exception as _e:
        import traceback
        open('/tmp/tracker_error.log','a').write(traceback.format_exc()+'\n')


import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST     = 'smtp.gmail.com'
SMTP_PORT     = 587
SMTP_USER     = 'ddieuval15@gmail.com'
SMTP_PASSWORD = 'itedvvxaojmswxlg'
SITE_URL = 'https://hellobizcongo.com'

def envoyer_email(destinataire, sujet, corps_html):
    def _send():
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = sujet
            msg['From']    = 'helloBiz Congo <' + SMTP_USER + '>'
            msg['To']      = destinataire
            msg.attach(MIMEText(corps_html, 'html', 'utf-8'))
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as srv:
                srv.starttls()
                srv.login(SMTP_USER, SMTP_PASSWORD)
                srv.sendmail(SMTP_USER, destinataire, msg.as_string())
            print('[EMAIL OK] ' + destinataire)
        except Exception as e:
            print('[EMAIL ERROR] ' + str(e))
    threading.Thread(target=_send, daemon=True).start()


def notifier_alertes(annonce_id, titre, description, prix, categorie_id, ville_id, quartier_id):
    # Verifie les alertes actives et envoie un email aux utilisateurs dont l'alerte correspond.
    try:
        db = get_db()
        alertes = db.execute('''
            SELECT al.*, v.email, v.nom as vendeur_nom
            FROM alertes al JOIN vendeurs v ON al.vendeur_id = v.id
            WHERE al.actif = 1
        ''').fetchall()
        annonce_url = f'{SITE_URL}/annonce/{db.execute("SELECT slug FROM annonces WHERE id=?", (annonce_id,)).fetchone()["slug"]}'
        db.close()
        for al in alertes:
            if al['categorie_id'] and al['categorie_id'] != categorie_id:
                continue
            if al['ville_id'] and al['ville_id'] != ville_id:
                continue
            if al['quartier_id'] and al['quartier_id'] != quartier_id:
                continue
            if al['prix_min'] and prix and prix < al['prix_min']:
                continue
            if al['prix_max'] and prix and prix > al['prix_max']:
                continue
            if al['mots_cles']:
                mots = [m.strip().lower() for m in al['mots_cles'].split(',')]
                texte = (titre + ' ' + (description or '')).lower()
                if not any(m in texte for m in mots):
                    continue
            prix_affiche = f"{prix:,.0f} FCFA".replace(',', ' ') if prix and prix > 0 else "Prix a negocier"
            corps = f'''
            <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;padding:24px">
              <div style="background:#00b7aa;padding:16px 24px;border-radius:8px 8px 0 0">
                <h1 style="color:white;margin:0;font-size:20px">Nouvelle annonce pour vous</h1>
              </div>
              <div style="border:1px solid #e5e7eb;border-top:none;padding:24px;border-radius:0 0 8px 8px">
                <p style="color:#374151">Bonjour <strong>{al['vendeur_nom']}</strong>,</p>
                <p style="color:#374151">Une nouvelle annonce correspond a votre alerte <strong>"{al['nom']}"</strong> :</p>
                <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin:16px 0">
                  <div style="font-size:16px;font-weight:700;color:#111827;margin-bottom:6px">{titre}</div>
                  <div style="font-size:18px;font-weight:900;color:#00b7aa">{prix_affiche}</div>
                </div>
                <a href="{annonce_url}" style="display:inline-block;background:#00b7aa;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:700;font-size:14px">
                  Voir l'annonce
                </a>
                <p style="color:#9ca3af;font-size:12px;margin-top:24px">
                  Vous recevez cet email car vous avez une alerte active sur helloBiz Congo.<br>
                  <a href="{SITE_URL}/alertes" style="color:#00b7aa">Gerer mes alertes</a>
                </p>
              </div>
            </div>
            '''
            envoyer_email(al['email'], f'Nouvelle annonce : {titre}', corps)
    except Exception as e:
        print(f'[ALERTES ERROR] {e}')


def calcul_badges_confiance(boutique, avis_list):
    # Calcule les badges de confiance d'une boutique a partir de ses infos existantes. Non bloquant.
    badges = []
    b = boutique
    try:
        if b['badge_verifie']:
            badges.append({'id': 'verifie', 'label': 'Verifie helloBiz', 'icon': '✅',
                            'couleur': '#16a34a', 'bg': '#f0fdf4'})
    except Exception:
        pass
    try:
        if b['logo'] and b['description'] and (b['telephone'] or b['whatsapp']):
            badges.append({'id': 'complet', 'label': 'Profil complet', 'icon': '📋',
                            'couleur': '#2563eb', 'bg': '#eff6ff'})
    except Exception:
        pass
    try:
        created = datetime.datetime.strptime(b['created_at'][:19], '%Y-%m-%d %H:%M:%S')
        mois = (datetime.datetime.now() - created).days // 30
        if mois >= 12:
            badges.append({'id': 'ancien', 'label': f'Membre depuis {mois // 12} an(s)', 'icon': '🏅',
                            'couleur': '#d97706', 'bg': '#fffbeb'})
        elif mois >= 3:
            badges.append({'id': 'ancien', 'label': f'Membre depuis {mois} mois', 'icon': '🏅',
                            'couleur': '#d97706', 'bg': '#fffbeb'})
    except Exception:
        pass
    try:
        if avis_list and len(avis_list) >= 3:
            note_moy = sum(a['note'] for a in avis_list) / len(avis_list)
            if note_moy >= 4.0:
                badges.append({'id': 'note', 'label': f'Bien note ({round(note_moy, 1)}/5)', 'icon': '⭐',
                                'couleur': '#b45309', 'bg': '#fef3c7'})
    except Exception:
        pass
    return badges



DB_PATH = os.environ.get('DB_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'marketplace.db'))

PLAN_LIMITS  = {'gratuit': 3, 'starter': 5, 'pro': 20, 'premium': 9999, 'business': 9999}
PLANS_TARIFS = {
    'gratuit':  {'nom': 'Gratuit',  'prix': 0,     'annonces': 3,    'photos': 2,  'videos': 0},
    'starter':  {'nom': 'Starter',  'prix': 2500,  'annonces': 5,    'photos': 3,  'videos': 0},
    'pro':      {'nom': 'Pro',      'prix': 6000,  'annonces': 20,   'photos': 8,  'videos': 1},
    'premium':  {'nom': 'Premium',  'prix': 12000, 'annonces': 9999, 'photos': 20, 'videos': 9999},
    'business': {'nom': 'Business', 'prix': 50000, 'annonces': 9999, 'photos': 30, 'videos': 9999},
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
            return redirect(url_for('connexion', next=request.url, _external=True))
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


def get_boutique_du_jour(db):
    from datetime import date
    today = str(date.today())
    existing = db.execute("SELECT b.*, c.nom as cat_nom FROM boutique_vedette bv JOIN boutiques b ON bv.boutique_id=b.id LEFT JOIN categories c ON b.categorie_id=c.id WHERE bv.date_vedette=?", (today,)).fetchone()
    if existing: return existing
    boutiques = db.execute("SELECT b.*, c.nom as cat_nom, (SELECT COUNT(*) FROM annonces WHERE boutique_id=b.id AND statut='active') as nb_annonces FROM boutiques b LEFT JOIN categories c ON b.categorie_id=c.id WHERE b.actif=1").fetchall()
    if not boutiques: return None
    best, best_score = None, -1
    for b in boutiques:
        score = (3 if b["logo"] else 0)+(2 if b["banniere"] else 0)+(1 if b["description"] and len(b["description"])>20 else 0)+(1 if b["whatsapp"] else 0)+(2 if b["badge_verifie"] else 0)+(3 if b["plan"]=="premium" else 2 if b["plan"]=="pro" else 1)+min(b["nb_annonces"] or 0,3)
        if score>best_score: best_score,best=score,b
    if best:
        try: db.execute("INSERT OR REPLACE INTO boutique_vedette (boutique_id,date_vedette,mode) VALUES (?,?,'auto')", (best["id"],today)); db.commit()
        except: pass
    return best


oauth=OAuth(app)
google_oauth=oauth.register(name='google',client_id='554436214311-t88auqoa0f1eevvdramak096at32i3pk.apps.googleusercontent.com',client_secret='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',server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',client_kwargs={'scope':'openid email profile'})


@app.route('/wa/<slug>')
def wa_redirect(slug):
    import sqlite3 as _sq
    try:
        b2 = _sq.connect(DB_PATH).execute(
            "SELECT id, whatsapp, telephone FROM boutiques WHERE slug=? AND actif=1", (slug,)).fetchone()
        if b2:
            bid, wa, tel = b2
            num = (wa or tel or '').replace(' ', '').replace('+', '')
            c2 = _sq.connect(DB_PATH)
            c2.execute("INSERT INTO clics_whatsapp(boutique_id,ip,user_agent) VALUES(?,?,?)",
                (bid, request.remote_addr, request.headers.get('User-Agent', '')[:200]))
            c2.commit(); c2.close()
            if num:
                return redirect('https://wa.me/' + num)
    except Exception:
        pass
    return redirect('/')


@app.route('/wa-annonce/<int:ann_id>')
def wa_annonce_redirect(ann_id):
    import sqlite3 as _sq
    try:
        row = _sq.connect(DB_PATH).execute(
            "SELECT b.id, b.whatsapp, b.telephone FROM annonces a JOIN boutiques b ON a.boutique_id=b.id WHERE a.id=? AND a.statut='active'", (ann_id,)).fetchone()
        if row:
            bid, wa, tel = row
            num = (wa or tel or '').replace(' ', '').replace('+', '')
            c2 = _sq.connect(DB_PATH)
            c2.execute("INSERT INTO clics_whatsapp(boutique_id,annonce_id,ip,user_agent) VALUES(?,?,?,?)",
                (bid, ann_id, request.remote_addr, request.headers.get('User-Agent', '')[:200]))
            c2.commit(); c2.close()
            if num:
                return redirect('https://wa.me/' + num)
    except Exception:
        pass
    return redirect('/')

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
               (SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url,
               CASE WHEN datetime(a.created_at) >= datetime('now', '-48 hours') THEN 1 ELSE 0 END as is_new
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
    boutique_du_jour = get_boutique_du_jour(db)
    # ── Matching Niveau 1 : Pour vous ──
    pour_vous = []
    if 'vendeur_id' in session:
        # Catégories les plus consultées par ce vendeur
        cats_vues = db.execute('''
            SELECT a.categorie_id, COUNT(*) as nb
            FROM vues_journal vj JOIN annonces a ON vj.annonce_id=a.id
            WHERE a.boutique_id IN (SELECT id FROM boutiques WHERE vendeur_id=?)
               OR vj.annonce_id IN (
                   SELECT annonce_id FROM vues_journal WHERE annonce_id IN (
                       SELECT id FROM annonces WHERE statut="active"
                   ) ORDER BY id DESC LIMIT 100
               )
            GROUP BY a.categorie_id ORDER BY nb DESC LIMIT 3
        ''', (session['vendeur_id'],)).fetchall()
        if not cats_vues:
            # Fallback : annonces récentes si pas d'historique
            cats_vues = []
        cat_ids = [str(r['categorie_id']) for r in cats_vues]
    else:
        # Visiteur anonyme : top catégories globales
        cats_top = db.execute('''
            SELECT categorie_id, COUNT(*) as nb FROM annonces
            WHERE statut="active" GROUP BY categorie_id ORDER BY nb DESC LIMIT 3
        ''').fetchall()
        cat_ids = [str(r['categorie_id']) for r in cats_top]

    if cat_ids:
        pour_vous = db.execute(f'''
            SELECT a.*, c.icon as cat_icon, c.nom as cat_nom, v.nom as ville_nom,
                   b.plan as boutique_plan,
                   (SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url
            FROM annonces a
            JOIN categories c ON a.categorie_id=c.id
            JOIN villes v ON a.ville_id=v.id
            LEFT JOIN boutiques b ON a.boutique_id=b.id
            WHERE a.statut="active" AND a.categorie_id IN ({",".join(cat_ids)})
            ORDER BY CASE WHEN b.plan IN ("premium","business") THEN 0 WHEN b.plan="pro" THEN 1 ELSE 2 END,
                     a.vues DESC, a.created_at DESC
            LIMIT 6
        ''').fetchall()

    db.close()
    return render_template('pages/index.html',
        villes=villes, categories=categories, stats=stats,
        annonces_recentes=annonces, boutiques_vedettes=boutiques,
        mes_favoris_ids=mes_favoris_ids, bon_plan=bon_plan,
           boutique_du_jour=boutique_du_jour)


@app.route("/admin/boutique-vedette", methods=["GET", "POST"])
@admin_required
def admin_boutique_vedette():
    boutique_id = request.form.get('boutique_id')
    if boutique_id:
        from datetime import date as _d
        today = _d.today().isoformat()
        db = get_db()
        db.execute("INSERT OR REPLACE INTO boutique_vedette (boutique_id,date_vedette,mode) VALUES (?,?,'manual')", (boutique_id, today))
        db.commit()
        flash('Boutique du jour mise a jour.', 'success')
        return redirect(url_for('admin_boutique_vedette'))
    from datetime import date
    today = date.today().isoformat()
    db = get_db()
    boutiques = db.execute('SELECT * FROM boutiques ORDER BY nom').fetchall()
    current = db.execute("SELECT bv.*,b.nom as boutique_nom,bv.boutique_id FROM boutique_vedette bv JOIN boutiques b ON bv.boutique_id=b.id WHERE bv.date_vedette=?",(today,)).fetchone()
    return render_template("pages/admin_boutique_vedette.html", current=current, boutiques=boutiques, today=today)



@app.route('/devenir-vendeur')
def devenir_vendeur():
    return render_template('pages/devenir_vendeur.html')

@app.route('/emploi')
def emploi():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    cat_emploi = db.execute('SELECT * FROM categories WHERE slug="emploi"').fetchone()
    offres = []
    total = 0
    if cat_emploi:
        offres = db.execute('''
            SELECT a.*, v.nom as ville_nom, b.nom as boutique_nom, b.whatsapp, b.telephone, b.slug as boutique_slug,
                   b.badge_verifie, b.plan,
                   (SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url
            FROM annonces a
            JOIN villes v ON a.ville_id=v.id
            LEFT JOIN boutiques b ON a.boutique_id=b.id
            WHERE a.categorie_id=? AND a.statut="active"
            ORDER BY CASE WHEN b.plan IN ("premium","business") THEN 0 WHEN b.plan="pro" THEN 1 ELSE 2 END,
                     a.created_at DESC
            LIMIT 50
        ''', (cat_emploi['id'],)).fetchall()
        total = db.execute('SELECT COUNT(*) as n FROM annonces WHERE categorie_id=? AND statut="active"', (cat_emploi['id'],)).fetchone()['n']
    secteurs = db.execute('''
        SELECT emploi_secteur, COUNT(*) as nb FROM annonces
        WHERE categorie_id=? AND statut="active" AND emploi_secteur IS NOT NULL
        GROUP BY emploi_secteur ORDER BY nb DESC LIMIT 8
    ''', (cat_emploi['id'],)).fetchall() if cat_emploi else []
    db.close()
    return render_template('pages/emploi.html',
        offres=offres, total=total, secteurs=secteurs,
        villes=villes, categories=categories)


@app.route('/deposer-emploi', methods=['GET', 'POST'])
def deposer_emploi():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    cat_emploi = db.execute('SELECT * FROM categories WHERE slug="emploi"').fetchone()
    form = {}
    errors = []
    logged_in = bool(session.get('vendeur_id'))

    if request.method == 'POST':
        form = {k: v.strip() for k, v in request.form.items()}
        emploi_type  = form.get('emploi_type', 'offre')
        titre        = form.get('titre', '')
        entreprise   = form.get('entreprise', '')
        secteur      = form.get('secteur', '')
        contrat      = form.get('contrat', '')
        ville_id     = form.get('ville_id', '')
        description  = form.get('description', '')
        telephone    = form.get('telephone', '')
        salaire_raw  = form.get('salaire', '')
        password     = form.get('password', '')

        if len(titre) < 3:       errors.append('Intitule du poste trop court.')
        if len(entreprise) < 2:  errors.append('Nom entreprise ou profil requis.')
        if not secteur:          errors.append('Secteur d activite requis.')
        if not ville_id:         errors.append('Ville requise.')
        if len(description) < 20: errors.append('Description trop courte (min. 20 caracteres).')
        if len(telephone) < 8:   errors.append('Numero de telephone invalide.')
        if not logged_in and len(password) < 4: errors.append('Code d acces trop court (min. 4 caracteres).')

        if not errors:
            vendeur_id  = session.get('vendeur_id')
            boutique_id = session.get('boutique_id')

            if not vendeur_id:
                existing_v = db.execute('SELECT * FROM vendeurs WHERE telephone=?', (telephone,)).fetchone()
                if existing_v:
                    vendeur_id = existing_v['id']
                    session.update({'vendeur_id': vendeur_id, 'vendeur_nom': existing_v['nom'], 'vendeur_plan': 'starter'})
                else:
                    from werkzeug.security import generate_password_hash as gph
                    db.execute('INSERT INTO vendeurs (nom, telephone, password_hash) VALUES (?,?,?)',
                               (entreprise, telephone, gph(password)))
                    db.commit()
                    v = db.execute('SELECT * FROM vendeurs WHERE telephone=?', (telephone,)).fetchone()
                    vendeur_id = v['id']
                    session.update({'vendeur_id': vendeur_id, 'vendeur_nom': v['nom'], 'vendeur_plan': 'starter'})
                    logged_in = True

            if vendeur_id and not boutique_id:
                existing_b = db.execute('SELECT * FROM boutiques WHERE vendeur_id=?', (vendeur_id,)).fetchone()
                if existing_b:
                    boutique_id = existing_b['id']
                    session.update({'boutique_id': boutique_id, 'boutique_slug': existing_b['slug']})
                else:
                    bslug = unique_slug(db, 'boutiques', slugify(entreprise))
                    desc_b = f"Profil recruteur helloBiz Congo. Contact : {telephone}."
                    db.execute('''INSERT INTO boutiques (slug,nom,description,categorie_id,ville_id,telephone,whatsapp,plan,vendeur_id,actif)
                        VALUES (?,?,?,?,?,?,?,?,?,?)''',
                        (bslug, entreprise, desc_b, cat_emploi['id'], ville_id, telephone, telephone, 'starter', vendeur_id, 1))
                    db.commit()
                    b = db.execute('SELECT * FROM boutiques WHERE slug=?', (bslug,)).fetchone()
                    boutique_id = b['id']
                    session.update({'boutique_id': boutique_id, 'boutique_slug': b['slug']})

            if vendeur_id and boutique_id:
                desc_finale = description
                if contrat:
                    desc_finale = f"Type de contrat : {contrat}\n\n{description}"
                prix = 0
                if salaire_raw:
                    try: prix = int(''.join(filter(str.isdigit, salaire_raw)))
                    except: prix = 0
                aslug = unique_slug(db, 'annonces', slugify(titre))
                import datetime as _dt
                expire_at = (_dt.datetime.now() + _dt.timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S')
                quartier_libre = request.form.get('quartier_libre', '').strip() or None
                if str(quartier_id) == 'autre':
                    quartier_id = None
                db.execute('''INSERT INTO annonces
                    (slug,titre,description,prix,prix_type,categorie_id,ville_id,boutique_id,
                     emploi_type,emploi_secteur,emploi_salaire,statut,expire_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (aslug, titre, desc_finale, prix, 'mois' if prix > 0 else 'negociable',
                     cat_emploi['id'], ville_id, boutique_id,
                     emploi_type, secteur, salaire_raw, 'active', expire_at))
                db.commit()
                db.close()
                flash('Votre annonce est en ligne !', 'success')
                return redirect('/annonce/' + aslug)

        for e in errors:
            flash(e, 'error')

    db.close()
    return render_template('pages/deposer_emploi.html',
        villes=villes, form=form, logged_in=logged_in)

@app.route('/robots.txt')
def robots():
    return app.response_class("User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /dashboard\nDisallow: /messages\nSitemap: https://hellobizcongo.com/sitemap.xml\n", mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap():
    db = get_db()
    annonces = db.execute('SELECT slug, created_at FROM annonces WHERE statut="active"').fetchall()
    boutiques = db.execute('SELECT slug, created_at FROM boutiques WHERE actif=1').fetchall()
    # Auto-publier les articles dont la date est atteinte
    db.execute("UPDATE blog_articles SET statut='publie' WHERE statut IN ('brouillon','planifie') AND published_at IS NOT NULL AND datetime(published_at) <= datetime('now', '+1 hour')")
    db.commit()
    articles_blog = db.execute("SELECT slug, updated_at FROM blog_articles WHERE statut='publie'").fetchall()
    db.close()
    urls = ['https://hellobizcongo.com/', 'https://hellobizcongo.com/recherche', 'https://hellobizcongo.com/boutiques', 'https://hellobizcongo.com/tarifs']
    xml = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    for u in urls:
        xml += f'<url><loc>{u}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>'
    for a in annonces:
        xml += f'<url><loc>https://hellobizcongo.com/annonce/{a["slug"]}</loc><lastmod>{str(a["created_at"])[:10]}</lastmod><priority>0.7</priority></url>'
    for b in boutiques:
        xml += f'<url><loc>https://hellobizcongo.com/boutique/{b["slug"]}</loc><lastmod>{str(b["created_at"])[:10]}</lastmod><priority>0.6</priority></url>'
    for art in articles_blog:
        xml += '<url><loc>https://hellobizcongo.com/blog/' + str(art[0]) + '</loc><lastmod>' + str(art[1])[:10] + '</lastmod><priority>0.7</priority></url>'
    xml += '</urlset>'
    return app.response_class(xml, mimetype='application/xml')

@app.route('/sw.js')
def service_worker():
    return app.send_static_file('sw.js'), 200, {'Content-Type': 'application/javascript'}

@app.route('/manifest.json')
def manifest():
    return app.send_static_file('manifest.json'), 200, {'Content-Type': 'application/manifest+json'}

@app.route('/offline')
def offline():
    html = "<html><body style='font-family:sans-serif;text-align:center;padding:50px;background:#0f172a;color:#fff'>"
    html += "<h1 style='color:#6366f1'>helloBiz</h1><p>Vous etes hors ligne.</p></body></html>"
    return html

    from datetime import date
    today = str(date.today())
    db = get_db()
    if request.method == "POST":
        bid = request.form.get("boutique_id", type=int)
        if bid:
            db.execute("INSERT OR REPLACE INTO boutique_vedette (boutique_id,date_vedette,mode) VALUES (?,?,'manual')", (bid,today))
            db.commit()
            flash("Boutique du Jour mise a jour.", "success")
        db.close()
        return redirect(url_for("admin_boutique_vedette"))
    current = db.execute("SELECT bv.*,b.nom as boutique_nom,bv.boutique_id FROM boutique_vedette bv JOIN boutiques b ON bv.boutique_id=b.id WHERE bv.date_vedette=?", (today,)).fetchone()
    boutiques = db.execute("SELECT b.*,(SELECT COUNT(*) FROM annonces WHERE boutique_id=b.id AND statut='active') as nb_annonces FROM boutiques b WHERE b.actif=1 ORDER BY b.plan DESC,b.nom").fetchall()
    db.close()
    return render_template("pages/admin_boutique_vedette.html", current=current, boutiques=boutiques, today=today)
@app.route('/support')
def support():
    return render_template('pages/support.html')

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

    # Scoring pertinence : plan + fraîcheur + popularité
    score_expr = '''
        (CASE WHEN b.plan IN ("premium","business") THEN 40
              WHEN b.plan="pro" THEN 20
              WHEN b.plan="starter" THEN 10
              ELSE 0 END)
        + (CASE WHEN a.created_at >= datetime("now","-3 days") THEN 30
                WHEN a.created_at >= datetime("now","-7 days") THEN 20
                WHEN a.created_at >= datetime("now","-30 days") THEN 10
                ELSE 0 END)
        + (CASE WHEN a.vues > 100 THEN 15
                WHEN a.vues > 50 THEN 10
                WHEN a.vues > 10 THEN 5
                ELSE 0 END)
        + (CASE WHEN b.badge_verifie=1 THEN 10 ELSE 0 END)
    '''
    order = {
        'pertinence': score_expr + ' DESC',
        'recent':    'CASE WHEN b.plan IN ("premium","business") THEN 0 WHEN b.plan="pro" THEN 1 ELSE 2 END, a.created_at DESC',
        'prix-asc':  'a.prix ASC',
        'prix-desc': 'a.prix DESC',
        'vues':      'a.vues DESC',
    }.get(tri, score_expr + ' DESC')

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
               (SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url,
               CASE WHEN datetime(a.created_at) >= datetime('now', '-48 hours') THEN 1 ELSE 0 END as is_new
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
    _is_admin = session.get('is_admin', False)
    b = db.execute('''
        SELECT b.*, c.nom as cat_nom, v.nom as ville_nom
        FROM boutiques b JOIN categories c ON b.categorie_id=c.id JOIN villes v ON b.ville_id=v.id
        WHERE b.slug=? AND (b.actif=1 OR ?)
    ''', (slug, 1 if _is_admin else 0)).fetchone()
    if not b:
        abort(404)
    annonces_b = db.execute('''
        SELECT a.*, c.icon as cat_icon, v.nom as ville_nom,
               (SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url,
               CASE WHEN datetime(a.created_at) >= datetime('now', '-48 hours') THEN 1 ELSE 0 END as is_new
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
    badges = calcul_badges_confiance(b, avis_list)
    db.close()
    return render_template('pages/boutique.html', boutique=b, annonces=annonces_b, stats=stats,
        avis_list=avis_list, note_moy=note_moy, mon_avis=mon_avis, badges=badges,
        villes=villes, categories=categories)



@app.route('/boutique/<slug>/affiche.pdf')
@login_required
def affiche_boutique_pdf(slug):
    db = get_db()
    b = db.execute(
        'SELECT b.*, v.nom as ville_nom FROM boutiques b '
        'JOIN villes v ON b.ville_id=v.id WHERE b.slug=? AND b.vendeur_id=?',
        (slug, session['vendeur_id'])).fetchone()
    db.close()
    if not b: abort(403)
    try:
        import qrcode as _qr, io
        from reportlab.lib.utils import ImageReader
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as _rc
        from reportlab.lib.units import cm
    except ImportError as e:
        flash(f'Module manquant : {e}', 'error')
        return redirect(url_for('dashboard'))
    url_b = f'{SITE_URL}/boutique/{slug}'
    q = _qr.QRCode(version=1, box_size=10, border=4)
    q.add_data(url_b); q.make(fit=True)
    qimg = q.make_image(fill_color="black", back_color="white")
    qbuf = io.BytesIO(); qimg.save(qbuf, format='PNG'); qbuf.seek(0)
    buf = io.BytesIO(); w, h = A4
    c = _rc.Canvas(buf, pagesize=A4)
    c.setFillColorRGB(0.055,0.055,0.055); c.rect(0,0,w,h,fill=1,stroke=0)
    c.setFillColorRGB(0,0.718,0.667); c.rect(0,h-2*cm,w,2*cm,fill=1,stroke=0)
    c.setFillColorRGB(1,1,1); c.setFont("Helvetica-Bold",26)
    c.drawCentredString(w/2,h-1.3*cm,"helloBiz Congo")
    c.setFillColorRGB(0.96,0.77,0.094); c.setFont("Helvetica-Bold",20)
    c.drawCentredString(w/2,h-3.8*cm,b['nom'][:38])
    c.setFillColorRGB(0.7,0.7,0.7); c.setFont("Helvetica",13)
    c.drawCentredString(w/2,h-5*cm,"Scannez pour voir toutes mes annonces")
    qs=8*cm; qx=(w-qs)/2; qy=h/2-qs/2+0.5*cm
    c.drawImage(ImageReader(io.BytesIO(qbuf.getvalue())),qx,qy,qs,qs)
    c.setStrokeColorRGB(0,0.718,0.667); c.setLineWidth(3)
    c.rect(qx-5,qy-5,qs+10,qs+10,fill=0)
    c.setFillColorRGB(0.5,0.5,0.5); c.setFont("Helvetica",9)
    c.drawCentredString(w/2,qy-0.7*cm,url_b)
    yc=qy-2.2*cm; c.setFillColorRGB(1,1,1); c.setFont("Helvetica-Bold",14)
    c.drawCentredString(w/2,yc,"Nous contacter"); yc-=0.7*cm
    c.setFont("Helvetica",13)
    if b['whatsapp']:
        c.setFillColorRGB(0.13,0.85,0.52)
        c.drawCentredString(w/2,yc,f"WhatsApp : {b['whatsapp']}"); yc-=0.6*cm
    if b['telephone']:
        c.setFillColorRGB(1,1,1)
        c.drawCentredString(w/2,yc,f"Tel : {b['telephone']}"); yc-=0.5*cm
    c.setFillColorRGB(0.55,0.55,0.55); c.setFont("Helvetica",11)
    c.drawCentredString(w/2,yc,f"Ville : {b['ville_nom']}")
    c.setFillColorRGB(0,0.718,0.667); c.rect(0,0,w,1.2*cm,fill=1,stroke=0)
    c.setFillColorRGB(1,1,1); c.setFont("Helvetica",10)
    c.drawCentredString(w/2,0.4*cm,"La marketplace du Congo - donytchicaya.pythonanywhere.com")
    c.save(); buf.seek(0)
    return send_file(buf,mimetype='application/pdf',as_attachment=True,
                     download_name=f'affiche-boutique-{slug}.pdf')


@app.route('/annonce/<slug>/affiche.pdf')
@login_required
def affiche_annonce_pdf(slug):
    db = get_db()
    a = db.execute(
        'SELECT a.*, c.nom as cat_nom, v.nom as ville_nom, '
        'b.nom as bnom, b.whatsapp as bwa, b.telephone as btel, b.vendeur_id as bvid '
        'FROM annonces a JOIN categories c ON a.categorie_id=c.id '
        'JOIN villes v ON a.ville_id=v.id '
        'LEFT JOIN boutiques b ON a.boutique_id=b.id '
        'WHERE a.slug=? AND b.vendeur_id=?',
        (slug, session['vendeur_id'])).fetchone()
    db.close()
    if not a: abort(403)
    try:
        import qrcode as _qr, io
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as _rc
        from reportlab.lib.units import cm
    except ImportError as e:
        flash(f'Module manquant : {e}', 'error')
        return redirect(url_for('dashboard'))
    url_a = f'{SITE_URL}/annonce/{slug}'
    q = _qr.QRCode(version=1,box_size=8,border=4)
    q.add_data(url_a); q.make(fit=True)
    qimg = q.make_image(fill_color="black",back_color="white")
    qbuf = io.BytesIO(); qimg.save(qbuf,format='PNG'); qbuf.seek(0)
    buf = io.BytesIO(); w,h = A4
    c = _rc.Canvas(buf,pagesize=A4)
    c.setFillColorRGB(0.055,0.055,0.055); c.rect(0,0,w,h,fill=1,stroke=0)
    c.setFillColorRGB(0,0.718,0.667); c.rect(0,h-2*cm,w,2*cm,fill=1,stroke=0)
    c.setFillColorRGB(1,1,1); c.setFont("Helvetica-Bold",24)
    c.drawCentredString(w/2,h-1.3*cm,"helloBiz Congo")
    c.setFillColorRGB(0.96,0.77,0.094); c.setFont("Helvetica-Bold",18)
    c.drawCentredString(w/2,h-3.5*cm,a['titre'][:42])
    if a['prix'] and a['prix']>0:
        c.setFillColorRGB(1,1,1); c.setFont("Helvetica-Bold",26)
        ps=f"{int(a['prix']):,}".replace(',',' ')+' FCFA'
        if a['prix_type']=='moi': ps+='/mois'
        c.drawCentredString(w/2,h-4.8*cm,ps)
    else:
        c.setFillColorRGB(0.7,0.7,0.7); c.setFont("Helvetica-Bold",20)
        c.drawCentredString(w/2,h-4.8*cm,"Prix a negocier")
    c.setFillColorRGB(0.6,0.6,0.6); c.setFont("Helvetica",12)
    c.drawCentredString(w/2,h-5.7*cm,f"{a['cat_nom']} - {a['ville_nom']}")
    qs=7*cm; qx=(w-qs)/2; qy=h/2-qs/2+1*cm
    c.drawImage(ImageReader(io.BytesIO(qbuf.getvalue())),qx,qy,qs,qs)
    c.setStrokeColorRGB(0,0.718,0.667); c.setLineWidth(2)
    c.rect(qx-4,qy-4,qs+8,qs+8,fill=0)
    c.setFillColorRGB(0.5,0.5,0.5); c.setFont("Helvetica",9)
    c.drawCentredString(w/2,qy-0.6*cm,"Scannez pour voir l annonce complete")
    c.drawCentredString(w/2,qy-1.1*cm,url_a)
    yc=qy-2.1*cm; c.setFillColorRGB(1,1,1); c.setFont("Helvetica-Bold",13)
    c.drawCentredString(w/2,yc,"Contact"); yc-=0.6*cm
    c.setFont("Helvetica",12)
    if a['bwa']:
        c.setFillColorRGB(0.13,0.85,0.52)
        c.drawCentredString(w/2,yc,f"WhatsApp : {a['bwa']}"); yc-=0.5*cm
    if a['btel']:
        c.setFillColorRGB(1,1,1)
        c.drawCentredString(w/2,yc,f"Tel : {a['btel']}")
    c.setFillColorRGB(0,0.718,0.667); c.rect(0,0,w,1.2*cm,fill=1,stroke=0)
    c.setFillColorRGB(1,1,1); c.setFont("Helvetica",10)
    c.drawCentredString(w/2,0.4*cm,"La marketplace du Congo - donytchicaya.pythonanywhere.com")
    c.save(); buf.seek(0)
    return send_file(buf,mimetype='application/pdf',as_attachment=True,
                     download_name=f'affiche-annonce-{slug}.pdf')



EMPLOI_SECTEURS = {
    "transport-logistique": "Transport / Logistique",
    "commerce-vente": "Commerce / Vente",
    "secretariat-admin": "Secretariat / Admin",
    "informatique-tech": "Informatique / Tech",
    "btp-construction": "BTP / Construction",
    "sante-medical": "Sante / Medical",
    "enseignement-formation": "Enseignement / Formation",
    "hotellerie-restauration": "Hotellerie / Restauration",
    "finance-comptabilite": "Finance / Comptabilite",
    "petrole-mines": "Petrole / Mines",
    "securite-gardiennage": "Securite / Gardiennage",
    "nettoyage-maintenance": "Nettoyage / Maintenance",
}

@app.route("/emploi/<secteur_slug>")
def emploi_secteur(secteur_slug):
    if secteur_slug not in EMPLOI_SECTEURS:
        abort(404)
    secteur_nom = EMPLOI_SECTEURS[secteur_slug]
    db = get_db()
    villes, categories, quartiers = get_base_data()
    cat_emploi = db.execute("SELECT * FROM categories WHERE slug=\"emploi\"").fetchone()
    offres = []
    if cat_emploi:
        offres = db.execute("""
            SELECT a.*, v.nom as ville_nom, b.nom as boutique_nom,
            b.whatsapp, b.telephone, b.slug as boutique_slug,
            b.badge_verifie, b.plan,
            (SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url
            FROM annonces a
            JOIN villes v ON a.ville_id=v.id
            LEFT JOIN boutiques b ON a.boutique_id=b.id
            WHERE a.categorie_id=? AND a.statut="active" AND a.emploi_secteur=?
            ORDER BY CASE WHEN b.plan IN ("premium","business") THEN 0 WHEN b.plan="pro" THEN 1 ELSE 2 END,
            a.created_at DESC LIMIT 50
        """, (cat_emploi["id"], secteur_nom)).fetchall()
    db.close()
    return render_template("pages/emploi_secteur.html",
        offres=offres, secteur_slug=secteur_slug, secteur_nom=secteur_nom,
        villes=villes, categories=categories, tous_secteurs=EMPLOI_SECTEURS)


@app.route('/alertes-emploi', methods=['POST'])
def alertes_emploi():
    whatsapp = request.form.get('whatsapp', '').strip()
    secteur = request.form.get('secteur', 'tous').strip()
    ref = request.referrer or '/emploi'
    if not whatsapp or len(whatsapp) < 8:
        flash('Numero WhatsApp invalide.', 'error')
        return redirect(ref)
    if secteur not in list(EMPLOI_SECTEURS.keys()) + ['tous']:
        secteur = 'tous'
    db = get_db()
    try:
        db.execute('INSERT INTO alertes_emploi (whatsapp, secteur) VALUES (?, ?)', (whatsapp, secteur))
        db.commit()
        flash('Inscription reussie ! Vous recevrez des alertes emploi sur WhatsApp.', 'success')
    except Exception:
        flash('Vous etes deja inscrit pour ce secteur.', 'info')
    db.close()
    return redirect(ref)

@app.route('/admin/alertes-emploi')
def admin_alertes_emploi():
    if not session.get('is_admin'):
        return redirect('/admin')
    db = get_db()
    alertes = db.execute("""
        SELECT secteur, COUNT(*) as nb, GROUP_CONCAT(whatsapp, '||') as numeros
        FROM alertes_emploi WHERE actif=1
        GROUP BY secteur ORDER BY nb DESC
    """).fetchall()
    total = db.execute('SELECT COUNT(*) as n FROM alertes_emploi WHERE actif=1').fetchone()['n']
    recent = db.execute('SELECT * FROM alertes_emploi ORDER BY created_at DESC LIMIT 20').fetchall()
    db.close()
    return render_template('pages/admin_alertes_emploi.html', alertes=alertes, total=total, recent=recent)

@app.route('/admin/supprimer-alerte-emploi/<int:aid>', methods=['POST'])
def supprimer_alerte_emploi(aid):
    if not session.get('is_admin'):
        return redirect('/admin')
    db = get_db()
    db.execute('UPDATE alertes_emploi SET actif=0 WHERE id=?', (aid,))
    db.commit()
    db.close()
    return redirect('/admin/alertes-emploi')

@app.route('/immo')
def immo():
    db = get_db()
    villes, categories, quartiers = get_base_data()
    ville_id = request.args.get('ville_id', type=int)
    type_bien = request.args.get('type_bien', '')
    transaction = request.args.get('transaction', '')
    chambres = request.args.get('chambres', type=int)
    prix_max = request.args.get('prix_max', type=float)
    cat_immo = db.execute("SELECT id FROM categories WHERE slug='immobilier'").fetchone()
    cat_id = cat_immo['id'] if cat_immo else 0
    conds = ['a.statut=\"active\"', 'a.categorie_id=?']
    params = [cat_id]
    if ville_id: conds.append('a.ville_id=?'); params.append(ville_id)
    if type_bien: conds.append('a.immo_type=?'); params.append(type_bien)
    if transaction: conds.append('a.immo_transaction=?'); params.append(transaction)
    if chambres: conds.append('(a.immo_chambres IS NOT NULL AND a.immo_chambres>=?)'); params.append(chambres)
    if prix_max: conds.append('(a.prix IS NULL OR a.prix=0 OR a.prix<=?)'); params.append(prix_max)
    where = ' AND '.join(conds)
    annonces_immo = db.execute(
        'SELECT a.*, c.nom as cat_nom, v.nom as ville_nom, '
        'b.nom as boutique_nom, b.slug as boutique_slug, b.plan as boutique_plan, '
        '(SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url, '
        "CASE WHEN datetime(a.created_at) >= datetime('now','-48 hours') THEN 1 ELSE 0 END as is_new "
        'FROM annonces a JOIN categories c ON a.categorie_id=c.id '
        'JOIN villes v ON a.ville_id=v.id '
        'LEFT JOIN boutiques b ON a.boutique_id=b.id '
        f'WHERE {where} '
        "ORDER BY CASE WHEN b.plan IN ('premium','business') THEN 0 "
        "WHEN b.plan='pro' THEN 1 ELSE 2 END, a.created_at DESC LIMIT 60", params).fetchall()
    nb_r = db.execute(
        'SELECT COUNT(*) as n FROM annonces a LEFT JOIN boutiques b ON a.boutique_id=b.id '
        f'WHERE {where}', params).fetchone()
    nb_total = nb_r['n'] if nb_r else 0
    db.close()
    return render_template('pages/immo.html',
        annonces=annonces_immo, villes=villes, nb_total=nb_total,
        filtre_ville=ville_id, filtre_type=type_bien,
        filtre_transaction=transaction, filtre_chambres=chambres,
        filtre_prix_max=prix_max)

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


@app.route("/pres-de-moi")
def pres_de_moi():
    import math
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    rayon = request.args.get("rayon", 5, type=float)
    if not lat or not lng:
        return redirect(url_for("annonces"))
    db = get_db()
    villes, categories, quartiers = get_base_data()
    def hav(a1,o1,a2,o2):
        R=6371; d1=math.radians(a2-a1); d2=math.radians(o2-o1)
        a=math.sin(d1/2)**2+math.cos(math.radians(a1))*math.cos(math.radians(a2))*math.sin(d2/2)**2
        return R*2*math.asin(math.sqrt(a))
    ids=[str(q["id"]) for q in quartiers if q["latitude"] and hav(lat,lng,q["latitude"],q["longitude"])<=rayon]
    anns=db.execute(f'SELECT a.*,c.nom as cat_nom,c.icon as cat_icon,c.slug as cat_slug,v.nom as ville_nom,b.nom as boutique_nom,b.badge_verifie,b.plan as boutique_plan,qr.nom as quartier_nom FROM annonces a JOIN categories c ON a.categorie_id=c.id JOIN villes v ON a.ville_id=v.id LEFT JOIN boutiques b ON a.boutique_id=b.id LEFT JOIN quartiers qr ON a.quartier_id=qr.id WHERE a.statut="active" AND a.quartier_id IN ({",".join(ids) if ids else "0"}) ORDER BY a.created_at DESC').fetchall() if ids else []
    db.close()
    return render_template("pages/annonces.html",annonces=anns,villes=villes,categories=categories,quartiers=quartiers,total=len(anns),lat=lat,lng=lng,rayon=rayon,pres_de_moi=True,ville_slug="",categorie_slug="",quartier_slug="",ville_nom=None,categorie_nom=None,quartier_nom=None,q="",prix_min=None,prix_max=None,tri="recent")


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


@app.route('/tarifs')
def tarifs():
    villes, categories, quartiers = get_base_data()
    return render_template('pages/tarifs.html', villes=villes, categories=categories)

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
    ref = request.args.get('ref', '').strip().upper()
    if ref: session['parrain_ref'] = ref
    if request.method == 'POST':
        form = {k: v.strip() for k, v in request.form.items()}
        nom, email = form.get('nom', ''), form.get('email', '').lower()
        telephone  = form.get('telephone', '')
        password, password2 = form.get('password', ''), form.get('password2', '')
        plan = form.get('plan', 'gratuit')
        errors = []
        # Anti-bot
        if form.get('website', '').strip():
            return redirect(url_for('index'))
        if re.search(r'https?://|www\.|graph\.|bit\.ly|\.org|\.com|\.net', nom, re.I):
            errors.append('Nom invalide : les liens ne sont pas autorisés.')
        if len(nom) < 2:           errors.append('Le nom est trop court.')
        if len(telephone) < 8:      errors.append('Numero de telephone invalide.')
        if len(password) < 6:       errors.append('Mot de passe trop court (min. 6 caracteres).')
        if password != password2:   errors.append('Les mots de passe ne correspondent pas.')
        if plan not in PLAN_LIMITS: errors.append('Plan invalide.')
        if not errors:
            db = get_db()
            p_row = None  # evite UnboundLocalError
            if db.execute('SELECT id FROM vendeurs WHERE email=?', (email,)).fetchone():
                flash('Email deja utilise. Connectez-vous.', 'error')
                db.close()
                return render_template('pages/inscription.html', error='Cet email est deja utilise. Connectez-vous.', villes=villes, categories=categories, form=request.form)
            else:
                parrain_ref = session.pop('parrain_ref', '').strip().upper()
                p_row = db.execute('SELECT id FROM vendeurs WHERE parrain_code=?', (parrain_ref,)).fetchone() if parrain_ref else None
            pid = p_row['id'] if p_row else None
            # Auto-nettoyage comptes fantomes (inscription sans boutique)
            stuck = db.execute(
                'SELECT v.id FROM vendeurs v LEFT JOIN boutiques b ON b.vendeur_id=v.id WHERE v.telephone=? AND b.id IS NULL AND v.is_admin=0',
                (telephone,)).fetchone()
            if stuck:
                db.execute('DELETE FROM vendeurs WHERE id=?', (stuck['id'],))
                db.commit()
            try:
                db.execute('INSERT INTO vendeurs (nom,email,telephone,password_hash,ref_code,parrain_id) VALUES (?,?,?,?,?,?)',
                    (nom, email, telephone, generate_password_hash(password), session.pop("ref_code", None), pid))
                db.commit()
            except Exception:
                db.close()
                return render_template('pages/inscription.html', error='Ce numero de telephone est deja utilise.', villes=villes, categories=categories, form=request.form)
            v = db.execute('SELECT * FROM vendeurs WHERE telephone=?', (telephone,)).fetchone()
            db.close()
            session.update({'vendeur_id': v['id'], 'vendeur_nom': v['nom'], 'vendeur_plan': plan})
            try:
                envoyer_email('ddieuval15@gmail.com', 'Nouvelle inscription helloBiz : ' + nom, '<p>Nom : ' + nom + '<br>Tel : ' + telephone + '</p>')
            except Exception:
                pass  # email non bloquant
            if plan == 'gratuit':
                flash(f'Bienvenue {nom} ! Creez votre boutique.', 'success')
                return redirect(url_for('creer_boutique'))
            else:
                flash(f'Bienvenue {nom} ! Finalisez votre abonnement pour activer votre boutique.', 'success')
                return redirect(url_for('paiement_abonnement', plan=plan))
        for e in errors:
            flash(e, 'error')
    return render_template('pages/inscription.html', villes=villes, categories=categories, form=request.form if request.method=='POST' else {})

@app.route('/connexion', methods=['GET', 'POST'])
def connexion():
    if 'vendeur_id' in session:
        return redirect(url_for('dashboard'))
    villes, categories, quartiers = get_base_data()
    next_url = request.args.get('next', '')
    ref = request.args.get('ref', '').strip()
    if ref:
        session['ref_code'] = ref
    error = None
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        next_url = request.form.get('next', '')
        db = get_db()
        v = db.execute('SELECT * FROM vendeurs WHERE email=? OR telephone=?', (email, email)).fetchone()
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
        if v and v['google_id'] and not v['password_hash']:
            error = "Ce compte a été créé avec Google. Cliquez sur \"Continuer avec Google\"."
        else:
            error = 'Email ou mot de passe incorrect.'
    return render_template('pages/connexion.html', villes=villes, categories=categories, next=next_url, error=error)


@app.route('/mot-de-passe-oublie', methods=['GET', 'POST'])
def mot_de_passe_oublie():
    villes, categories, quartiers = get_base_data()
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        db = get_db()
        v = db.execute('SELECT * FROM vendeurs WHERE LOWER(email)=?', (email,)).fetchone()
        if v:
            token = str(uuid.uuid4())
            expires = (datetime.datetime.now() + datetime.timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')
            db.execute('INSERT INTO reset_tokens (vendeur_id, token, expires_at) VALUES (?,?,?)', (v['id'], token, expires))
            db.commit()
            lien = "{}".format(SITE_URL) + "/reinitialiser/{}".format(token)
            corps = "<h2>Reinitialisation mot de passe helloBiz</h2><p>Bonjour {},</p><p><a href=\"{}\">Cliquez ici</a> (valable 2h)</p>".format(v['nom'], lien)
            envoyer_email(v['email'], 'Reinitialisation mot de passe', corps)
        db.close()
        flash('Si cet email existe, un lien vous a ete envoye.', 'success')
        return redirect(url_for('connexion'))
    return render_template('pages/mot_de_passe_oublie.html', villes=villes, categories=categories)

@app.route('/reinitialiser/<token>', methods=['GET', 'POST'])
def reinitialiser_mdp(token):
    villes, categories, quartiers = get_base_data()
    db = get_db()
    rt = db.execute("SELECT rt.*, v.email FROM reset_tokens rt JOIN vendeurs v ON rt.vendeur_id=v.id WHERE rt.token=? AND rt.used=0 AND rt.expires_at > datetime('now')", (token,)).fetchone()
    if not rt:
        db.close()
        flash('Lien invalide ou expire.', 'error')
        return redirect(url_for('mot_de_passe_oublie'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        if len(password) < 6:
            flash('Mot de passe trop court.', 'error')
        elif password != password2:
            flash('Les mots de passe ne correspondent pas.', 'error')
        else:
            db.execute('UPDATE vendeurs SET password_hash=? WHERE id=?', (generate_password_hash(password), rt['vendeur_id']))
            db.execute('UPDATE reset_tokens SET used=1 WHERE token=?', (token,))
            db.commit()
            db.close()
            flash('Mot de passe mis a jour.', 'success')
            return redirect(url_for('connexion'))
    db.close()
    return render_template('pages/reinitialiser_mdp.html', token=token, villes=villes, categories=categories)

@app.route('/changer-mot-de-passe', methods=['GET', 'POST'])
@login_required
def changer_mot_de_passe():
    villes, categories, quartiers = get_base_data()
    if request.method == 'POST':
        ancien = request.form.get('ancien_mdp', '')
        nouveau = request.form.get('nouveau_mdp', '')
        confirmer = request.form.get('confirmer_mdp', '')
        db = get_db()
        v = db.execute('SELECT * FROM vendeurs WHERE id=?', (session['vendeur_id'],)).fetchone()
        if not check_password_hash(v['password_hash'], ancien):
            flash('Ancien mot de passe incorrect.', 'error')
        elif len(nouveau) < 6:
            flash('Nouveau mot de passe trop court.', 'error')
        elif nouveau != confirmer:
            flash('Les mots de passe ne correspondent pas.', 'error')
        else:
            db.execute('UPDATE vendeurs SET password_hash=? WHERE id=?', (generate_password_hash(nouveau), session['vendeur_id']))
            db.commit()
            db.close()
            flash('Mot de passe modifie.', 'success')
            return redirect(url_for('dashboard'))
        db.close()
    return render_template('pages/changer_mdp.html', villes=villes, categories=categories)


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
        plan     = session.get('vendeur_plan', 'gratuit')
        errors   = []
        if len(nom) < 2:   errors.append('Nom de boutique trop court.')
        if len(desc) < 20: errors.append('Description trop courte (min. 20 caracteres).')
        if not cat_id:      errors.append('Choisissez une categorie.')
        if not ville_id:    errors.append('Choisissez une ville.')
        if len(tel) < 8:    errors.append('Telephone invalide.')
        if not errors:
            slug = unique_slug(db, 'boutiques', slugify(nom))
            actif_initial = 0  # En attente de validation admin
            logo_fname=None
            banniere_fname=None
            if request.files.get('logo') and request.files['logo'].filename and allowed_file(request.files['logo'].filename):
                logo_fname=save_image(request.files['logo'])
            if request.files.get('banniere') and request.files['banniere'].filename and allowed_file(request.files['banniere'].filename):
                banniere_fname=save_image(request.files['banniere'])
            quartier_libre_b = form.get('quartier_libre', '').strip() or None
            if form.get('quartier_id') == 'autre' and quartier_libre_b:
                _q_slug = slugify(quartier_libre_b)
                db.execute('INSERT OR IGNORE INTO quartiers (slug, nom, ville_id) VALUES (?,?,?)',
                           (_q_slug, quartier_libre_b, ville_id))
                db.commit()
                _q_row = db.execute('SELECT id FROM quartiers WHERE slug=?', (_q_slug,)).fetchone()
                quartier_id_b = _q_row['id'] if _q_row else None
            else:
                quartier_id_b = form.get('quartier_id') or None
            db.execute('''INSERT INTO boutiques
                (slug,nom,description,categorie_id,ville_id,quartier_id,telephone,whatsapp,email,plan,vendeur_id,actif,logo,banniere)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''  ,
                (slug, nom, desc, cat_id, ville_id, quartier_id_b, tel, wa, vendeur['email'], plan,
                 session['vendeur_id'], actif_initial, logo_fname, banniere_fname))
            db.commit()
            b = db.execute('SELECT * FROM boutiques WHERE slug=?', (slug,)).fetchone()
            db.close()
            session.update({'boutique_id': b['id'], 'boutique_slug': b['slug']})
            if plan in ('starter', 'pro', 'premium', 'business'):
                flash('Boutique creee ! Finalisez votre abonnement ' + plan.capitalize() + ' pour l activer.', 'success')
                return redirect(url_for('paiement_abonnement', plan=plan))
            try:
                envoyer_email('ddieuval15@gmail.com', 'Nouvelle boutique helloBiz : ' + nom, '<p><b>Vendeur :</b> ' + session.get("vendeur_nom","?") + '<br><b>Boutique :</b> ' + nom + '<br><b>Plan :</b> ' + plan + '<br><b>Tel :</b> ' + tel + '</p>')
            except Exception:
                pass  # email non bloquant
            flash('Boutique creee ! Elle sera visible apres validation par notre equipe sous 24h.', 'success')
            return redirect(url_for('deposer_annonce'))
        for e in errors:
            flash(e, 'error')
    db.close()
    mode_recruteur = request.args.get('from') == 'emploi'
    return render_template('pages/creer_boutique.html',
        villes=villes, categories=categories, vendeur=vendeur, form=form,
        quartiers=quartiers, mode_recruteur=mode_recruteur)

# ════════════════════════════════════════════════════════════════════

@app.route('/modifier-boutique', methods=['GET', 'POST'])
@login_required
def modifier_boutique():
    db=get_db()
    b=db.execute('SELECT * FROM boutiques WHERE vendeur_id=?',(session['vendeur_id'],)).fetchone()
    if not b:
        db.close()
        return redirect(url_for('creer_boutique'))
    if request.method=='POST':
        form={k:v.strip() for k,v in request.form.items() if isinstance(v,str)}
        nom=form.get('nom',b['nom'])
        description=form.get('description',b['description'] or '')
        telephone=form.get('telephone',b['telephone'] or '')
        whatsapp=form.get('whatsapp',b['whatsapp'] or '')
        email=form.get('email',b['email'] or '')
        horaires=form.get('horaires',b['horaires'] or '')
        site_web=form.get('site_web',b['site_web'] or '')
        facebook=form.get('facebook',b['facebook'] or '')
        instagram=form.get('instagram',b['instagram'] or '')
        logo=b['logo']
        banniere=b['banniere']
        if request.files.get('logo') and request.files['logo'].filename and allowed_file(request.files['logo'].filename):
            logo=save_image(request.files['logo'])
        if request.files.get('banniere') and request.files['banniere'].filename and allowed_file(request.files['banniere'].filename):
            banniere=save_image(request.files['banniere'])
        errors=[]
        if len(nom)<2: errors.append('Le nom est trop court.')
        if not errors:
            db.execute("UPDATE boutiques SET nom=?,description=?,telephone=?,whatsapp=?,email=?,logo=?,banniere=?,horaires=?,site_web=?,facebook=?,instagram=? WHERE vendeur_id=?",
                (nom,description,telephone,whatsapp,email,logo,banniere,horaires,site_web,facebook,instagram,session['vendeur_id']))
            db.commit()
            db.close()
            flash('Boutique mise a jour.','success')
            return redirect(url_for('dashboard'))
        for e in errors: flash(e,'error')
    villes,categories,quartiers=get_base_data()
    db.close()
    return render_template('pages/modifier_boutique.html',b=b,villes=villes,categories=categories)

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
    if not vendeur['parrain_code']:
        import uuid
        _pc = uuid.uuid4().hex[:8].upper()
        db.execute('UPDATE vendeurs SET parrain_code=? WHERE id=?', (_pc, session['vendeur_id']))
        db.commit()
        vendeur = db.execute('SELECT * FROM vendeurs WHERE id=?', (session['vendeur_id'],)).fetchone()
    nb_filleuls = db.execute('SELECT COUNT(*) as n FROM vendeurs WHERE parrain_id=?', (session['vendeur_id'],)).fetchone()['n']
    _comm_rows = db.execute("SELECT b.plan, COUNT(*) as nb FROM boutiques b JOIN vendeurs r ON b.vendeur_id=r.id WHERE r.parrain_id=? AND b.plan!='gratuit' GROUP BY b.plan", (session['vendeur_id'],)).fetchall()
    _PRIX = {'starter':1250,'pro':3000,'premium':6000,'business':25000}
    commission_due = int(sum(_PRIX.get(r['plan'],0)*r['nb']*0.10 for r in _comm_rows))
    nb_fp = db.execute("SELECT COUNT(*) as n FROM boutiques b JOIN vendeurs r ON b.vendeur_id=r.id WHERE r.parrain_id=? AND b.plan!='gratuit'", (session['vendeur_id'],)).fetchone()['n']
    remise_pct = min(nb_fp * 5, 10)
    parrain_link = f"{SITE_URL}/inscription?ref={vendeur['parrain_code']}"
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
    from datetime import datetime as _dt
    plan_score = 40 if b['plan'] in ('premium','business') else 20 if b['plan']=='pro' else 10 if b['plan']=='starter' else 0
    badge_score = 10 if b['badge_verifie'] else 0
    positionnement = []
    for a in annonces_list:
        if a['statut'] != 'active':
            continue
        try:
            created = _dt.strptime(a['created_at'][:19], '%Y-%m-%d %H:%M:%S')
            days_old = (_dt.now() - created).days
        except Exception:
            days_old = 999
        fresh_score = 30 if days_old < 3 else 20 if days_old < 7 else 10 if days_old < 30 else 0
        vues = a['vues'] or 0
        views_score = 15 if vues > 100 else 10 if vues > 50 else 5 if vues > 10 else 0
        score = plan_score + fresh_score + views_score + badge_score
        rang_row = db.execute('''
            SELECT COUNT(*) + 1 as rang FROM annonces a2
            LEFT JOIN boutiques b2 ON a2.boutique_id=b2.id
            WHERE a2.statut="active" AND a2.categorie_id=? AND a2.id != ?
            AND (
                (CASE WHEN b2.plan IN ("premium","business") THEN 40 WHEN b2.plan="pro" THEN 20 WHEN b2.plan="starter" THEN 10 ELSE 0 END)
                + (CASE WHEN a2.created_at >= datetime("now","-3 days") THEN 30 WHEN a2.created_at >= datetime("now","-7 days") THEN 20 WHEN a2.created_at >= datetime("now","-30 days") THEN 10 ELSE 0 END)
                + (CASE WHEN a2.vues > 100 THEN 15 WHEN a2.vues > 50 THEN 10 WHEN a2.vues > 10 THEN 5 ELSE 0 END)
                + (CASE WHEN b2.badge_verifie=1 THEN 10 ELSE 0 END)
            ) > ?
        ''', (a['categorie_id'], a['id'], score)).fetchone()
        rang = rang_row['rang'] if rang_row else 1
        total_row = db.execute('SELECT COUNT(*) as n FROM annonces WHERE statut="active" AND categorie_id=?', (a['categorie_id'],)).fetchone()
        total_cat = total_row['n'] if total_row else 1
        has_photo = db.execute('SELECT id FROM photos WHERE annonce_id=? LIMIT 1', (a['id'],)).fetchone()
        conseils = []
        if not has_photo:
            conseils.append({'type': 'photo', 'text': 'Ajoutez une photo — les annonces avec photo ont 3x plus de vues'})
        if vues < 5 and days_old > 3:
            conseils.append({'type': 'titre', 'text': 'Peu de vues — essayez un titre plus precis'})
        if days_old > 25:
            conseils.append({'type': 'renouveler', 'text': 'Annonce ancienne — renouvelez-la pour remonter'})
        if b['plan'] == 'starter' and rang > 5:
            conseils.append({'type': 'upgrade', 'text': 'Plan Pro = +20 pts de visibilite'})
        positionnement.append({
            'annonce': a, 'score': score, 'score_max': 95,
            'score_pct': round(score / 95 * 100),
            'rang': rang, 'total_cat': total_cat,
            'conseils': conseils, 'days_old': days_old,
        })
    db.close()
    
    # === Dashboard extras ===
    _champs = {
        'Nom': bool(b.get('nom') if isinstance(b, dict) else getattr(b, 'nom', None)),
        'Description': bool(b.get('description') if isinstance(b, dict) else getattr(b, 'description', None)),
        'Telephone': bool(b.get('telephone') if isinstance(b, dict) else getattr(b, 'telephone', None)),
        'WhatsApp': bool(b.get('whatsapp') if isinstance(b, dict) else getattr(b, 'whatsapp', None)),
        'Logo': bool(b.get('logo') if isinstance(b, dict) else getattr(b, 'logo', None)),
        'Horaires': bool(b.get('horaires') if isinstance(b, dict) else getattr(b, 'horaires', None)),
        'Categorie': bool(b.get('categorie_id') if isinstance(b, dict) else getattr(b, 'categorie_id', None)),
        'Ville': bool(b.get('ville_id') if isinstance(b, dict) else getattr(b, 'ville_id', None)),
    }
    score_completude = int(sum(_champs.values()) / len(_champs) * 100)
    champs_manquants = [k for k, v in _champs.items() if not v]
    try:
        import sqlite3 as _s3; _c3 = _s3.connect(DB_PATH)
        _bid3 = b.get('id') if isinstance(b, dict) else getattr(b, 'id', 0)
        clics_wa_7j = _c3.execute(
            "SELECT COUNT(*) FROM clics_whatsapp WHERE boutique_id=? AND created_at >= datetime('now','-7 days')",
            (_bid3,)).fetchone()[0]
        clics_wa_total = _c3.execute(
            "SELECT COUNT(*) FROM clics_whatsapp WHERE boutique_id=?", (_bid3,)).fetchone()[0]
        top_annonces = [{'titre': r[0], 'vues': r[1], 'slug': r[2], 'prix': r[3], 'prix_type': r[4]}
            for r in _c3.execute(
                "SELECT titre,vues,slug,prix,prix_type FROM annonces WHERE boutique_id=? AND statut='active' ORDER BY vues DESC LIMIT 3",
                (_bid3,)).fetchall()]
        vues_sem = _c3.execute(
            "SELECT COALESCE(SUM(vues),0) FROM annonces WHERE boutique_id=? AND statut='active'",
            (_bid3,)).fetchone()[0]
        tendance_pct = 100 if vues_sem > 0 else 0
        _c3.close()
    except Exception as _e3:
        clics_wa_7j = clics_wa_total = 0; top_annonces = []; vues_sem = tendance_pct = 0
    # === Fin Dashboard extras ===
    return render_template('pages/dashboard.html',
        vendeur=vendeur, boutique=b, annonces=annonces_list, stats=stats,
        villes=villes, categories=categories, plans_tarifs=PLANS_TARIFS,
        positionnement=positionnement, parrain_link=parrain_link, nb_filleuls=nb_filleuls, commission_due=commission_due, remise_pct=remise_pct, score_completude=score_completude, champs_manquants=champs_manquants, clics_wa_7j=clics_wa_7j, clics_wa_total=clics_wa_total, top_annonces=top_annonces, vues_cette_sem=vues_sem, tendance_pct=tendance_pct)

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
    return render_template('pages/stats.html', ca_total=0, ca_mois=0, nb_favoris=0, nb_messages=0, semaines=[], vues_28j=[],
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
    # Quota daily reset pour plan gratuit
    _cfg = db.execute("SELECT valeur FROM site_config WHERE cle='plan_gratuit_periode'").fetchone()
    _periode = _cfg[0] if _cfg else 'monthly'
    if b['plan'] == 'gratuit' and _periode == 'daily':
        import datetime as _dt
        _now = _dt.datetime.now()
        _reset = b['quota_reset_at']
        if _reset:
            try:
                _reset_dt = _dt.datetime.strptime(str(_reset)[:19], '%Y-%m-%d %H:%M:%S')
            except:
                _reset_dt = _now - _dt.timedelta(hours=25)
            if (_now - _reset_dt).total_seconds() >= 86400:
                _reset = _now.strftime('%Y-%m-%d %H:%M:%S')
                db.execute("UPDATE boutiques SET quota_reset_at=? WHERE id=?", (_reset, b['id']))
                db.commit()
        else:
            _reset = _now.strftime('%Y-%m-%d %H:%M:%S')
            db.execute("UPDATE boutiques SET quota_reset_at=? WHERE id=?", (_reset, b['id']))
            db.commit()
        nb = db.execute('SELECT COUNT(*) FROM annonces WHERE boutique_id=? AND statut="active" AND created_at >= ?', (b['id'], _reset)).fetchone()[0]
    else:
        nb = db.execute('SELECT COUNT(*) FROM annonces WHERE boutique_id=? AND statut="active"', (b['id'],)).fetchone()[0]
    limite    = PLAN_LIMITS.get(b['plan'], 5)
    restantes = max(0, limite - nb)
    plan_photos = {'starter': 3, 'pro': 8, 'premium': 20, 'business': 30}
    max_photos  = plan_photos.get(b['plan'], 3)
    mode_simple = (b['plan'] == 'starter')
    form = {}
    if request.method == 'POST':
        form = {k: v.strip() for k, v in request.form.items() if isinstance(v, str)}
        is_mode_simple = form.get('mode_simple') == '1'
        titre       = form.get('titre', '')
        desc        = form.get('description', '')
        prix        = float(form.get('prix', '0') or 0)
        prix_type   = form.get('prix_type', 'fixe')
        cat_id      = form.get('categorie_id', str(b['categorie_id']))
        ville_id    = form.get('ville_id') or str(b['ville_id'])
        quartier_id = form.get('quartier_id') or None
        quartier_libre = form.get('quartier_libre', '') or ''
        disponibilite = form.get('disponibilite', '') or None
        files       = request.files.getlist('photos')
        # Mode simple : auto-compléter la description si trop courte
        if is_mode_simple and len(desc) < 20:
            desc = titre + ('. ' + desc if desc else '. Contactez-moi sur WhatsApp pour plus de détails.')
            if len(desc) < 20:
                desc = titre + '. Contactez-moi sur WhatsApp pour plus de détails.'
        errors = []
        # Champs spécifiques Emploi
        emploi_type    = form.get('emploi_type', '') or None
        emploi_secteur = form.get('emploi_secteur', '') or None
        emploi_salaire = form.get('emploi_salaire', '') or None
        urgent         = 1 if form.get('urgent') == '1' else 0
        # Vérifier si catégorie emploi
        cat_emploi = db.execute('SELECT id FROM categories WHERE slug="emploi"').fetchone()
        cat_services = db.execute('SELECT id FROM categories WHERE slug="services"').fetchone()
        is_emploi = cat_emploi and str(cat_id) == str(cat_emploi['id'])
        is_services = cat_services and str(cat_id) == str(cat_services['id'])
        if is_emploi:
            if not emploi_type:    errors.append('Précisez si c\'est une offre ou une recherche d\'emploi.')
            if not emploi_secteur: errors.append('Le secteur d\'activité est obligatoire pour une annonce Emploi.')
        if len(titre) < 5:  errors.append('Titre trop court (min. 5 caracteres).')
        if not is_mode_simple and len(desc) < 20:  errors.append('Description trop courte (min. 20 caracteres).')
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
                 emploi_type,emploi_secteur,emploi_salaire,expire_at,disponibilite,quartier_libre)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (slug, titre, desc, prix, prix_type, cat_id, ville_id, b['id'], quartier_id,
                 emploi_type, emploi_secteur, emploi_salaire, expire_at, disponibilite, quartier_libre))
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
            try:
                envoyer_email('ddieuval15@gmail.com', 'Nouvelle annonce helloBiz : ' + titre, '<p><b>Vendeur :</b> ' + session.get("vendeur_nom","?") + '<br><b>Boutique :</b> ' + b["nom"] + '<br><b>Titre :</b> ' + titre + '<br><b>Lien :</b> https://hellobizcongo.com/annonce/' + slug + '</p>')
            except Exception:
                pass  # email non bloquant
            flash('Annonce publiee avec succes !', 'success')
            return redirect(url_for('dashboard'))
        for e in errors:
            flash(e, 'error')
    db.close()
    return render_template('pages/deposer_annonce.html',
        villes=villes, categories=categories, quartiers=quartiers, boutique=b,
        annonces_restantes=restantes, max_photos=max_photos, form=form,
        mode_simple=mode_simple)

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
        quartier_libre = request.form.get('quartier_libre', '').strip() or None
        if quartier_id == 'autre': quartier_id = None or None
        urgent      = 1 if request.form.get('urgent') == '1' else 0
        suppr_ids   = request.form.getlist('supprimer_photo')
        new_files   = request.files.getlist('photos')
        if len(titre) < 5:  errors.append('Titre trop court.')
        if len(desc) < 20:  errors.append('Description trop courte.')
        disponibilite_edit = request.form.get('disponibilite', '') or None
        if not errors:
            db.execute('''UPDATE annonces SET titre=?, description=?, prix=?, prix_type=?,
                categorie_id=?, ville_id=?, quartier_id=?, disponibilite=?, quartier_libre=? WHERE id=?''',
                (titre, desc, prix, prix_type, cat_id, ville_id, quartier_id, disponibilite_edit, quartier_libre, a['id']))
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
def mes_favoris():
    villes, categories, quartiers = get_base_data()
    return render_template('pages/mes_favoris.html', villes=villes, categories=categories)

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
            conv_row = db.execute('SELECT * FROM conversations WHERE id=?',(conv_id,)).fetchone()
            if conv_row:
                sender_id = session['vendeur_id']
                recip_id = conv_row['destinataire_id'] if sender_id == conv_row['expediteur_id'] else conv_row['expediteur_id']
                recip = db.execute('SELECT nom,email FROM vendeurs WHERE id=?',(recip_id,)).fetchone()
                sender = db.execute('SELECT nom FROM vendeurs WHERE id=?',(sender_id,)).fetchone()
                if recip and recip['email']:
                    corps = '<p>Bonjour ' + (recip['nom'] or '') + ',</p><p><b>' + (sender['nom'] if sender else 'Quelqu un') + '</b> vous a envoye un message.</p><p><a href="https://hellobizcongo.com/messages/' + str(conv_id) + '">Voir le message</a></p>'
                    envoyer_email(recip['email'], 'Nouveau message sur helloBiz', corps)
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
        recip2 = db.execute('SELECT nom,email FROM vendeurs WHERE id=?',(ann['proprietaire_id'],)).fetchone()
        sender2 = db.execute('SELECT nom FROM vendeurs WHERE id=?',(session['vendeur_id'],)).fetchone()
        if recip2 and recip2['email']:
            corps2 = '<p>Bonjour ' + (recip2['nom'] or '') + ',</p><p><b>' + (sender2['nom'] if sender2 else 'Quelqu un') + '</b> vous a envoye un message via helloBiz.</p><p><a href="https://hellobizcongo.com/messages/' + str(conv_id) + '">Voir le message</a></p>'
            envoyer_email(recip2['email'], 'Nouveau message sur helloBiz', corps2)
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
    if tarif['prix'] == 0:
        db2 = get_db()
        db2.execute('UPDATE boutiques SET plan=? WHERE vendeur_id=?', (plan, session['vendeur_id']))
        db2.commit()
        db2.close()
        flash(f"Plan {tarif['nom']} activé avec succès.", 'success')
        return redirect(url_for('dashboard'))
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
    if tarif['prix'] == 0:
        db2 = get_db()
        db2.execute('UPDATE boutiques SET plan=? WHERE vendeur_id=?', (plan, session['vendeur_id']))
        db2.commit()
        db2.close()
        flash(f"Plan {tarif['nom']} activé avec succès.", 'success')
        return redirect(url_for('dashboard'))
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
    from datetime import datetime
    mois_debut = datetime.now().replace(day=1).strftime('%Y-%m-01')
    paiements_attente = db.execute(
        "SELECT COUNT(*) FROM paiements WHERE statut='en_attente'"
    ).fetchone()[0]
    ca_mois = db.execute(
        "SELECT COALESCE(SUM(montant),0) FROM paiements WHERE statut='confirme' AND created_at>=?",
        (mois_debut,)
    ).fetchone()[0]
    boutiques_attente = db.execute(
        "SELECT COUNT(*) FROM boutiques WHERE actif=0"
    ).fetchone()[0]

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
        'ca_mois':           ca_mois,
        'paiements_attente': paiements_attente,
        'boutiques_attente': boutiques_attente,
        'nb_bugs_ouverts':   db.execute("SELECT COUNT(*) FROM bug_reports WHERE statut='ouvert'").fetchone()[0],
    'visites_today':      db.execute("SELECT COUNT(*) FROM site_visits WHERE DATE(visited_at)=DATE('now')").fetchone()[0],
    'visites_7j':         db.execute("SELECT COUNT(*) FROM site_visits WHERE visited_at >= DATETIME('now','-7 days')").fetchone()[0],
    'visites_30j':        db.execute("SELECT COUNT(*) FROM site_visits WHERE visited_at >= DATETIME('now','-30 days')").fetchone()[0],
    'visites_total':      db.execute("SELECT COUNT(*) FROM site_visits").fetchone()[0],
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
    boutiques_en_attente = db.execute('''
        SELECT b.*, v.nom as vendeur_nom, v.telephone as vendeur_tel
        FROM boutiques b JOIN vendeurs v ON b.vendeur_id=v.id
        WHERE b.actif=0 ORDER BY b.created_at DESC
    ''').fetchall()
    _cfg_periode = db.execute("SELECT valeur FROM site_config WHERE cle='plan_gratuit_periode'").fetchone()
    plan_gratuit_periode = _cfg_periode[0] if _cfg_periode else 'monthly'
    ambassadeurs = db.execute('''SELECT v.id, v.nom, v.ref_code, v.is_ambassadeur, (SELECT COUNT(*) FROM boutiques b WHERE b.vendeur_id IN (SELECT id FROM vendeurs WHERE parrain_id=v.id) AND b.plan!='gratuit') as nb_recrutes FROM vendeurs v WHERE v.is_ambassadeur=1 ORDER BY nb_recrutes DESC''').fetchall()
    offres_emploi = db.execute("""
        SELECT a.id, a.titre, a.slug, a.statut, a.created_at,
               a.emploi_type, a.emploi_secteur,
               b.nom as boutique_nom, v2.nom as ville_nom
        FROM annonces a
        JOIN villes v2 ON a.ville_id = v2.id
        LEFT JOIN boutiques b ON a.boutique_id = b.id
        WHERE a.categorie_id = (SELECT id FROM categories WHERE slug='emploi')
        ORDER BY a.created_at DESC
    """).fetchall()
    stats['nb_emploi'] = len(offres_emploi)
    stats['nb_emploi_attente'] = sum(1 for o in offres_emploi if o['statut'] == 'en_attente')
    db.close()
    return render_template('pages/admin.html', stats=stats, vendeurs=vendeurs, plan_gratuit_periode=plan_gratuit_periode,
        boutiques=boutiques_all, annonces=annonces_all, paiements=paiements_all,
        offres_emploi=offres_emploi, villes=villes, categories=categories,
            boutiques_en_attente=boutiques_en_attente, ambassadeurs=ambassadeurs)

@app.route('/admin/offre-rapide', methods=['GET','POST'])
@admin_required
def admin_offre_rapide():
    db = get_db()
    if request.method == 'POST':
        titre       = request.form.get('titre','').strip()
        secteur     = request.form.get('secteur','').strip()
        type_emploi = request.form.get('type_emploi','Recrutement').strip()
        description = request.form.get('description','').strip()
        whatsapp    = request.form.get('whatsapp','').strip()
        salaire     = request.form.get('salaire','').strip() or None

        if not titre or not secteur or not description or not whatsapp:
            flash('Merci de remplir tous les champs obligatoires.', 'error')
            db.close()
            return render_template('pages/offre_rapide.html')

        # Récupérer IDs nécessaires
        cat = db.execute("SELECT id FROM categories WHERE slug='emploi'").fetchone()
        ville = db.execute("SELECT id FROM villes WHERE slug='pointe-noire'").fetchone()
        if not ville:
            ville = db.execute("SELECT id FROM villes LIMIT 1").fetchone()
        boutique = db.execute("SELECT id FROM boutiques WHERE vendeur_id=(SELECT id FROM vendeurs WHERE is_admin=1 LIMIT 1) LIMIT 1").fetchone()

        if not cat or not ville or not boutique:
            flash('Erreur configuration. Contactez le support.', 'error')
            db.close()
            return render_template('pages/offre_rapide.html')

        # Générer slug unique
        import re, unicodedata, uuid
        def make_slug(text):
            t = unicodedata.normalize('NFD', text).encode('ascii','ignore').decode()
            t = re.sub(r'[^\w\s-]','',t.lower())
            t = re.sub(r'[\s_-]+','-',t).strip('-')
            return t
        base_slug = make_slug(titre)[:60]
        slug = base_slug + '-' + uuid.uuid4().hex[:6]

        import datetime
        expire = (datetime.datetime.now() + datetime.timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S')

        db.execute("""
            INSERT INTO annonces
              (titre, slug, description, categorie_id, ville_id, boutique_id,
               statut, emploi_type, emploi_secteur, emploi_salaire,
               whatsapp, telephone, expire_at, created_at)
            VALUES (?,?,?,?,?,?,'active',?,?,?,?,?,?,datetime('now'))
        """, (titre, slug, description, cat['id'], ville['id'], boutique['id'],
              type_emploi, secteur, salaire, whatsapp, whatsapp, expire))
        db.commit()
        ann_id = db.execute('SELECT id FROM annonces WHERE slug=?', (slug,)).fetchone()['id']

        # Sauvegarder l'affiche si uploadée
        affiche = request.files.get('affiche')
        if affiche and affiche.filename:
            try:
                fname = save_image(affiche)
                db.execute('INSERT INTO photos (annonce_id, url, principale) VALUES (?,?,1)',
                           (ann_id, fname))
                db.commit()
            except Exception as e:
                print(f'Affiche error: {e}')

        db.close()
        flash(f'Offre "{titre}" publiée avec succès !', 'success')
        return redirect(url_for('admin_offre_rapide'))

    db.close()
    return render_template('pages/offre_rapide.html')

@app.route('/admin/emploi/<int:annonce_id>/supprimer', methods=['POST'])
@admin_required
def admin_emploi_supprimer(annonce_id):
    db = get_db()
    db.execute("DELETE FROM annonces WHERE id=? AND categorie_id=(SELECT id FROM categories WHERE slug='emploi')", (annonce_id,))
    db.commit()
    db.close()
    flash("Offre supprimee.", 'success')
    return redirect(url_for('admin') + '#emploi')

@app.route('/admin/emploi/<int:annonce_id>/toggle', methods=['POST'])
@admin_required
def admin_emploi_toggle(annonce_id):
    db = get_db()
    a = db.execute('SELECT statut FROM annonces WHERE id=?', (annonce_id,)).fetchone()
    if a:
        nouveau = 'masquee' if a['statut'] == 'active' else 'active'
        db.execute('UPDATE annonces SET statut=? WHERE id=?', (nouveau, annonce_id))
        db.commit()
    db.close()
    return redirect(url_for('admin') + '#emploi')


# ── Page publique soumission offre d'emploi ──────────────────────────
@app.route('/soumettre-offre', methods=['GET','POST'])
def soumettre_offre():
    db = get_db()
    if request.method == 'POST':
        titre       = request.form.get('titre','').strip()
        secteur     = request.form.get('secteur','').strip()
        type_emploi = request.form.get('type_emploi','Recrutement').strip()
        description = request.form.get('description','').strip()
        whatsapp    = request.form.get('whatsapp','').strip()
        salaire     = request.form.get('salaire','').strip() or None
        if not titre or not secteur or not description or not whatsapp:
            flash('Merci de remplir tous les champs obligatoires.', 'error')
            db.close()
            return render_template('pages/soumettre_offre.html')
        cat   = db.execute("SELECT id FROM categories WHERE slug='emploi'").fetchone()
        ville = db.execute("SELECT id FROM villes WHERE slug='pointe-noire'").fetchone()
        if not ville:
            ville = db.execute("SELECT id FROM villes LIMIT 1").fetchone()
        boutique = db.execute(
            "SELECT id FROM boutiques WHERE vendeur_id=(SELECT id FROM vendeurs WHERE is_admin=1 LIMIT 1) LIMIT 1"
        ).fetchone()
        if not cat or not ville or not boutique:
            flash('Erreur configuration.', 'error')
            db.close()
            return render_template('pages/soumettre_offre.html')
        import unicodedata as _ud2
        def _slug(text):
            t = _ud2.normalize('NFD', text).encode('ascii','ignore').decode()
            t = re.sub(r'[^\w\s-]','',t.lower())
            t = re.sub(r'[\s_-]+','-',t).strip('-')
            return t
        slug = _slug(titre)[:60] + '-' + uuid.uuid4().hex[:6]
        expire = (datetime.datetime.now() + datetime.timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S')
        db.execute(
            """INSERT INTO annonces
               (titre, slug, description, categorie_id, ville_id, boutique_id,
                statut, emploi_type, emploi_secteur, emploi_salaire,
                whatsapp, telephone, expire_at, created_at)
               VALUES (?,?,?,?,?,?,'en_attente',?,?,?,?,?,?,datetime('now'))""",
            (titre, slug, description, cat['id'], ville['id'], boutique['id'],
             type_emploi, secteur, salaire, whatsapp, whatsapp, expire)
        )
        db.commit()
        ann_id = db.execute('SELECT id FROM annonces WHERE slug=?', (slug,)).fetchone()['id']
        affiche = request.files.get('affiche')
        if affiche and affiche.filename:
            try:
                fname = save_image(affiche)
                db.execute('INSERT INTO photos (annonce_id, url, principale) VALUES (?,?,1)',
                           (ann_id, fname))
                db.commit()
            except Exception as e:
                print(f'Affiche error: {e}')
        db.close()
        flash(f'Offre "{titre}" envoyée avec succès !', 'success')
        return redirect('/soumettre-offre')
    db.close()
    return render_template('pages/soumettre_offre.html')


# ── Approuver une offre en attente ───────────────────────────────────
@app.route('/admin/emploi/<int:annonce_id>/approuver', methods=['POST'])
@admin_required
def admin_emploi_approuver(annonce_id):
    db = get_db()
    db.execute("UPDATE annonces SET statut='active' WHERE id=?", (annonce_id,))
    db.commit()
    db.close()
    flash("Offre approuvée et publiée.", 'success')
    return redirect(url_for('admin') + '#emploi')



# ── Page publique soumission annonce immobilière ─────────────────────
@app.route('/soumettre-immo', methods=['GET','POST'])
def soumettre_immo():
    db = get_db()
    if request.method == 'POST':
        titre       = request.form.get('titre','').strip()
        transaction = request.form.get('transaction','Location').strip()
        type_bien   = request.form.get('type_bien','').strip()
        quartier    = request.form.get('quartier','').strip()
        description = request.form.get('description','').strip()
        whatsapp    = request.form.get('whatsapp','').strip()
        prix_raw    = request.form.get('prix','').strip()
        prix_type   = request.form.get('prix_type','fixe').strip()
        if not titre or not type_bien or not quartier or not description or not whatsapp:
            flash('Merci de remplir tous les champs obligatoires.', 'error')
            db.close()
            return render_template('pages/soumettre_immo.html')
        try:
            prix = float(prix_raw) if prix_raw else 0.0
        except ValueError:
            prix = 0.0
        cat   = db.execute("SELECT id FROM categories WHERE slug='immobilier'").fetchone()
        ville = db.execute("SELECT id FROM villes WHERE slug='pointe-noire'").fetchone()
        if not ville:
            ville = db.execute("SELECT id FROM villes LIMIT 1").fetchone()
        boutique = db.execute(
            "SELECT id FROM boutiques WHERE vendeur_id=(SELECT id FROM vendeurs WHERE is_admin=1 LIMIT 1) LIMIT 1"
        ).fetchone()
        if not cat or not ville or not boutique:
            flash('Erreur configuration.', 'error')
            db.close()
            return render_template('pages/soumettre_immo.html')
        import unicodedata as _ud3
        def _slug3(text):
            t = _ud3.normalize('NFD', text).encode('ascii','ignore').decode()
            t = re.sub(r'[^\w\s-]','',t.lower())
            t = re.sub(r'[\s_-]+','-',t).strip('-')
            return t
        desc_full = f"[{transaction} — {type_bien}] {quartier}\n\n{description}"
        slug = _slug3(titre)[:60] + '-' + uuid.uuid4().hex[:6]
        expire = (datetime.datetime.now() + datetime.timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')
        db.execute(
            """INSERT INTO annonces
               (titre, slug, description, prix, prix_type, categorie_id, ville_id, boutique_id,
                statut, whatsapp, telephone, expire_at, created_at)
               VALUES (?,?,?,?,?,?,?,?,'en_attente',?,?,?,datetime('now'))""",
            (titre, slug, desc_full, prix, prix_type, cat['id'], ville['id'], boutique['id'],
             whatsapp, whatsapp, expire)
        )
        db.commit()
        ann_id = db.execute('SELECT id FROM annonces WHERE slug=?', (slug,)).fetchone()['id']
        photo = request.files.get('photo')
        if photo and photo.filename:
            try:
                fname = save_image(photo)
                db.execute('INSERT INTO photos (annonce_id, url, principale) VALUES (?,?,1)',
                           (ann_id, fname))
                db.commit()
            except Exception as e:
                print(f'Photo immo error: {e}')
        db.close()
        flash(f'Annonce "{titre}" envoyée avec succès !', 'success')
        return redirect('/soumettre-immo')
    db.close()
    return render_template('pages/soumettre_immo.html')


# ── Approuver une annonce immo en attente ────────────────────────────
@app.route('/admin/immo/<int:annonce_id>/approuver', methods=['POST'])
@admin_required
def admin_immo_approuver(annonce_id):
    db = get_db()
    db.execute("UPDATE annonces SET statut='active' WHERE id=?", (annonce_id,))
    db.commit()
    db.close()
    flash("Annonce approuvée et publiée.", 'success')
    return redirect(url_for('admin') + '#en-attente')


# ── Page acquisition commerçants ─────────────────────────────────────
@app.route('/commercants')
def commercants():
    return render_template('pages/commercants.html')


@app.route('/admin/boutique/<int:boutique_id>/valider', methods=['POST'])
@admin_required
def admin_boutique_valider(boutique_id):
    db = get_db()
    b = db.execute('SELECT b.*, v.email as vendeur_email, v.nom as vendeur_nom FROM boutiques b JOIN vendeurs v ON b.vendeur_id=v.id WHERE b.id=?', (boutique_id,)).fetchone()
    db.execute('UPDATE boutiques SET actif=1 WHERE id=?', (boutique_id,))
    db.commit()
    db.close()
    if b and b['vendeur_email']:
        envoyer_email(b['vendeur_email'], 'Votre boutique helloBiz est validee !',
            '<p>Bonjour ' + b['vendeur_nom'] + ',<br>Votre boutique <b>' + b['nom'] + '</b> est maintenant visible sur helloBiz Congo.<br>'
            '<a href="https://hellobizcongo.com/boutique/' + b['slug'] + '">Voir ma boutique</a></p>')
    flash('Boutique validee et activee.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/boutique/<int:boutique_id>/rejeter', methods=['POST'])
@admin_required
def admin_boutique_rejeter(boutique_id):
    db = get_db()
    db.execute('DELETE FROM annonces WHERE boutique_id=?', (boutique_id,))
    db.execute('DELETE FROM boutiques WHERE id=?', (boutique_id,))
    db.commit()
    db.close()
    flash('Boutique rejetee et supprimee.', 'warning')
    return redirect(url_for('admin'))

@app.route('/admin/boutique/<int:boutique_id>/valider', methods=['POST'])
@admin_required
def admin_valider_boutique(boutique_id):
    action = request.form.get('action', 'valider')
    db = get_db()
    b = db.execute('SELECT b.*, v.email as vendeur_email, v.nom as vendeur_nom FROM boutiques b JOIN vendeurs v ON b.vendeur_id=v.id WHERE b.id=?', (boutique_id,)).fetchone()
    if b:
        if action == 'valider':
            db.execute('UPDATE boutiques SET actif=1 WHERE id=?', (boutique_id,))
            db.commit()
            if b['vendeur_email']:
                corps = f'''<p>Bonjour {b['vendeur_nom']},</p>
<p>Votre boutique <strong>{b['nom']}</strong> a été validée et est maintenant visible sur helloBiz Congo.</p>
<p><a href="https://hellobizcongo.com/boutique/{b['slug']}">Voir ma boutique</a></p>
<p>L'équipe helloBiz</p>'''
                envoyer_email(b['vendeur_email'], 'Votre boutique helloBiz est validée !', corps)
            flash(f'Boutique "{b["nom"]}" validée et activée.', 'success')
        else:
            db.execute('DELETE FROM boutiques WHERE id=?', (boutique_id,))
            db.commit()
            flash(f'Boutique refusée et supprimée.', 'warning')
    db.close()
    return redirect(url_for('admin') + '#boutiques')

@app.route('/signaler-bug', methods=['GET', 'POST'])
@login_required
def signaler_bug():
    if request.method == 'POST':
        type_bug = request.form.get('type', '').strip()
        description = request.form.get('description', '').strip()
        url = request.form.get('url', '').strip()
        if type_bug and description:
            db = get_db()
            db.execute('INSERT INTO bug_reports (vendeur_id, type, description, url) VALUES (?,?,?,?)',
                       (session['vendeur_id'], type_bug, description, url))
            db.commit()
            db.close()
            flash('Signalement envoyé. Merci !', 'success')
            return redirect(url_for('dashboard'))
        flash('Veuillez remplir tous les champs.', 'error')
    return render_template('pages/signaler_bug.html')

@app.route('/admin/bugs')
@admin_required
def admin_bugs():
    db = get_db()
    bugs = db.execute('''SELECT br.*, v.nom as vendeur_nom, v.email as vendeur_email
        FROM bug_reports br LEFT JOIN vendeurs v ON br.vendeur_id=v.id
        ORDER BY br.created_at DESC''').fetchall()
    db.close()
    return render_template('pages/admin_bugs.html', bugs=bugs)

@app.route('/admin/bugs/<int:bug_id>/statut', methods=['POST'])
@admin_required
def admin_bug_statut(bug_id):
    statut = request.form.get('statut', 'ouvert')
    db = get_db()
    db.execute('UPDATE bug_reports SET statut=? WHERE id=?', (statut, bug_id))
    db.commit()
    db.close()
    return redirect(url_for('admin_bugs'))

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


@app.route('/admin/vendeur/<int:vid>/toggle-ambassadeur', methods=['POST'])
def toggle_ambassadeur(vid):
    if not session.get('is_admin'):return redirect(url_for('index'))
    db=get_db()
    v=db.execute('SELECT is_ambassadeur FROM vendeurs WHERE id=?',(vid,)).fetchone()
    if v:db.execute('UPDATE vendeurs SET is_ambassadeur=? WHERE id=?',(0 if v['is_ambassadeur'] else 1,vid));db.commit()
    db.close()
    return redirect(request.referrer or url_for('admin'))



@app.route('/admin/vendeur/<int:vid>/reset-mdp', methods=['POST'])
def admin_reset_mdp(vid):
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    import secrets, string
    chars = string.ascii_letters + string.digits
    new_mdp = ''.join(secrets.choice(chars) for _ in range(10))
    db = get_db()
    v = db.execute('SELECT nom FROM vendeurs WHERE id=?', (vid,)).fetchone()
    db.execute('UPDATE vendeurs SET password_hash=? WHERE id=?', (generate_password_hash(new_mdp), vid))
    db.commit()
    db.close()
    nom = v['nom'] if v else 'Vendeur'
    flash(f'MDP reinitialise pour {nom} : {new_mdp}', 'success')
    return redirect(request.referrer or url_for('admin'))


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
    # Traçabilité changement manuel admin
    b_info = db.execute('SELECT vendeur_id, nom FROM boutiques WHERE id=?', (boutique_id,)).fetchone()
    if b_info:
        import datetime
        ref = f'ADMIN-{boutique_id}-{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}'
        db.execute(
            """INSERT INTO paiements (reference, vendeur_id, boutique_id, type, montant, operateur, telephone, statut, plan_cible)
               VALUES (?, ?, ?, 'manuel_admin', 0, 'Admin', '', 'confirme', ?)""",
            (ref, b_info['vendeur_id'], boutique_id, plan)
        )
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


@app.route('/admin/config/toggle-plan-periode', methods=['POST'])
@admin_required
def admin_toggle_plan_periode():
    db = get_db()
    current = db.execute("SELECT valeur FROM site_config WHERE cle='plan_gratuit_periode'").fetchone()
    new_val = 'monthly' if current and current[0] == 'daily' else 'daily'
    db.execute("INSERT OR REPLACE INTO site_config (cle, valeur) VALUES ('plan_gratuit_periode', ?)", (new_val,))
    db.commit()
    db.close()
    flash(f"Plan gratuit : mode {new_val} activé.", 'success')
    return redirect(url_for('admin'))



@app.route('/admin/boutiques-importees')
@admin_required
def admin_boutiques_importees():
    db = get_db()
    bouts = db.execute("""
        SELECT b.*, c.nom as cat_nom,
        (CASE WHEN b.logo IS NOT NULL AND b.logo!='' THEN 1 ELSE 0 END +
         CASE WHEN b.site_web IS NOT NULL AND b.site_web!='' THEN 1 ELSE 0 END +
         CASE WHEN b.horaires IS NOT NULL AND b.horaires!='' THEN 1 ELSE 0 END +
         CASE WHEN b.facebook IS NOT NULL AND b.facebook!='' THEN 1 ELSE 0 END +
         CASE WHEN LENGTH(COALESCE(b.description,''))>80 THEN 1 ELSE 0 END) as score
        FROM boutiques b LEFT JOIN categories c ON b.categorie_id=c.id
        WHERE b.slug LIKE 'pnr-%' ORDER BY b.nom
    """).fetchall()
    db.close()
    return render_template('pages/admin_boutiques_importees.html', boutiques=bouts)

@app.route('/admin/boutiques-importees/<int:bid>/edit', methods=['POST'])
@admin_required
def admin_boutique_importee_edit(bid):
    db = get_db()
    db.execute("UPDATE boutiques SET logo=?,description=?,site_web=?,horaires=?,facebook=?,instagram=?,whatsapp=?,telephone=? WHERE id=? AND slug LIKE 'pnr-%'",
        (request.form.get('logo',''), request.form.get('description',''), request.form.get('site_web',''),
         request.form.get('horaires',''), request.form.get('facebook',''), request.form.get('instagram',''),
         request.form.get('whatsapp',''), request.form.get('telephone',''), bid))
    db.commit(); db.close()
    return redirect(url_for('admin_boutiques_importees'))




@app.route('/admin/boutique/<int:bid>/activer', methods=['POST'])
@admin_required
def admin_activer_boutique(bid):
    action = request.form.get('action','activer')
    actif_val = 1 if action == 'activer' else 0
    db = get_db()
    db.execute('UPDATE boutiques SET actif=? WHERE id=?', (actif_val, bid))
    db.commit()
    db.close()
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

@app.route('/admin/annonce/<int:annonce_id>/supprimer', methods=['POST'])
@admin_required
def admin_annonce_supprimer(annonce_id):
    db = get_db()
    db.execute("UPDATE annonces SET statut='supprime' WHERE id=?", (annonce_id,))
    db.commit()
    db.close()
    flash('Annonce supprimee.', 'success')
    return redirect(url_for('admin'))

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




# ============================================================
# BLOG
# ============================================================


@app.route('/admin/blog/upload-image', methods=['POST'])
@admin_required
def admin_blog_upload_image():
    import uuid, os
    from werkzeug.utils import secure_filename
    if 'image' not in request.files:
        return jsonify({'error': 'Aucun fichier'}), 400
    file = request.files['image']
    if not file or file.filename == '':
        return jsonify({'error': 'Fichier vide'}), 400
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in {'jpg', 'jpeg', 'png', 'webp'}:
        return jsonify({'error': 'Format non supporté (jpg, png, webp)'}), 400
    filename = str(uuid.uuid4()) + '.' + ext
    upload_dir = '/home/donytchicaya/hellobiz/static/uploads/blog'
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, filename))
    return jsonify({'url': '/static/uploads/blog/' + filename})

@app.route('/blog')
def blog():
    db = get_db()
    db.execute("UPDATE blog_articles SET statut='publie' WHERE statut IN ('brouillon','planifie') AND published_at IS NOT NULL AND datetime(published_at) <= datetime('now', '+1 hour')")
    db.commit()
    articles = db.execute("""
        SELECT id, titre, slug, chapeau, categorie, vues, created_at
        FROM blog_articles WHERE statut='publie'
        ORDER BY created_at DESC
    """).fetchall()
    categories = db.execute("""
        SELECT DISTINCT categorie FROM blog_articles WHERE statut='publie'
    """).fetchall()
    db.close()
    villes, cats, quartiers = get_base_data()
    return render_template('pages/blog.html',
        articles=articles, categories=categories,
        villes=villes, cats=cats)

@app.route('/blog/<slug>')
def article(slug):
    db = get_db()
    a = db.execute("SELECT * FROM blog_articles WHERE slug=? AND statut='publie'", (slug,)).fetchone()
    if not a:
        db.close()
        return redirect(url_for('blog'))
    db.execute("UPDATE blog_articles SET vues=vues+1 WHERE slug=?", (slug,))
    db.commit()
    recents = db.execute("""
        SELECT titre, slug FROM blog_articles
        WHERE statut='publie' AND slug!=?
        ORDER BY created_at DESC LIMIT 4
    """, (slug,)).fetchall()
    db.close()
    villes, cats, quartiers = get_base_data()
    return render_template('pages/article.html',
        a=a, recents=recents, villes=villes, cats=cats)

@app.route('/admin/blog')
@admin_required
def admin_blog():
    db = get_db()
    db.execute("UPDATE blog_articles SET statut='publie' WHERE statut IN ('brouillon','planifie') AND published_at IS NOT NULL AND datetime(published_at) <= datetime('now', '+1 hour')")
    db.commit()
    articles = db.execute("""
        SELECT id, titre, slug, categorie, statut, vues, created_at
        FROM blog_articles ORDER BY created_at DESC
    """).fetchall()
    db.close()
    return render_template('pages/admin_blog.html', articles=articles)

@app.route('/admin/blog/nouveau', methods=['GET', 'POST'])
@admin_required
def admin_blog_nouveau():
    if request.method == 'POST':
        import re, datetime
        titre = request.form.get('titre', '').strip()
        chapeau = request.form.get('chapeau', '').strip()
        contenu = request.form.get('contenu', '').strip()
        categorie = request.form.get('categorie', 'conseils')
        image_url = request.form.get('image_url', '').strip()
        statut = request.form.get('statut', 'brouillon')
        published_at = request.form.get('published_at') or None
        slug = re.sub(r'[^a-z0-9]+', '-', titre.lower()).strip('-')
        db = get_db()
        try:
            db.execute("""
                INSERT INTO blog_articles (titre, slug, chapeau, contenu, categorie, image_url, statut, published_at)
                VALUES (?,?,?,?,?,?,?,?)
            """, (titre, slug, chapeau, contenu, categorie, image_url, statut, published_at))
            db.commit()
            flash('Article créé avec succès.', 'success')
        except Exception as e:
            flash(f'Erreur : {e}', 'error')
        db.close()
        return redirect(url_for('admin_blog'))
    return render_template('pages/admin_blog_form.html', article=None)

@app.route('/admin/blog/<int:article_id>/editer', methods=['GET', 'POST'])
@admin_required
def admin_blog_editer(article_id):
    db = get_db()
    a = db.execute("SELECT * FROM blog_articles WHERE id=?", (article_id,)).fetchone()
    if not a:
        db.close()
        return redirect(url_for('admin_blog'))
    if request.method == 'POST':
        import re, datetime
        titre = request.form.get('titre', '').strip()
        chapeau = request.form.get('chapeau', '').strip()
        contenu = request.form.get('contenu', '').strip()
        categorie = request.form.get('categorie', 'conseils')
        image_url = request.form.get('image_url', '').strip()
        statut = request.form.get('statut', 'brouillon')
        published_at = request.form.get('published_at') or None
        slug = re.sub(r'[^a-z0-9]+', '-', titre.lower()).strip('-')
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.execute("""
            UPDATE blog_articles SET titre=?, slug=?, chapeau=?, contenu=?,
            categorie=?, image_url=?, statut=?, published_at=?, updated_at=? WHERE id=?
        """, (titre, slug, chapeau, contenu, categorie, image_url, statut, published_at, now, article_id))
        db.commit()
        db.close()
        flash('Article mis à jour.', 'success')
        return redirect(url_for('admin_blog'))
    db.close()
    return render_template('pages/admin_blog_form.html', article=a)

@app.route('/admin/blog/<int:article_id>/supprimer', methods=['POST'])
@admin_required
def admin_blog_supprimer(article_id):
    db = get_db()
    db.execute("DELETE FROM blog_articles WHERE id=?", (article_id,))
    db.commit()
    db.close()
    flash('Article supprimé.', 'success')
    return redirect(url_for('admin_blog'))


@app.route('/installer')
def installer():
    return render_template('pages/installer.html')
import json as _json
from pywebpush import webpush as _wbp,WebPushException as _WPE
VAPID_PUB='BDwGlU_xB-yHPqmgNUlpd8xVhhQ2rKurxsUJlH_XvAoZzrTqITZsD983ySUQk924kCW8N_651V_In6qRr8rm55g'
VAPID_PRV='/home/donytchicaya/hellobiz/vapid_private.pem'
VAPID_CLM={'sub':'mailto:admin@hellobizcongo.com'}
@app.route('/save-push-sub',methods=['POST'])
def save_push_sub():
    if 'vendeur_id' not in session: return jsonify({'e':'nc'}),401
    d=request.get_json()
    if not d: return jsonify({'e':'nd'}),400
    sub=_json.dumps(d)
    db=get_db()
    ex=db.execute('SELECT id FROM push_subscriptions WHERE vendeur_id=?',(session['vendeur_id'],)).fetchone()
    if ex: db.execute('UPDATE push_subscriptions SET subscription=? WHERE vendeur_id=?',(sub,session['vendeur_id']))
    else: db.execute('INSERT INTO push_subscriptions (vendeur_id,subscription) VALUES (?,?)',(session['vendeur_id'],sub))
    db.commit()
    return jsonify({'ok':True})
@app.route('/notifier-whatsapp',methods=['POST'])
def notifier_whatsapp():
    d=request.get_json() or {}
    vid=d.get('vendeur_id')
    nom=d.get('nom','votre annonce')
    if not vid: return jsonify({'ok':False})
    db=get_db()
    row=db.execute('SELECT subscription FROM push_subscriptions WHERE vendeur_id=?',(vid,)).fetchone()
    if not row: return jsonify({'ok':False,'r':'no_sub'})
    try:
        _wbp(subscription_info=_json.loads(row['subscription']),data=_json.dumps({'title':'helloBiz — Nouveau contact','body':'Contact WhatsApp pour: '+nom,'url':'/dashboard'}),vapid_private_key=VAPID_PRV,vapid_claims=VAPID_CLM)
        return jsonify({'ok':True})
    except _WPE as e: return jsonify({'ok':False,'e':str(e)})

@app.template_filter('phone_wa')
def phone_wa_filter(s):
    import re
    if not s: return ''
    s=re.sub(r'[\s\-\(\)]','',str(s)).replace('+','')
    if s.startswith('0'): s='242'+s[1:]
    return s



# =====================================================================
# MODULE RECRUTEURS & CANDIDATS
# =====================================================================

from functools import wraps as _wraps

def recruteur_required(f):
    @_wraps(f)
    def decorated(*args, **kwargs):
        if 'recruteur_id' not in session:
            flash('Connectez-vous à votre espace recruteur.', 'error')
            return redirect(url_for('connexion_recruteur'))
        return f(*args, **kwargs)
    return decorated


@app.route('/inscription-recruteur', methods=['GET','POST'])
def inscription_recruteur():
    if request.method == 'POST':
        nom = request.form.get('nom','').strip()
        entreprise = request.form.get('entreprise','').strip()
        secteur = request.form.get('secteur','').strip()
        email = request.form.get('email','').strip()
        telephone = request.form.get('telephone','').strip()
        password = request.form.get('password','')
        if not nom or not telephone or not password:
            return render_template('pages/inscription_recruteur.html',
                error='Nom, téléphone et mot de passe sont obligatoires.')
        db = get_db()
        try:
            db.execute(
                'INSERT INTO recruteurs (nom,entreprise,secteur,email,telephone,password_hash) VALUES (?,?,?,?,?,?)',
                (nom, entreprise or None, secteur or None, email or None,
                 telephone, generate_password_hash(password))
            )
            db.commit()
        except Exception:
            db.close()
            return render_template('pages/inscription_recruteur.html',
                error='Ce numéro de téléphone est déjà enregistré.')
        row = db.execute('SELECT id,nom FROM recruteurs WHERE telephone=?', (telephone,)).fetchone()
        session['recruteur_id'] = row['id']
        session['recruteur_nom'] = row['nom']
        db.close()
        return redirect(url_for('dashboard_recruteur'))
    return render_template('pages/inscription_recruteur.html')


@app.route('/connexion-recruteur', methods=['GET','POST'])
def connexion_recruteur():
    if request.method == 'POST':
        telephone = request.form.get('telephone','').strip()
        password = request.form.get('password','')
        db = get_db()
        r = db.execute('SELECT * FROM recruteurs WHERE telephone=? AND actif=1', (telephone,)).fetchone()
        db.close()
        if r and check_password_hash(r['password_hash'], password):
            session['recruteur_id'] = r['id']
            session['recruteur_nom'] = r['nom']
            return redirect(url_for('dashboard_recruteur'))
        return render_template('pages/connexion_recruteur.html', error='Identifiants incorrects.')
    return render_template('pages/connexion_recruteur.html')


@app.route('/deconnexion-recruteur', methods=['POST'])
def deconnexion_recruteur():
    session.pop('recruteur_id', None)
    session.pop('recruteur_nom', None)
    return redirect(url_for('deposer_emploi'))


@app.route('/dashboard-recruteur')
@recruteur_required
def dashboard_recruteur():
    db = get_db()
    rid = session['recruteur_id']
    offres = db.execute(
        """SELECT a.*, v.nom as ville_nom FROM annonces a
           LEFT JOIN villes v ON a.ville_id=v.id
           WHERE a.recruteur_id=? ORDER BY a.created_at DESC""",
        (rid,)).fetchall()
    secteur_f = request.args.get('secteur','')
    if secteur_f:
        candidats = db.execute(
            """SELECT c.*, v.nom as ville_nom FROM candidats c
               LEFT JOIN villes v ON c.ville_id=v.id
               WHERE c.actif=1 AND c.secteur=? ORDER BY c.created_at DESC""",
            (secteur_f,)).fetchall()
    else:
        candidats = db.execute(
            """SELECT c.*, v.nom as ville_nom FROM candidats c
               LEFT JOIN villes v ON c.ville_id=v.id
               WHERE c.actif=1 ORDER BY c.created_at DESC""").fetchall()
    secteurs = db.execute(
        "SELECT DISTINCT secteur FROM candidats WHERE actif=1 AND secteur!='' ORDER BY secteur"
    ).fetchall()
    villes = db.execute('SELECT * FROM villes ORDER BY nom').fetchall()
    db.close()
    return render_template('pages/dashboard_recruteur.html',
        offres=offres, candidats=candidats,
        secteurs=secteurs, secteur_f=secteur_f, villes=villes)


@app.route('/soumettre-candidature', methods=['POST'])
def soumettre_candidature():
    nom = request.form.get('nom','').strip()
    telephone = request.form.get('telephone','').strip()
    secteur = request.form.get('secteur','').strip()
    contrat = request.form.get('contrat_souhaite','').strip()
    ville_id = request.form.get('ville_id') or None
    motivation = request.form.get('motivation','').strip()
    if not nom or not telephone or not secteur:
        flash('Nom, téléphone et secteur sont obligatoires.', 'error')
        return redirect(url_for('deposer_emploi') + '?mode=cherche')
    cv_fichier = None
    if 'cv' in request.files:
        f = request.files['cv']
        if f and f.filename and f.filename.lower().endswith('.pdf'):
            import os, uuid
            cv_dir = os.path.join(app.root_path, 'static', 'uploads', 'cvs')
            os.makedirs(cv_dir, exist_ok=True)
            fname = f'cv_{uuid.uuid4().hex[:10]}.pdf'
            f.save(os.path.join(cv_dir, fname))
            cv_fichier = fname
    db = get_db()
    db.execute(
        'INSERT INTO candidats (nom,telephone,secteur,contrat_souhaite,ville_id,motivation,cv_fichier) VALUES (?,?,?,?,?,?,?)',
        (nom, telephone, secteur, contrat, ville_id, motivation, cv_fichier)
    )
    db.commit()
    db.close()
    flash('Profil soumis avec succès. Les recruteurs inscrits pourront vous contacter directement.', 'success')
    return redirect(url_for('emploi'))


@app.route('/admin/cvtheque')
def admin_cvtheque():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    db = get_db()
    secteur_f = request.args.get('secteur','')
    if secteur_f:
        candidats = db.execute(
            """SELECT c.*, v.nom as ville_nom FROM candidats c
               LEFT JOIN villes v ON c.ville_id=v.id
               WHERE c.secteur=? ORDER BY c.created_at DESC""", (secteur_f,)).fetchall()
    else:
        candidats = db.execute(
            """SELECT c.*, v.nom as ville_nom FROM candidats c
               LEFT JOIN villes v ON c.ville_id=v.id
               ORDER BY c.created_at DESC""").fetchall()
    secteurs = db.execute(
        "SELECT DISTINCT secteur FROM candidats WHERE secteur!='' ORDER BY secteur").fetchall()
    recruteurs = db.execute('SELECT * FROM recruteurs ORDER BY created_at DESC').fetchall()
    db.close()
    return render_template('pages/admin_cvtheque.html',
        candidats=candidats, recruteurs=recruteurs,
        secteurs=secteurs, secteur_f=secteur_f)


@app.route('/admin/recruteur/<int:rid>/toggle', methods=['POST'])
def admin_toggle_recruteur(rid):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    db = get_db()
    db.execute('UPDATE recruteurs SET actif=1-actif WHERE id=?', (rid,))
    db.commit()
    db.close()
    return redirect(url_for('admin_cvtheque'))


@app.route('/admin/candidat/<int:cid>/toggle', methods=['POST'])
def admin_toggle_candidat(cid):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    db = get_db()
    db.execute('UPDATE candidats SET actif=1-actif WHERE id=?', (cid,))
    db.commit()
    db.close()
    return redirect(url_for('admin_cvtheque'))

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

@app.route('/auth/google')
def auth_google():
    redirect_uri='https://hellobizcongo.com/auth/google/callback'
    return google_oauth.authorize_redirect(redirect_uri)

@app.route('/auth/google/callback')
def auth_google_callback():
    try:
        token=google_oauth.authorize_access_token()
        ui=token.get('userinfo')
        if not ui:
            flash('Erreur connexion Google.','error');return redirect(url_for('connexion'))
        email=ui.get('email','');nom=ui.get('name','Utilisateur');gid=ui.get('sub')
        db=get_db()
        v=db.execute("SELECT * FROM vendeurs WHERE google_id=?",(gid,)).fetchone()
        if not v and email:v=db.execute("SELECT * FROM vendeurs WHERE email=?",(email,)).fetchone()
        if v:
            if not v['google_id']:db.execute("UPDATE vendeurs SET google_id=? WHERE id=?",(gid,v['id']));db.commit()
            session['vendeur_id']=v['id'];session['vendeur_nom']=v['nom'];db.close();return redirect(url_for('dashboard'))
        import datetime,secrets
        now=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S');pw=secrets.token_hex(16)
        db.execute("INSERT INTO vendeurs (nom,email,google_id,telephone,password,created_at) VALUES (?,?,?,?,?,?)",(nom,email,gid,'',pw,now))
        db.commit();nv=db.execute("SELECT * FROM vendeurs WHERE google_id=?",(gid,)).fetchone()
        session['vendeur_id']=nv['id'];session['vendeur_nom']=nom;db.close()
        flash('Compte créé ! Complétez votre profil.','info');return redirect(url_for('profil'))
    except Exception as e:
        flash(f'Erreur: {e}','error');return redirect(url_for('connexion'))

# ── VÉRIFICATION BOUTIQUE ──────────────────────────────────────────
@app.route('/demande-verification', methods=['GET','POST'])
def demande_verification():
    if 'vendeur_id' not in session:
        return redirect(url_for('connexion'))
    db = get_db()
    boutique = db.execute("SELECT * FROM boutiques WHERE vendeur_id=?", (session['vendeur_id'],)).fetchone()
    if not boutique:
        flash("Vous devez d'abord créer votre boutique.", 'error')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        if boutique['verification_statut'] not in ('en_attente', 'validee'):
            db.execute("UPDATE boutiques SET verification_statut='en_attente' WHERE id=?", (boutique['id'],))
            db.commit()
            flash("Votre demande a été envoyée. Nous la traitons sous 24-48h après réception du paiement.", 'success')
        return redirect(url_for('dashboard'))
    return render_template('pages/demande_verification.html', boutique=boutique)

@app.route('/admin/verifications')
def admin_verifications():
    if not session.get('is_admin'):
        return redirect(url_for('connexion'))
    db = get_db()
    boutiques_attente = db.execute("""SELECT b.*, v.nom as vendeur_nom, v.telephone as vendeur_tel, v.email as vendeur_email
        FROM boutiques b JOIN vendeurs v ON b.vendeur_id=v.id
        WHERE b.actif=0 ORDER BY b.created_at DESC""").fetchall()
    en_attente = db.execute("""SELECT b.*, v.nom as vendeur_nom, v.telephone as vendeur_tel
        FROM boutiques b JOIN vendeurs v ON b.vendeur_id=v.id
        WHERE b.verification_statut='en_attente' ORDER BY b.created_at DESC""").fetchall()
    verifiees = db.execute("""SELECT b.*, v.nom as vendeur_nom
        FROM boutiques b JOIN vendeurs v ON b.vendeur_id=v.id
        WHERE b.badge_verifie=1 ORDER BY b.created_at DESC""").fetchall()
    return render_template('pages/admin_verifications.html', boutiques_attente=boutiques_attente, en_attente=en_attente, verifiees=verifiees)

@app.route('/admin/valider-verification/<int:bid>', methods=['POST'])
def admin_valider_verification(bid):
    if not session.get('is_admin'):
        return redirect(url_for('connexion'))
    db = get_db()
    db.execute("UPDATE boutiques SET badge_verifie=1, verification_statut='validee' WHERE id=?", (bid,))
    db.commit()
    flash("Boutique vérifiée avec succès.", 'success')
    return redirect(url_for('admin_verifications'))

@app.route('/admin/rejeter-verification/<int:bid>', methods=['POST'])
def admin_rejeter_verification(bid):
    if not session.get('is_admin'):
        return redirect(url_for('connexion'))
    db = get_db()
    db.execute("UPDATE boutiques SET verification_statut='rejetee' WHERE id=?", (bid,))
    db.commit()
    flash("Demande rejetée.", 'info')
    return redirect(url_for('admin_verifications'))

@app.route('/admin/verifier-manuellement/<int:bid>', methods=['POST'])
def admin_verifier_manuellement(bid):
    if not session.get('is_admin'):
        return redirect(url_for('connexion'))
    db = get_db()
    db.execute("UPDATE boutiques SET badge_verifie=1, verification_statut='validee' WHERE id=?", (bid,))
    db.commit()
    flash("Boutique vérifiée manuellement.", 'success')
    return redirect(url_for('admin_verifications'))


@app.route('/admin/relance-vendeurs')
@admin_required
def admin_relance_vendeurs():
    db = get_db()
    # Boutiques avec 0 annonces actives, creees depuis 48h+
    boutiques = db.execute("""
        SELECT b.id, b.nom as boutique_nom, b.telephone, b.whatsapp, b.plan, b.created_at,
               v.nom as vendeur_nom,
               (SELECT COUNT(*) FROM annonces a WHERE a.boutique_id=b.id AND a.statut='active') as nb_annonces,
               CAST((julianday('now') - julianday(b.created_at)) AS INTEGER) as jours
        FROM boutiques b
        JOIN vendeurs v ON b.vendeur_id = v.id
        WHERE b.actif = 1
        ORDER BY b.created_at DESC
    """).fetchall()
    db.close()

    import urllib.parse
    vendeurs_sans_annonce = []
    vendeurs_avec_annonce = []
    for b in boutiques:
        tel = (b['whatsapp'] or b['telephone'] or '').replace(' ','').replace('+','').replace('-','')
        if tel.startswith('00'): tel = tel[2:]
        if tel.startswith('242'): pass
        elif len(tel) == 9: tel = '242' + tel
        
        prenom = (b['vendeur_nom'] or '').split()[0]
        msg = (
            f"Bonjour {prenom}, votre boutique *{b['boutique_nom']}* est en ligne sur hellobizcongo.com "
            f"mais sans annonce. Vos clients ne peuvent pas vous trouver ! "
            f"Deposez votre premiere annonce en 2 minutes : https://hellobizcongo.com/deposer-annonce"
        )
        wa_link = f"https://wa.me/{tel}?text={urllib.parse.quote(msg)}" if tel else None
        
        entry = dict(b) | {'wa_link': wa_link, 'tel_clean': tel, 'message': msg}
        if b['nb_annonces'] == 0:
            vendeurs_sans_annonce.append(entry)
        else:
            vendeurs_avec_annonce.append(entry)

    return render_template('pages/admin_relance.html',
        sans_annonce=vendeurs_sans_annonce,
        avec_annonce=vendeurs_avec_annonce)



@app.route('/ouvrir-ma-boutique')
def ouvrir_ma_boutique():
    db = get_db()
    nb_boutiques = db.execute('SELECT COUNT(*) FROM boutiques WHERE actif=1').fetchone()[0]
    nb_annonces  = db.execute('SELECT COUNT(*) FROM annonces WHERE statut="active"').fetchone()[0]
    return render_template('pages/ouvrir-ma-boutique.html',
        nb_boutiques=nb_boutiques,
        nb_annonces=nb_annonces)

@app.after_request
def wa_share(response):
    from urllib.parse import quote as _q
    from flask import request as _R
    if 'text/html' not in (response.content_type or ''):return response
    p=_R.path.strip('/').split('/')
    if len(p)!=2 or p[0] not in ('boutique','annonce'):return response
    h=response.get_data(as_text=True)
    if 'wa-float-share' in h:return response
    import re as _re
    m=_re.search(r'<title>([^<]+)</title>',h)
    title=p[1].replace('-',' ').title()
    if m:
        raw=m.group(1)
        for sfx in [' · helloBiz',' - helloBiz']:
            if raw.endswith(sfx):raw=raw[:-len(sfx)];break
        title=raw.strip()
    page_url='https://donytchicaya.pythonanywhere.com'+_R.path
    wa_href='https://wa.me/?text='+_q('helloBiz : '+title+' '+page_url,safe='')
    btn=('<div id="wa-float-share" style="position:fixed;bottom:90px;right:18px;z-index:9999;font-family:sans-serif">'
         '<a href="'+wa_href+'" target="_blank" style="display:flex;align-items:center;gap:8px;background:#25D366;color:#fff;text-decoration:none;padding:11px 16px;border-radius:50px;box-shadow:0 4px 14px rgba(37,211,102,0.4);font-weight:700;font-size:13px">&#128233; Partager sur WhatsApp</a></div>')
    response.set_data(h.replace('</body>',btn+'</body>',1))
    return response
