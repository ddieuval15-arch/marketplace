#!/usr/bin/env python3
"""
Deploiement helloBiz -> PythonAnywhere via l'API Files.
Recupere le fichier LIVE sur le serveur, applique des patchs idempotents
(anchor-based), puis renvoie le resultat. Ne fait jamais un overwrite
complet : preserve tout ce qui existe deja en prod et n'a pas ete
touche par ces patchs.
"""
import os
import sys
import requests

print(f'[INFO] PA_USER={os.environ.get("PA_USERNAME","donytchicaya")}')
PA_USER = os.environ.get("PA_USERNAME", "donytchicaya")
_pa_token_raw = os.environ.get("PA_API_TOKEN")
if not _pa_token_raw:
    print("::error::La variable d'environnement PA_API_TOKEN est vide ou absente. Verifiez que le secret 'PA_API_TOKEN' existe bien dans Settings > Secrets and variables > Actions du depot.")
    sys.exit(1)
PA_TOKEN = _pa_token_raw.strip()
print(f"[INFO] Token recu, longueur={len(PA_TOKEN)} caracteres")
DOMAIN = os.environ.get("PA_DOMAIN", f"{PA_USER}.pythonanywhere.com")

API_BASE = f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}"
HEADERS = {"Authorization": f"Token {PA_TOKEN}"}
APP_ROOT = f"/home/{PA_USER}/hellobiz"

def _list_dir(path):
    import json as _json
    url = f"{API_BASE}/files/path{path}"
    if not url.endswith("/"):
        url += "/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.ok:
            try:
                keys = sorted(_json.loads(r.text).keys())
            except Exception:
                keys = ["<parse error>"]
            print(f"::warning::[LISTING {path}] HTTP {r.status_code} -- {len(keys)} entrees : {', '.join(keys)}")
        else:
            print(f"::warning::[LISTING {path}] HTTP {r.status_code} -- {r.text[:500]}")
    except Exception as e:
        print(f"::warning::[LISTING {path}] exception: {e}")

_list_dir(f"/home/{PA_USER}/hellobiz/")
_list_dir(f"/home/{PA_USER}/hellobiz/templates/")

def _fail(step, r):
    print(f"::error::[{step}] HTTP {r.status_code} -- {r.text[:500]}")
    r.raise_for_status()

def get_file(path):
    url = f"{API_BASE}/files/path{APP_ROOT}/{path}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    if not r.ok:
        _fail(f"GET {path}", r)
    return r.text

def put_file(path, content):
    url = f"{API_BASE}/files/path{APP_ROOT}/{path}"
    r = requests.post(url, headers=HEADERS, files={"content": content.encode("utf-8")}, timeout=30)
    if not r.ok:
        _fail(f"PUT {path}", r)

def reload_app():
    url = f"{API_BASE}/webapps/{DOMAIN}/reload/"
    r = requests.post(url, headers=HEADERS, timeout=60)
    print(f"[RELOAD] status={r.status_code}")
    if not r.ok:
        _fail("RELOAD", r)

def apply_patch(content, old, new, label):
    if new in content:
        print(f"  [--] deja applique : {label}")
        return content, False
    if old not in content:
        print(f"  [!!] ancre introuvable, patch ignore : {label}")
        return content, False
    content = content.replace(old, new, 1)
    print(f"  [OK] applique : {label}")
    return content, True

# ─────────────────────────────────────────────────────────────
# 1. templates/base.html
# ─────────────────────────────────────────────────────────────
print("=== templates/base.html ===")
path = "templates/base.html"
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '''          <a href="/deposer-annonce" style="display:flex;align-items:center;gap:10px;padding:11px 16px;font-size:13px;color:var(--text);transition:background .15s" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='none'">
            <i class="ti ti-plus"></i> Deposer une annonce
          </a>
          <a href="/mes-favoris" style="display:flex;align-items:center;gap:10px;padding:11px 16px;font-size:13px;color:var(--text);transition:background .15s" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='none'">
            <i class="ti ti-heart"></i> Mes favoris
          </a>''',
    '''          <a href="/deposer-annonce" style="display:flex;align-items:center;gap:10px;padding:11px 16px;font-size:13px;color:var(--text);transition:background .15s" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='none'">
            <i class="ti ti-plus"></i> Deposer une annonce
          </a>
          <a href="/alertes" style="display:flex;align-items:center;gap:10px;padding:11px 16px;font-size:13px;color:var(--text);transition:background .15s" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='none'">
            <i class="ti ti-bell"></i> Mes alertes
          </a>
          <a href="/mes-favoris" style="display:flex;align-items:center;gap:10px;padding:11px 16px;font-size:13px;color:var(--text);transition:background .15s" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='none'">
            <i class="ti ti-heart"></i> Mes favoris
          </a>''',
    'lien Mes alertes dans le menu utilisateur',
)
changed = changed or ch

c, ch = apply_patch(
    c,
    '''      {% for cat, msg in messages %}
        <div class="flash {{ cat }}" style="margin-bottom:8px">{{ msg }}</div>
      {% endfor %}''',
    '''      {% for cat, msg in messages %}
        <div class="flash {{ cat }}" style="margin-bottom:8px"
          {% if 'annonce publiee' in msg.lower() %}data-ga-event="annonce_publiee"{% endif %}
          {% if 'alerte creee' in msg.lower() %}data-ga-event="alerte_creee"{% endif %}
          {% if 'boutique creee' in msg.lower() %}data-ga-event="boutique_creee"{% endif %}
        >{{ msg }}</div>
      {% endfor %}''',
    'attributs data-ga-event sur les messages flash',
)
changed = changed or ch

c, ch = apply_patch(
    c,
    '''document.querySelectorAll('.flash').forEach(function(el) {
  setTimeout(function() {
    el.style.transition = 'opacity .5s';
    el.style.opacity = '0';
    setTimeout(function() { el.remove(); }, 500);
  }, 5000);
});''',
    '''document.querySelectorAll('.flash').forEach(function(el) {
  setTimeout(function() {
    el.style.transition = 'opacity .5s';
    el.style.opacity = '0';
    setTimeout(function() { el.remove(); }, 500);
  }, 5000);
});
// GA4 : conversions clefs declenchees via les messages flash
document.querySelectorAll('.flash[data-ga-event]').forEach(function(el) {
  if (typeof gtag === 'function') {
    gtag('event', el.getAttribute('data-ga-event'));
  }
});''',
    'script GA4 declenche par les flash messages',
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# 2. templates/pages/index.html
# ─────────────────────────────────────────────────────────────
print("=== templates/pages/index.html ===")
path = "templates/pages/index.html"
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '<div class="container" style="padding-top:40px">',
    '''<div class="container" style="padding-top:24px">
  <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:stretch;background:var(--card-bg);border:1px solid var(--border);border-radius:var(--radius);padding:16px 20px;box-shadow:var(--shadow)">
    <div style="display:flex;align-items:center;gap:12px;flex:1;min-width:220px">
      <div style="width:38px;height:38px;border-radius:50%;background:var(--primary-light);display:flex;align-items:center;justify-content:center;flex-shrink:0">
        <i class="ti ti-bell-ringing" style="color:var(--primary);font-size:18px"></i>
      </div>
      <div>
        <div style="font-size:13.5px;font-weight:700;color:var(--text)">Ne manquez plus aucune annonce</div>
        <div style="font-size:12px;color:var(--text-muted)">Créez une alerte gratuite, on vous notifie par email des nouvelles offres.</div>
      </div>
    </div>
    <a href="{{ url_for('alertes') }}"
       onclick="if(typeof gtag==='function'){gtag('event','cta_alerte_click',{'page':'accueil'});}"
       style="display:flex;align-items:center;gap:6px;background:var(--primary);color:#fff;padding:10px 18px;border-radius:20px;font-size:13px;font-weight:700;white-space:nowrap;flex-shrink:0;align-self:center">
      <i class="ti ti-bell-plus"></i> Créer une alerte
    </a>
    <a href="https://wa.me/242057731857?text={{ 'Bonjour, je viens de hellobizcongo.com et je souhaite en savoir plus.' | urlencode }}"
       target="_blank" rel="noopener"
       onclick="if(typeof gtag==='function'){gtag('event','cta_whatsapp_click',{'page':'accueil'});}"
       style="display:flex;align-items:center;gap:6px;background:#25D366;color:#fff;padding:10px 18px;border-radius:20px;font-size:13px;font-weight:700;white-space:nowrap;flex-shrink:0;align-self:center">
      <i class="ti ti-brand-whatsapp"></i> WhatsApp
    </a>
  </div>
</div>

<div class="container" style="padding-top:24px">''',
    'bandeau CTA alerte + WhatsApp sur l\'accueil',
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# 3. templates/pages/annonce.html
# ─────────────────────────────────────────────────────────────
print("=== templates/pages/annonce.html ===")
path = "templates/pages/annonce.html"
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '''          <a href="https://wa.me/{{ boutique.whatsapp|replace('(+','')|replace(')','') | replace(' ','')|replace('-','') }}"
             target="_blank" class="btn btn-secondary btn-full" style="margin-bottom:8px;justify-content:center;border-color:#25d366;color:#25d366">
            <i class="ti ti-brand-whatsapp"></i> WhatsApp
          </a>''',
    '''          <a href="https://wa.me/{{ boutique.whatsapp|replace('(+','')|replace(')','') | replace(' ','')|replace('-','') }}"
             target="_blank" class="btn btn-secondary btn-full" style="margin-bottom:8px;justify-content:center;border-color:#25d366;color:#25d366"
             onclick="if(typeof gtag==='function'){gtag('event','whatsapp_contact_vendeur',{'annonce_id':{{ annonce.id }}});}">
            <i class="ti ti-brand-whatsapp"></i> WhatsApp
          </a>''',
    'tracking GA4 sur le bouton WhatsApp contact vendeur',
)
changed = changed or ch

c, ch = apply_patch(
    c,
    '''          <a href="https://wa.me/?text={{ wa_text | urlencode }}" target="_blank" rel="noopener"
            style="flex:1;display:flex;align-items:center;justify-content:center;gap:6px;padding:9px 0;background:#25d366;color:white;border-radius:var(--radius-sm);font-size:12px;font-weight:700;text-decoration:none">
            <i class="ti ti-brand-whatsapp" style="font-size:15px"></i> WhatsApp
          </a>''',
    '''          <a href="https://wa.me/?text={{ wa_text | urlencode }}" target="_blank" rel="noopener"
            onclick="if(typeof gtag==='function'){gtag('event','whatsapp_partage_annonce',{'annonce_id':{{ annonce.id }}});}"
            style="flex:1;display:flex;align-items:center;justify-content:center;gap:6px;padding:9px 0;background:#25d366;color:white;border-radius:var(--radius-sm);font-size:12px;font-weight:700;text-decoration:none">
            <i class="ti ti-brand-whatsapp" style="font-size:15px"></i> WhatsApp
          </a>''',
    'tracking GA4 sur le bouton WhatsApp partage annonce (ignore si le bloc Partager n\'existe pas encore en prod)',
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# 4. templates/pages/contact.html
# ─────────────────────────────────────────────────────────────
print("=== templates/pages/contact.html ===")
path = "templates/pages/contact.html"
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '''    <a href="https://wa.me/242057731857" target="_blank"
       style="background:var(--card-bg);border:1px solid var(--border);border-radius:var(--radius);padding:20px;display:flex;align-items:center;gap:14px;transition:border-color .15s"
       onmouseover="this.style.borderColor='var(--primary)'" onmouseout="this.style.borderColor='var(--border)'">''',
    '''    <a href="https://wa.me/242057731857" target="_blank"
       onclick="if(typeof gtag==='function'){gtag('event','whatsapp_contact_support',{'page':'contact'});}"
       style="background:var(--card-bg);border:1px solid var(--border);border-radius:var(--radius);padding:20px;display:flex;align-items:center;gap:14px;transition:border-color .15s"
       onmouseover="this.style.borderColor='var(--primary)'" onmouseout="this.style.borderColor='var(--border)'">''',
    'tracking GA4 sur le bouton WhatsApp de la page contact',
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# app.py
# ─────────────────────────────────────────────────────────────
path = "app.py"
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    """    threading.Thread(target=_send, daemon=True).start()


DB_PATH = os.environ.get(\'DB_PATH\',""",
    """    threading.Thread(target=_send, daemon=True).start()


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



DB_PATH = os.environ.get(\'DB_PATH\',""",
    "ajout notifier_alertes() et calcul_badges_confiance()",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    """    flash('Publicite mise a jour.', 'success')
    return redirect(url_for('admin_publicites'))""",
    """    flash('Publicite mise a jour.', 'success')
    return redirect(url_for('admin_publicites'))

@app.route('/admin/annonce/<int:annonce_id>/supprimer', methods=['POST'])
@admin_required
def admin_annonce_supprimer(annonce_id):
    db = get_db()
    db.execute("UPDATE annonces SET statut='supprime' WHERE id=?", (annonce_id,))
    db.commit()
    db.close()
    flash('Annonce supprimee.', 'success')
    return redirect(url_for('admin'))""",
    "route admin pour supprimer une annonce par id",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    """    db.close()
    return render_template('pages/boutique.html', boutique=b, annonces=annonces_b, stats=stats,
        avis_list=avis_list, note_moy=note_moy, mon_avis=mon_avis,
        villes=villes, categories=categories)""",
    """    badges = calcul_badges_confiance(b, avis_list)
    db.close()
    return render_template('pages/boutique.html', boutique=b, annonces=annonces_b, stats=stats,
        avis_list=avis_list, note_moy=note_moy, mon_avis=mon_avis, badges=badges,
        villes=villes, categories=categories)""",
    "calcul et transmission des badges de confiance a la page boutique",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/boutique.html
# ─────────────────────────────────────────────────────────────
path = "templates/pages/boutique.html"
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '''          <span class="plan-badge {{ boutique.plan }}">{{ boutique.plan }}</span>
        </div>''',
    '''          <span class="plan-badge {{ boutique.plan }}">{{ boutique.plan }}</span>
        </div>
        {% if badges %}
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
          {% for bd in badges %}
          <span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:600;padding:4px 10px;border-radius:20px;color:{{ bd.couleur }};background:{{ bd.bg }}">{{ bd.icon }} {{ bd.label }}</span>
          {% endfor %}
        </div>
        {% endif %}''',
    "affichage des badges de confiance sur la page boutique",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# --- Snapshot temporaire du app.py / database.py reellement en ligne ---
# Ecrit le contenu live dans des fichiers locaux du checkout, qui seront
# commit/push par l'etape suivante du workflow -- permet de les lire
# directement via git au lieu de les extraire via les annotations
# (trop volumineux et coupees au premier retour a la ligne).
for _fname, _out in [("app.py", "live_snapshot_app.py"), ("database.py", "live_snapshot_database.py"), ("templates/pages/annonce.html", "live_snapshot_annonce.html"), ("templates/pages/boutique.html", "live_snapshot_boutique.html"), ("templates/pages/creer_boutique.html", "live_snapshot_creer_boutique.html"), ("templates/pages/deposer_annonce.html", "live_snapshot_deposer_annonce.html")]:
    try:
        _live = get_file(_fname)
        with open(_out, "w", encoding="utf-8") as _f:
            _f.write(_live)
        print(f"[SNAPSHOT] {_fname} -> {_out} ({len(_live.splitlines())} lignes)")
    except Exception as e:
        print(f"::warning::[SNAPSHOT {_fname}] exception: {e}")

print("=== reload de l'application ===")
reload_app()
print("=== TERMINE ===")

# trigger: relance apres ajout du secret PA_API_TOKEN
# trigger
