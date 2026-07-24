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

c, ch = apply_patch(
    c,
    """  <!-- HORAIRES (entreprise) -->
  {% if boutique.is_entreprise and boutique.horaires %}
  <div style="background:var(--card-bg);border:1px solid var(--border);border-radius:var(--radius);padding:16px 20px;margin-bottom:20px;display:flex;align-items:flex-start;gap:14px">
    <i class="ti ti-clock" style="font-size:20px;color:var(--primary);flex-shrink:0;margin-top:2px"></i>
    <div>
      <div style="font-size:13px;font-weight:700;margin-bottom:4px">Horaires d'ouverture</div>
      <div style="font-size:13px;color:var(--text-muted);white-space:pre-line">{{ boutique.horaires }}</div>
    </div>
  </div>
  {% endif %}""",
    """  <!-- FERMETURE TEMPORAIRE -->
  {% if boutique.fermeture_message %}
  <div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:var(--radius);padding:14px 20px;margin-bottom:20px;display:flex;align-items:center;gap:12px">
    <i class="ti ti-alert-triangle" style="font-size:20px;color:#dc2626;flex-shrink:0"></i>
    <div style="font-size:13px;font-weight:700;color:#991b1b">{{ boutique.fermeture_message }}</div>
  </div>
  {% endif %}

  <!-- ADRESSE -->
  {% if boutique.adresse %}
  <div style="background:var(--card-bg);border:1px solid var(--border);border-radius:var(--radius);padding:16px 20px;margin-bottom:20px;display:flex;align-items:flex-start;gap:14px">
    <i class="ti ti-map-pin" style="font-size:20px;color:var(--primary);flex-shrink:0;margin-top:2px"></i>
    <div>
      <div style="font-size:13px;font-weight:700;margin-bottom:4px">Adresse</div>
      <div style="font-size:13px;color:var(--text-muted);margin-bottom:6px">{{ boutique.adresse }}</div>
      <a href="https://www.google.com/maps/search/?api=1&query={{ boutique.adresse|urlencode }}" target="_blank" rel="noopener" style="font-size:12px;font-weight:700;color:var(--primary)">
        <i class="ti ti-map-2"></i> Voir sur Google Maps
      </a>
    </div>
  </div>
  {% endif %}

  <!-- HORAIRES -->
  {% if boutique.horaires %}
  <div style="background:var(--card-bg);border:1px solid var(--border);border-radius:var(--radius);padding:16px 20px;margin-bottom:20px;display:flex;align-items:flex-start;gap:14px">
    <i class="ti ti-clock" style="font-size:20px;color:var(--primary);flex-shrink:0;margin-top:2px"></i>
    <div>
      <div style="font-size:13px;font-weight:700;margin-bottom:4px">Horaires d'ouverture</div>
      <div style="font-size:13px;color:var(--text-muted);white-space:pre-line">{{ boutique.horaires }}</div>
    </div>
  </div>
  {% endif %}""",
    "affiche l'adresse (avec lien Google Maps), les horaires pour toutes les boutiques (plus seulement Entreprise Pro) et le bandeau de fermeture temporaire",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# database.py
# ─────────────────────────────────────────────────────────────
path = "database.py"
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    """        ('km4', 'Km4', 2), ('boscongo', 'Boscongo', 2),""",
    """        ('km4', 'Km4', 2), ('boscongo', 'Boscongo', 2),
        ('mpaka', 'Mpaka', 2), ('wharf', 'Wharf', 2),
        ('sangolo', 'Sangolo', 2), ('la-base', 'La Base', 2),
        ('patra', 'Patra', 2), ('malala', 'Malala', 2),
        ('aeroport-pnr', 'Aeroport', 2),""",
    "ajout des quartiers manquants de Pointe-Noire (Mpaka, Wharf, Sangolo, La Base, Patra, Malala, Aeroport)",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    "    ]\n    for sql in migrations:",
    ("        \"ALTER TABLE boutiques ADD COLUMN adresse TEXT\",\n"
     "        \"ALTER TABLE boutiques ADD COLUMN fermeture_message TEXT\",\n"
     "    ]\n    for sql in migrations:"),
    "ajoute les colonnes adresse et fermeture_message a la table boutiques",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# app.py -- fix quartier sur creer_boutique()
# ─────────────────────────────────────────────────────────────
path = "app.py"
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    """            quartier_id_b = form.get(\'quartier_id\') or None
            db.execute(\'\'\'INSERT INTO boutiques
                (slug,nom,description,categorie_id,ville_id,quartier_id,telephone,whatsapp,email,plan,vendeur_id,actif,logo,banniere)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)\'\'\'  ,
                (slug, nom, desc, cat_id, ville_id, quartier_id_b, tel, wa, vendeur[\'email\'], plan,
                 session[\'vendeur_id\'], actif_initial, logo_fname, banniere_fname))""",
    """            quartier_libre_b = form.get(\'quartier_libre\', \'\').strip() or None
            if form.get(\'quartier_id\') == \'autre\' and quartier_libre_b:
                _q_slug = slugify(quartier_libre_b)
                db.execute(\'INSERT OR IGNORE INTO quartiers (slug, nom, ville_id) VALUES (?,?,?)\',
                           (_q_slug, quartier_libre_b, ville_id))
                db.commit()
                _q_row = db.execute(\'SELECT id FROM quartiers WHERE slug=?\', (_q_slug,)).fetchone()
                quartier_id_b = _q_row[\'id\'] if _q_row else None
            else:
                quartier_id_b = form.get(\'quartier_id\') or None
            db.execute(\'\'\'INSERT INTO boutiques
                (slug,nom,description,categorie_id,ville_id,quartier_id,telephone,whatsapp,email,plan,vendeur_id,actif,logo,banniere)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)\'\'\'  ,
                (slug, nom, desc, cat_id, ville_id, quartier_id_b, tel, wa, vendeur[\'email\'], plan,
                 session[\'vendeur_id\'], actif_initial, logo_fname, banniere_fname))""",
    "gestion du quartier libre (Autre) avec enrichissement automatique de la table quartiers",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    """    return render_template(\'pages/creer_boutique.html\',
        villes=villes, categories=categories, vendeur=vendeur, form=form,
        mode_recruteur=mode_recruteur)""",
    """    return render_template(\'pages/creer_boutique.html\',
        villes=villes, categories=categories, vendeur=vendeur, form=form,
        quartiers=quartiers, mode_recruteur=mode_recruteur)""",
    "transmission de la liste des quartiers au formulaire de creation de boutique",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    """    boutiques_attente = db.execute(
        "SELECT COUNT(*) FROM boutiques WHERE actif=0"
    ).fetchone()[0]""",
    """    boutiques_attente = db.execute(
        "SELECT COUNT(*) FROM boutiques WHERE actif=0"
    ).fetchone()[0]
    boutiques_non_verifiees = db.execute(
        "SELECT COUNT(*) FROM boutiques WHERE actif=1 AND badge_verifie=0"
    ).fetchone()[0]""",
    "ajout du calcul des boutiques actives non verifiees pour la notification admin",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    "        'boutiques_attente': boutiques_attente,",
    "        'boutiques_attente': boutiques_attente,\n        'boutiques_non_verifiees': boutiques_non_verifiees,",
    "ajout de boutiques_non_verifiees dans le dict stats",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    """    try:
        if b['badge_verifie']:
            badges.append({'id': 'verifie', 'label': 'Verifie helloBiz', 'icon': '\u2705',
                            'couleur': '#16a34a', 'bg': '#f0fdf4'})
    except Exception:
        pass""",
    """    try:
        if b['badge_verifie']:
            if b['plan'] == 'business':
                badges.append({'id': 'verifie', 'label': 'Verifie Business', 'icon': '\U0001F451',
                                'couleur': '#92400e', 'bg': '#fef9c3'})
            else:
                badges.append({'id': 'verifie', 'label': 'Verifie helloBiz', 'icon': '\u2705',
                                'couleur': '#16a34a', 'bg': '#f0fdf4'})
    except Exception:
        pass""",
    "badge Verifie en dore/couronne pour les boutiques plan Business, vert pour les autres",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    "    'business': {'nom': 'Business', 'prix': 50000, 'annonces': 9999, 'photos': 30, 'videos': 9999},",
    "    'business': {'nom': 'Business', 'prix': 25000, 'annonces': 9999, 'photos': 30, 'videos': 9999},",
    "corrige le prix reellement facture du plan Business (25000 FCFA, prix promo actuel) au lieu de l'ancien 50000",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    """@app.route('/boutique/<slug>')
def boutique(slug):""",
    """@app.route('/vendeur/<int:vendeur_id>')
def vendeur_profil(vendeur_id):
    db = get_db()
    b = db.execute('SELECT slug FROM boutiques WHERE vendeur_id=?', (vendeur_id,)).fetchone()
    db.close()
    if not b:
        abort(404)
    return redirect(url_for('boutique', slug=b['slug']))

@app.route('/boutique/<slug>')
def boutique(slug):""",
    "ajoute la route /vendeur/<id> manquante (le lien Profil vendeur sur les annonces menait a une 404 partout)",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    """            quartier_libre_b = form.get('quartier_libre', '').strip() or None
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
                 session['vendeur_id'], actif_initial, logo_fname, banniere_fname))""",
    """            quartier_libre_b = form.get('quartier_libre', '').strip() or None
            if form.get('quartier_id') == 'autre' and quartier_libre_b:
                _q_slug = slugify(quartier_libre_b)
                db.execute('INSERT OR IGNORE INTO quartiers (slug, nom, ville_id) VALUES (?,?,?)',
                           (_q_slug, quartier_libre_b, ville_id))
                db.commit()
                _q_row = db.execute('SELECT id FROM quartiers WHERE slug=?', (_q_slug,)).fetchone()
                quartier_id_b = _q_row['id'] if _q_row else None
            else:
                quartier_id_b = form.get('quartier_id') or None
            adresse_b = form.get('adresse', '')[:300]
            fermeture_message_b = form.get('fermeture_message', '')[:300]
            _jours_b = [('lun','Lundi'),('mar','Mardi'),('mer','Mercredi'),('jeu','Jeudi'),('ven','Vendredi'),('sam','Samedi'),('dim','Dimanche')]
            _lignes_horaires_b = []
            for _code_b, _label_b in _jours_b:
                if request.form.get(f'horaire_{_code_b}_ferme'):
                    _lignes_horaires_b.append(f'{_label_b} : Ferme')
                else:
                    _hd_b = request.form.get(f'horaire_{_code_b}_debut', '').strip()
                    _hf_b = request.form.get(f'horaire_{_code_b}_fin', '').strip()
                    if _hd_b and _hf_b:
                        _lignes_horaires_b.append(f'{_label_b} : {_hd_b} - {_hf_b}')
            horaires_b = chr(10).join(_lignes_horaires_b)
            db.execute('''INSERT INTO boutiques
                (slug,nom,description,categorie_id,ville_id,quartier_id,telephone,whatsapp,email,plan,vendeur_id,actif,logo,banniere,adresse,horaires,fermeture_message)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''  ,
                (slug, nom, desc, cat_id, ville_id, quartier_id_b, tel, wa, vendeur['email'], plan,
                 session['vendeur_id'], actif_initial, logo_fname, banniere_fname, adresse_b, horaires_b, fermeture_message_b))""",
    "ajoute la capture adresse, horaires (jour par jour) et fermeture temporaire a la creation de boutique",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    """        horaires=form.get('horaires',b['horaires'] or '')
        site_web=form.get('site_web',b['site_web'] or '')
        facebook=form.get('facebook',b['facebook'] or '')
        instagram=form.get('instagram',b['instagram'] or '')
        logo=b['logo']
        banniere=b['banniere']""",
    """        _jours_m = [('lun','Lundi'),('mar','Mardi'),('mer','Mercredi'),('jeu','Jeudi'),('ven','Vendredi'),('sam','Samedi'),('dim','Dimanche')]
        if any((f'horaire_{_c}_ferme' in request.form or f'horaire_{_c}_debut' in request.form) for _c, _ in _jours_m):
            _lignes_m = []
            for _code_m, _label_m in _jours_m:
                if request.form.get(f'horaire_{_code_m}_ferme'):
                    _lignes_m.append(f'{_label_m} : Ferme')
                else:
                    _hd_m = request.form.get(f'horaire_{_code_m}_debut', '').strip()
                    _hf_m = request.form.get(f'horaire_{_code_m}_fin', '').strip()
                    if _hd_m and _hf_m:
                        _lignes_m.append(f'{_label_m} : {_hd_m} - {_hf_m}')
            horaires = chr(10).join(_lignes_m)
        else:
            horaires=form.get('horaires',b['horaires'] or '')
        adresse=form.get('adresse',b['adresse'] or '')
        fermeture_message=form.get('fermeture_message',b['fermeture_message'] or '')
        site_web=form.get('site_web',b['site_web'] or '')
        facebook=form.get('facebook',b['facebook'] or '')
        instagram=form.get('instagram',b['instagram'] or '')
        logo=b['logo']
        banniere=b['banniere']""",
    "ajoute la capture adresse, horaires (jour par jour) et fermeture temporaire a la modification de boutique",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    """            db.execute("UPDATE boutiques SET nom=?,description=?,telephone=?,whatsapp=?,email=?,logo=?,banniere=?,horaires=?,site_web=?,facebook=?,instagram=? WHERE vendeur_id=?",
                (nom,description,telephone,whatsapp,email,logo,banniere,horaires,site_web,facebook,instagram,session['vendeur_id']))""",
    """            db.execute("UPDATE boutiques SET nom=?,description=?,telephone=?,whatsapp=?,email=?,logo=?,banniere=?,horaires=?,site_web=?,facebook=?,instagram=?,adresse=?,fermeture_message=? WHERE vendeur_id=?",
                (nom,description,telephone,whatsapp,email,logo,banniere,horaires,site_web,facebook,instagram,adresse,fermeture_message,session['vendeur_id']))""",
    "inclut adresse et fermeture_message dans la mise a jour de la boutique (modifier-boutique)",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/creer_boutique.html
# ─────────────────────────────────────────────────────────────
path = "templates/pages/creer_boutique.html"
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '''            <label style="font-size:13px;font-weight:600;color:var(--text);display:block;margin-bottom:6px">Ville *</label>
            <select name="ville_id" required
              style="width:100%;border:1px solid var(--border);border-radius:var(--radius-sm);padding:11px 14px;font-size:14px;outline:none;background:white"
              onfocus="this.style.borderColor=\'var(--primary)\'" onblur="this.style.borderColor=\'var(--border)\'">
              <option value="">Choisir…</option>
              {% for v in villes %}
                <option value="{{ v.id }}" {% if form.ville_id == v.id|string %}selected{% endif %}>{{ v.nom }}</option>
              {% endfor %}
            </select>''',
    '''            <label style="font-size:13px;font-weight:600;color:var(--text);display:block;margin-bottom:6px">Ville *</label>
            <select name="ville_id" id="select-ville-b" required onchange="updateQuartiersBoutique(this.value)"
              style="width:100%;border:1px solid var(--border);border-radius:var(--radius-sm);padding:11px 14px;font-size:14px;outline:none;background:white"
              onfocus="this.style.borderColor=\'var(--primary)\'" onblur="this.style.borderColor=\'var(--border)\'">
              <option value="">Choisir…</option>
              {% for v in villes %}
                <option value="{{ v.id }}" {% if form.ville_id == v.id|string %}selected{% endif %}>{{ v.nom }}</option>
              {% endfor %}
            </select>''',
    "ajout de l\'id et du onchange sur le select ville (creer_boutique)",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    '''<div style="margin-bottom:16px"><label style="font-size:13px;font-weight:600;color:var(--text);display:block;margin-bottom:6px">Quartier / Zone <span style="font-weight:400;color:var(--text-muted)">(optionnel)</span></label><select name="quartier_id" style="width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);font-size:14px;background:white"><option value="">Choisir un quartier...</option>{% for q in quartiers %}<option value="{{ q.id }}" {% if form.quartier_id == q.id|string %}selected{% endif %}>{{ q.nom }}</option>{% endfor %}</select></div>''',
    '''<div style="margin-bottom:16px"><label style="font-size:13px;font-weight:600;color:var(--text);display:block;margin-bottom:6px">Quartier / Zone <span style="font-weight:400;color:var(--text-muted)">(optionnel)</span></label><select name="quartier_id" id="select-quartier-b" style="width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);font-size:14px;background:white"><option value="">Selectionnez d\'abord une ville</option>{% for q in quartiers %}<option value="{{ q.id }}" data-ville="{{ q.ville_id }}" {% if form.quartier_id == q.id|string %}selected{% endif %}>{{ q.nom }}</option>{% endfor %}<option value="autre" {% if form.quartier_libre %}selected{% endif %}>Autre (preciser)...</option></select><input type="text" name="quartier_libre" id="input-quartier-libre-b" placeholder="Precisez votre quartier..." value="{% if form.quartier_libre %}{{ form.quartier_libre }}{% endif %}" style="width:100%;margin-top:8px;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);font-size:14px;{% if not form.quartier_libre %}display:none;{% endif %}"></div>''',
    "ajout du filtrage par ville et de l\'option Autre (preciser) sur le quartier boutique",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    '''<div style="margin-bottom:16px"><label style="font-size:13px;font-weight:600;color:var(--text);display:block;margin-bottom:6px">Quartier / Zone <span style="font-weight:400;color:var(--text-muted)">(optionnel)</span></label><select name="quartier_id" id="select-quartier-b" style="width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);font-size:14px;background:white"><option value="">Selectionnez d'abord une ville</option>{% for q in quartiers %}<option value="{{ q.id }}" data-ville="{{ q.ville_id }}" {% if form.quartier_id == q.id|string %}selected{% endif %}>{{ q.nom }}</option>{% endfor %}<option value="autre" {% if form.quartier_libre %}selected{% endif %}>Autre (preciser)...</option></select><input type="text" name="quartier_libre" id="input-quartier-libre-b" placeholder="Precisez votre quartier..." value="{% if form.quartier_libre %}{{ form.quartier_libre }}{% endif %}" style="width:100%;margin-top:8px;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);font-size:14px;{% if not form.quartier_libre %}display:none;{% endif %}"></div></form>''',
    '''<div style="margin-bottom:16px"><label style="font-size:13px;font-weight:600;color:var(--text);display:block;margin-bottom:6px">Quartier / Zone <span style="font-weight:400;color:var(--text-muted)">(optionnel)</span></label><select name="quartier_id" id="select-quartier-b" style="width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);font-size:14px;background:white"><option value="">Selectionnez d'abord une ville</option>{% for q in quartiers %}<option value="{{ q.id }}" data-ville="{{ q.ville_id }}" {% if form.quartier_id == q.id|string %}selected{% endif %}>{{ q.nom }}</option>{% endfor %}<option value="autre" {% if form.quartier_libre %}selected{% endif %}>Autre (preciser)...</option></select><input type="text" name="quartier_libre" id="input-quartier-libre-b" placeholder="Precisez votre quartier..." value="{% if form.quartier_libre %}{{ form.quartier_libre }}{% endif %}" style="width:100%;margin-top:8px;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);font-size:14px;{% if not form.quartier_libre %}display:none;{% endif %}"></div>
<div style="margin-bottom:16px"><label style="font-size:13px;font-weight:600;color:var(--text);display:block;margin-bottom:6px">Adresse <span style="font-weight:400;color:var(--text-muted)">(pour les boutiques physiques - permet aux clients de vous localiser sur Google Maps)</span></label><input type="text" name="adresse" placeholder="Ex : Avenue de l Independance, face a la pharmacie X, Pointe-Noire" value="{{ form.adresse or '' }}" style="width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);font-size:14px"></div>
<div style="margin-bottom:16px"><label style="font-size:13px;font-weight:600;color:var(--text);display:block;margin-bottom:10px">Horaires d ouverture <span style="font-weight:400;color:var(--text-muted)">(optionnel)</span></label><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="width:78px;font-size:13px;font-weight:600">Lundi</span><label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted)"><input type="checkbox" name="horaire_lun_ferme" id="horaire_lun_ferme" onchange="toggleHoraireJour('lun')"> Ferme</label><input type="time" name="horaire_lun_debut" id="horaire_lun_debut" value="08:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"><span style="font-size:12px;color:var(--text-muted)">a</span><input type="time" name="horaire_lun_fin" id="horaire_lun_fin" value="18:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"></div><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="width:78px;font-size:13px;font-weight:600">Mardi</span><label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted)"><input type="checkbox" name="horaire_mar_ferme" id="horaire_mar_ferme" onchange="toggleHoraireJour('mar')"> Ferme</label><input type="time" name="horaire_mar_debut" id="horaire_mar_debut" value="08:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"><span style="font-size:12px;color:var(--text-muted)">a</span><input type="time" name="horaire_mar_fin" id="horaire_mar_fin" value="18:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"></div><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="width:78px;font-size:13px;font-weight:600">Mercredi</span><label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted)"><input type="checkbox" name="horaire_mer_ferme" id="horaire_mer_ferme" onchange="toggleHoraireJour('mer')"> Ferme</label><input type="time" name="horaire_mer_debut" id="horaire_mer_debut" value="08:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"><span style="font-size:12px;color:var(--text-muted)">a</span><input type="time" name="horaire_mer_fin" id="horaire_mer_fin" value="18:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"></div><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="width:78px;font-size:13px;font-weight:600">Jeudi</span><label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted)"><input type="checkbox" name="horaire_jeu_ferme" id="horaire_jeu_ferme" onchange="toggleHoraireJour('jeu')"> Ferme</label><input type="time" name="horaire_jeu_debut" id="horaire_jeu_debut" value="08:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"><span style="font-size:12px;color:var(--text-muted)">a</span><input type="time" name="horaire_jeu_fin" id="horaire_jeu_fin" value="18:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"></div><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="width:78px;font-size:13px;font-weight:600">Vendredi</span><label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted)"><input type="checkbox" name="horaire_ven_ferme" id="horaire_ven_ferme" onchange="toggleHoraireJour('ven')"> Ferme</label><input type="time" name="horaire_ven_debut" id="horaire_ven_debut" value="08:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"><span style="font-size:12px;color:var(--text-muted)">a</span><input type="time" name="horaire_ven_fin" id="horaire_ven_fin" value="18:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"></div><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="width:78px;font-size:13px;font-weight:600">Samedi</span><label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted)"><input type="checkbox" name="horaire_sam_ferme" id="horaire_sam_ferme" onchange="toggleHoraireJour('sam')"> Ferme</label><input type="time" name="horaire_sam_debut" id="horaire_sam_debut" value="08:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"><span style="font-size:12px;color:var(--text-muted)">a</span><input type="time" name="horaire_sam_fin" id="horaire_sam_fin" value="18:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"></div><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="width:78px;font-size:13px;font-weight:600">Dimanche</span><label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted)"><input type="checkbox" name="horaire_dim_ferme" id="horaire_dim_ferme" onchange="toggleHoraireJour('dim')"> Ferme</label><input type="time" name="horaire_dim_debut" id="horaire_dim_debut" value="08:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"><span style="font-size:12px;color:var(--text-muted)">a</span><input type="time" name="horaire_dim_fin" id="horaire_dim_fin" value="18:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"></div></div>
<div style="margin-bottom:16px"><label style="font-size:13px;font-weight:600;color:var(--text);display:block;margin-bottom:6px">Fermeture temporaire <span style="font-weight:400;color:var(--text-muted)">(optionnel - ex: travaux, conges)</span></label><input type="text" name="fermeture_message" placeholder="Ex : Ferme pour travaux jusqu au 15/08, ou Ferme pour conges annuels" value="{{ form.fermeture_message or '' }}" style="width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);font-size:14px"></div>
</form>''',
    "ajoute les champs adresse, horaires jour par jour et fermeture temporaire au formulaire de creation de boutique",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    """<script>
const ta = document.querySelector('textarea[name=description]');
const counter = document.getElementById('desc-count');
ta.addEventListener('input', () => { counter.textContent = ta.value.length + ' / 500'; });
</script>""",
    """<script>
const ta = document.querySelector('textarea[name=description]');
const counter = document.getElementById('desc-count');
ta.addEventListener('input', () => { counter.textContent = ta.value.length + ' / 500'; });

function updateQuartiersBoutique(villeId) {
  var sel = document.getElementById('select-quartier-b');
  if (!sel) return;
  var opts = sel.querySelectorAll('option[data-ville]');
  opts.forEach(function(opt) { opt.style.display = (opt.dataset.ville === villeId) ? '' : 'none'; });
  sel.value = '';
  var lq = document.getElementById('input-quartier-libre-b');
  if (lq) lq.style.display = 'none';
}
(function(){
  var s = document.getElementById('select-quartier-b');
  var inp = document.getElementById('input-quartier-libre-b');
  if (!s || !inp) return;
  s.addEventListener('change', function(){
    inp.style.display = this.value === 'autre' ? '' : 'none';
    if (this.value === 'autre') inp.focus();
  });
  var v = document.getElementById('select-ville-b');
  if (v && v.value) updateQuartiersBoutique(v.value);
})();
</script>""",
    "javascript de filtrage quartier par ville + bascule du champ Autre (creer_boutique)",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    """  var v = document.getElementById('select-ville-b');
  if (v && v.value) updateQuartiersBoutique(v.value);
})();
</script>""",
    """  var v = document.getElementById('select-ville-b');
  if (v && v.value) updateQuartiersBoutique(v.value);
})();

function toggleHoraireJour(code) {
  var ferme = document.getElementById('horaire_' + code + '_ferme');
  var debut = document.getElementById('horaire_' + code + '_debut');
  var fin = document.getElementById('horaire_' + code + '_fin');
  if (!ferme || !debut || !fin) return;
  debut.disabled = ferme.checked;
  fin.disabled = ferme.checked;
}
</script>""",
    "js pour desactiver les champs heure quand le jour est marque Ferme (creer_boutique)",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/admin.html -- fix lien notification boutiques en attente
# ─────────────────────────────────────────────────────────────
path = "templates/pages/admin.html"
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '''  {% if stats.boutiques_attente > 0 %}
  <a href="#" onclick="showTab(\'boutiques\');return false;" style="display:flex;align-items:center;gap:8px;background:#fee2e2;border:1px solid #ef4444;color:#7f1d1d;padding:10px 16px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none">
    \U0001F534 {{ stats.boutiques_attente }} boutique(s) en attente d\'activation
  </a>
  {% endif %}''',
    '''  {% if stats.boutiques_attente > 0 %}
  <a href="#" onclick="showTab(\'en-attente\');return false;" style="display:flex;align-items:center;gap:8px;background:#fee2e2;border:1px solid #ef4444;color:#7f1d1d;padding:10px 16px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none">
    \U0001F534 {{ stats.boutiques_attente }} boutique(s) en attente d\'activation
  </a>
  {% endif %}''',
    "corrige le lien de notification boutiques en attente pour pointer vers l\'onglet En attente (avec les boutons Approuver/Rejeter) au lieu de l\'onglet Boutiques (simple liste)",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    "{% if stats.paiements_attente > 0 or stats.boutiques_attente > 0 or stats.nb_bugs_ouverts > 0 %}",
    "{% if stats.paiements_attente > 0 or stats.boutiques_attente > 0 or stats.boutiques_non_verifiees > 0 or stats.nb_bugs_ouverts > 0 %}",
    "inclut boutiques_non_verifiees dans la condition d'affichage du bandeau de notifications",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    """  {% if stats.boutiques_attente > 0 %}
  <a href="#" onclick="showTab(\'en-attente\');return false;" style="display:flex;align-items:center;gap:8px;background:#fee2e2;border:1px solid #ef4444;color:#7f1d1d;padding:10px 16px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none">
    \U0001F534 {{ stats.boutiques_attente }} boutique(s) en attente d\'activation
  </a>
  {% endif %}""",
    """  {% if stats.boutiques_attente > 0 %}
  <a href="#" onclick="showTab(\'en-attente\');return false;" style="display:flex;align-items:center;gap:8px;background:#fee2e2;border:1px solid #ef4444;color:#7f1d1d;padding:10px 16px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none">
    \U0001F534 {{ stats.boutiques_attente }} boutique(s) en attente d\'activation
  </a>
  {% endif %}
  {% if stats.boutiques_non_verifiees > 0 %}
  <a href="#" onclick="showTab(\'boutiques\');return false;" style="display:flex;align-items:center;gap:8px;background:#fef9c3;border:1px solid #eab308;color:#713f12;padding:10px 16px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none">
    \U0001F7E1 {{ stats.boutiques_non_verifiees }} boutique(s) active(s) non verifiee(s)
  </a>
  {% endif %}""",
    "ajout d'une notification dediee pour les boutiques actives non verifiees, avec lien direct vers l'onglet Boutiques",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    """<div id="panel-boutiques" style="display:none;margin-bottom:32px">
    <div style="background:white;border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow)">""",
    """<div id="panel-boutiques" style="display:none;margin-bottom:32px">
    <div style="background:white;border:1px solid var(--border);border-radius:var(--radius);overflow-x:auto;box-shadow:var(--shadow)">""",
    "autorise le scroll horizontal du tableau Boutiques pour que le bouton Verifier reste atteignable sur mobile",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/cgu.html -- corrige le prix affiche du plan Business
# ─────────────────────────────────────────────────────────────
path = "templates/pages/cgu.html"
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '<li><strong style="color:var(--text)">Business \u2014 50 000 FCFA/mois</strong>',
    '<li><strong style="color:var(--text)">Business \u2014 25 000 FCFA/mois</strong>',
    "corrige le prix Business affiche dans les CGU (25000 FCFA au lieu de 50000)",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/modifier_boutique.html -- ajoute Adresse, Horaires jour par jour
# et Fermeture temporaire (memes champs que la fiche de creation de boutique)
# ─────────────────────────────────────────────────────────────
path = "templates/pages/modifier_boutique.html"
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '    <div style="margin-bottom:16px">\n      <label style="font-size:13px;font-weight:600;display:block;margin-bottom:6px">Horaires</label>\n      <input type="text" name="horaires" value="{{ b.horaires or \'\' }}" placeholder="Ex: Lun-Sam 8h-18h" style="width:100%;padding:10px 14px;border:1px solid var(--border);border-radius:8px;font-size:14px;box-sizing:border-box">\n    </div>',
    '    <div style="margin-bottom:16px">\n      <label style="font-size:13px;font-weight:600;display:block;margin-bottom:6px">Adresse <span style="font-weight:400;color:var(--text-muted)">(pour les boutiques physiques - permet aux clients de vous localiser sur Google Maps)</span></label>\n      <input type="text" name="adresse" value="{{ b.adresse or \'\' }}" placeholder="Ex : Avenue de l Independance, face a la pharmacie X, Pointe-Noire" style="width:100%;padding:10px 14px;border:1px solid var(--border);border-radius:8px;font-size:14px;box-sizing:border-box">\n    </div>\n    <div style="margin-bottom:16px">\n      <label style="font-size:13px;font-weight:600;display:block;margin-bottom:10px">Horaires d ouverture <span style="font-weight:400;color:var(--text-muted)">(reglez chaque jour, puis enregistrez)</span></label>\n      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="width:78px;font-size:13px;font-weight:600">Lundi</span><label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted)"><input type="checkbox" name="horaire_lun_ferme" id="horaire_lun_ferme" onchange="toggleHoraireJourM(\'lun\')"> Ferme</label><input type="time" name="horaire_lun_debut" id="horaire_lun_debut" value="08:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"><span style="font-size:12px;color:var(--text-muted)">a</span><input type="time" name="horaire_lun_fin" id="horaire_lun_fin" value="18:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"></div><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="width:78px;font-size:13px;font-weight:600">Mardi</span><label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted)"><input type="checkbox" name="horaire_mar_ferme" id="horaire_mar_ferme" onchange="toggleHoraireJourM(\'mar\')"> Ferme</label><input type="time" name="horaire_mar_debut" id="horaire_mar_debut" value="08:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"><span style="font-size:12px;color:var(--text-muted)">a</span><input type="time" name="horaire_mar_fin" id="horaire_mar_fin" value="18:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"></div><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="width:78px;font-size:13px;font-weight:600">Mercredi</span><label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted)"><input type="checkbox" name="horaire_mer_ferme" id="horaire_mer_ferme" onchange="toggleHoraireJourM(\'mer\')"> Ferme</label><input type="time" name="horaire_mer_debut" id="horaire_mer_debut" value="08:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"><span style="font-size:12px;color:var(--text-muted)">a</span><input type="time" name="horaire_mer_fin" id="horaire_mer_fin" value="18:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"></div><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="width:78px;font-size:13px;font-weight:600">Jeudi</span><label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted)"><input type="checkbox" name="horaire_jeu_ferme" id="horaire_jeu_ferme" onchange="toggleHoraireJourM(\'jeu\')"> Ferme</label><input type="time" name="horaire_jeu_debut" id="horaire_jeu_debut" value="08:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"><span style="font-size:12px;color:var(--text-muted)">a</span><input type="time" name="horaire_jeu_fin" id="horaire_jeu_fin" value="18:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"></div><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="width:78px;font-size:13px;font-weight:600">Vendredi</span><label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted)"><input type="checkbox" name="horaire_ven_ferme" id="horaire_ven_ferme" onchange="toggleHoraireJourM(\'ven\')"> Ferme</label><input type="time" name="horaire_ven_debut" id="horaire_ven_debut" value="08:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"><span style="font-size:12px;color:var(--text-muted)">a</span><input type="time" name="horaire_ven_fin" id="horaire_ven_fin" value="18:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"></div><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="width:78px;font-size:13px;font-weight:600">Samedi</span><label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted)"><input type="checkbox" name="horaire_sam_ferme" id="horaire_sam_ferme" onchange="toggleHoraireJourM(\'sam\')"> Ferme</label><input type="time" name="horaire_sam_debut" id="horaire_sam_debut" value="08:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"><span style="font-size:12px;color:var(--text-muted)">a</span><input type="time" name="horaire_sam_fin" id="horaire_sam_fin" value="18:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"></div><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><span style="width:78px;font-size:13px;font-weight:600">Dimanche</span><label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted)"><input type="checkbox" name="horaire_dim_ferme" id="horaire_dim_ferme" onchange="toggleHoraireJourM(\'dim\')"> Ferme</label><input type="time" name="horaire_dim_debut" id="horaire_dim_debut" value="08:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"><span style="font-size:12px;color:var(--text-muted)">a</span><input type="time" name="horaire_dim_fin" id="horaire_dim_fin" value="18:00" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px"></div>\n    </div>\n    <div style="margin-bottom:16px">\n      <label style="font-size:13px;font-weight:600;display:block;margin-bottom:6px">Fermeture temporaire <span style="font-weight:400;color:var(--text-muted)">(optionnel - ex: travaux, conges)</span></label>\n      <input type="text" name="fermeture_message" value="{{ b.fermeture_message or \'\' }}" placeholder="Ex : Ferme pour travaux jusqu au 15/08, ou Ferme pour conges annuels" style="width:100%;padding:10px 14px;border:1px solid var(--border);border-radius:8px;font-size:14px;box-sizing:border-box">\n    </div>',
    "remplace le simple champ Horaires par Adresse + horaires jour par jour + fermeture temporaire, comme sur la fiche de creation",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    '    <button type="submit" style="width:100%;padding:13px;background:var(--primary);color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer">Enregistrer les modifications</button>\n    <a href="/dashboard" style="display:block;text-align:center;margin-top:12px;font-size:13px;color:var(--text-muted)">Annuler</a>\n  </form>\n</div>\n{% endblock %}',
    '    <button type="submit" style="width:100%;padding:13px;background:var(--primary);color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer">Enregistrer les modifications</button>\n    <a href="/dashboard" style="display:block;text-align:center;margin-top:12px;font-size:13px;color:var(--text-muted)">Annuler</a>\n  </form>\n</div>\n{% endblock %}\n\n{% block scripts %}\n<script>\nfunction toggleHoraireJourM(code) {\n  var ferme = document.getElementById(\'horaire_\' + code + \'_ferme\');\n  var debut = document.getElementById(\'horaire_\' + code + \'_debut\');\n  var fin = document.getElementById(\'horaire_\' + code + \'_fin\');\n  if (!ferme || !debut || !fin) return;\n  debut.disabled = ferme.checked;\n  fin.disabled = ferme.checked;\n}\n</script>\n{% endblock %}',
    "ajoute le bloc scripts avec toggleHoraireJourM pour desactiver les heures des jours de fermeture",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/dashboard.html -- corrige le prix affiche du lien upgrade Business
# ─────────────────────────────────────────────────────────────
path = "templates/pages/dashboard.html"
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    "\u2b06 Passer en Business (50 000 FCFA) \u2192",
    "\u2b06 Passer en Business (25 000 FCFA) \u2192",
    "corrige le prix Business affiche sur le lien d'upgrade du dashboard vendeur (25000 FCFA au lieu de 50000)",
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
for _fname, _out in [("app.py", "live_snapshot_app.py"), ("database.py", "live_snapshot_database.py"), ("templates/pages/annonce.html", "live_snapshot_annonce.html"), ("templates/pages/boutique.html", "live_snapshot_boutique.html"), ("templates/pages/creer_boutique.html", "live_snapshot_creer_boutique.html"), ("templates/pages/deposer_annonce.html", "live_snapshot_deposer_annonce.html"), ("templates/pages/admin.html", "live_snapshot_admin.html"), ("templates/pages/cgu.html", "live_snapshot_cgu.html"), ("templates/pages/dashboard.html", "live_snapshot_dashboard.html"), ("templates/pages/tarifs.html", "live_snapshot_tarifs.html"), ("templates/pages/modifier_boutique.html", "live_snapshot_modifier_boutique.html")]:
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
