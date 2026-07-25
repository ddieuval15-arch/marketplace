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
_list_dir(f"/home/{PA_USER}/hellobiz/templates/pages/")

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
# database.py -- ajoute la colonne disponibilite_type pour les boutiques de service
# ─────────────────────────────────────────────────────────────
path = 'database.py'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '"ALTER TABLE boutiques ADD COLUMN fermeture_message TEXT",\n    ]',
    '"ALTER TABLE boutiques ADD COLUMN fermeture_message TEXT",\n        "ALTER TABLE boutiques ADD COLUMN disponibilite_type TEXT",\n    ]',
    'ajoute la colonne disponibilite_type a la table boutiques (horaires / disponible / reservation)',
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# app.py -- creer_boutique() capture le type de disponibilite
# ─────────────────────────────────────────────────────────────
path = 'app.py'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    "            adresse_b = form.get('adresse', '')[:300]\n            fermeture_message_b = form.get('fermeture_message', '')[:300]\n",
    "            adresse_b = form.get('adresse', '')[:300]\n            fermeture_message_b = form.get('fermeture_message', '')[:300]\n            disponibilite_type_b = form.get('disponibilite_type', 'horaires')\n            if disponibilite_type_b not in ('horaires', 'disponible', 'reservation'):\n                disponibilite_type_b = 'horaires'\n",
    'capture disponibilite_type a la creation de boutique (horaires par defaut)',
)
changed = changed or ch

c, ch = apply_patch(
    c,
    "            db.execute('''INSERT INTO boutiques\n                (slug,nom,description,categorie_id,ville_id,quartier_id,telephone,whatsapp,email,plan,vendeur_id,actif,logo,banniere,adresse,horaires,fermeture_message)\n                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''  ,\n                (slug, nom, desc, cat_id, ville_id, quartier_id_b, tel, wa, vendeur['email'], plan,\n                 session['vendeur_id'], actif_initial, logo_fname, banniere_fname, adresse_b, horaires_b, fermeture_message_b))\n",
    "            db.execute('''INSERT INTO boutiques\n                (slug,nom,description,categorie_id,ville_id,quartier_id,telephone,whatsapp,email,plan,vendeur_id,actif,logo,banniere,adresse,horaires,fermeture_message,disponibilite_type)\n                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''  ,\n                (slug, nom, desc, cat_id, ville_id, quartier_id_b, tel, wa, vendeur['email'], plan,\n                 session['vendeur_id'], actif_initial, logo_fname, banniere_fname, adresse_b, horaires_b, fermeture_message_b, disponibilite_type_b))\n",
    "inclut disponibilite_type dans l'INSERT de creation de boutique",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# app.py -- modifier_boutique() capture le type de disponibilite
# ─────────────────────────────────────────────────────────────
path = 'app.py'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    "        adresse=form.get('adresse',b['adresse'] or '')\n        fermeture_message=form.get('fermeture_message',b['fermeture_message'] or '')\n",
    "        adresse=form.get('adresse',b['adresse'] or '')\n        fermeture_message=form.get('fermeture_message',b['fermeture_message'] or '')\n        disponibilite_type=form.get('disponibilite_type', b['disponibilite_type'] if 'disponibilite_type' in b.keys() and b['disponibilite_type'] else 'horaires')\n        if disponibilite_type not in ('horaires','disponible','reservation'):\n            disponibilite_type='horaires'\n",
    'capture disponibilite_type a la modification de boutique',
)
changed = changed or ch

c, ch = apply_patch(
    c,
    '        db.execute("UPDATE boutiques SET nom=?,description=?,telephone=?,whatsapp=?,email=?,logo=?,banniere=?,horaires=?,site_web=?,facebook=?,instagram=?,adresse=?,fermeture_message=? WHERE vendeur_id=?",\n                (nom,description,telephone,whatsapp,email,logo,banniere,horaires,site_web,facebook,instagram,adresse,fermeture_message,session[\'vendeur_id\']))\n',
    '        db.execute("UPDATE boutiques SET nom=?,description=?,telephone=?,whatsapp=?,email=?,logo=?,banniere=?,horaires=?,site_web=?,facebook=?,instagram=?,adresse=?,fermeture_message=?,disponibilite_type=? WHERE vendeur_id=?",\n                (nom,description,telephone,whatsapp,email,logo,banniere,horaires,site_web,facebook,instagram,adresse,fermeture_message,disponibilite_type,session[\'vendeur_id\']))\n',
    "inclut disponibilite_type dans l'UPDATE de modification de boutique",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/creer_boutique.html -- ajoute le type de disponibilite (en plus des horaires, ne les remplace pas)
# ─────────────────────────────────────────────────────────────
path = 'templates/pages/creer_boutique.html'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '<div style="margin-bottom:16px"><label style="font-size:13px;font-weight:600;color:var(--text);display:block;margin-bottom:6px">Fermeture temporaire',
    '<div style="margin-bottom:16px"><label style="font-size:13px;font-weight:600;color:var(--text);display:block;margin-bottom:10px">Disponibilite <span style="font-weight:400;color:var(--text-muted)">(pour les prestations de service - optionnel)</span></label><label style="display:flex;align-items:center;gap:6px;font-size:13px;margin-bottom:8px"><input type="radio" name="disponibilite_type" value="horaires" checked> Horaires fixes (voir ci-dessus)</label><label style="display:flex;align-items:center;gap:6px;font-size:13px;margin-bottom:8px"><input type="radio" name="disponibilite_type" value="disponible"> Disponible maintenant</label><label style="display:flex;align-items:center;gap:6px;font-size:13px"><input type="radio" name="disponibilite_type" value="reservation"> Sur reservation / rendez-vous uniquement</label></div><div style="margin-bottom:16px"><label style="font-size:13px;font-weight:600;color:var(--text);display:block;margin-bottom:6px">Fermeture temporaire',
    'ajoute le choix Disponibilite (Horaires fixes / Disponible maintenant / Sur reservation) en plus du bloc horaires, pour les boutiques de service',
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/modifier_boutique.html -- ajoute le type de disponibilite (en plus des horaires, ne les remplace pas)
# ─────────────────────────────────────────────────────────────
path = 'templates/pages/modifier_boutique.html'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '    <div style="margin-bottom:16px">\n      <label style="font-size:13px;font-weight:600;display:block;margin-bottom:6px">Fermeture temporaire',
    '    <div style="margin-bottom:16px">\n      <label style="font-size:13px;font-weight:600;display:block;margin-bottom:10px">Disponibilite <span style="font-weight:400;color:var(--text-muted)">(pour les prestations de service - optionnel)</span></label>\n      <label style="display:flex;align-items:center;gap:6px;font-size:13px;margin-bottom:8px"><input type="radio" name="disponibilite_type" value="horaires" {{ \'checked\' if (b.disponibilite_type or \'horaires\')==\'horaires\' else \'\' }}> Horaires fixes (voir ci-dessus)</label>\n      <label style="display:flex;align-items:center;gap:6px;font-size:13px;margin-bottom:8px"><input type="radio" name="disponibilite_type" value="disponible" {{ \'checked\' if b.disponibilite_type==\'disponible\' else \'\' }}> Disponible maintenant</label>\n      <label style="display:flex;align-items:center;gap:6px;font-size:13px"><input type="radio" name="disponibilite_type" value="reservation" {{ \'checked\' if b.disponibilite_type==\'reservation\' else \'\' }}> Sur reservation / rendez-vous uniquement</label>\n    </div>\n    <div style="margin-bottom:16px">\n      <label style="font-size:13px;font-weight:600;display:block;margin-bottom:6px">Fermeture temporaire',
    'ajoute le choix Disponibilite (Horaires fixes / Disponible maintenant / Sur reservation) en plus du bloc horaires, pre-rempli depuis b.disponibilite_type',
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/boutique.html -- affiche le badge de disponibilite (Disponible maintenant / Sur reservation)
# ─────────────────────────────────────────────────────────────
path = 'templates/pages/boutique.html'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '<!-- HORAIRES -->\n  {% if boutique.horaires %}\n  <div style="background:var(--card-bg);border:1px solid var(--border);border-radius:var(--radius);padding:16px 20px;margin-bottom:20px;display:flex;align-items:flex-start;gap:14px">\n    <i class="ti ti-clock" style="font-size:20px;color:var(--primary);flex-shrink:0;margin-top:2px"></i>\n    <div>\n      <div style="font-size:13px;font-weight:700;margin-bottom:4px">Horaires d\'ouverture</div>\n      <div style="font-size:13px;color:var(--text-muted);white-space:pre-line">{{ boutique.horaires }}</div>\n    </div>\n  </div>\n  {% endif %}\n\n  ',
    '<!-- HORAIRES -->\n  {% if boutique.horaires %}\n  <div style="background:var(--card-bg);border:1px solid var(--border);border-radius:var(--radius);padding:16px 20px;margin-bottom:20px;display:flex;align-items:flex-start;gap:14px">\n    <i class="ti ti-clock" style="font-size:20px;color:var(--primary);flex-shrink:0;margin-top:2px"></i>\n    <div>\n      <div style="font-size:13px;font-weight:700;margin-bottom:4px">Horaires d\'ouverture</div>\n      <div style="font-size:13px;color:var(--text-muted);white-space:pre-line">{{ boutique.horaires }}</div>\n    </div>\n  </div>\n  {% endif %}\n\n  \n  <!-- DISPONIBILITE -->\n  {% if boutique.disponibilite_type == \'disponible\' %}\n  <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:var(--radius);padding:14px 20px;margin-bottom:20px;display:flex;align-items:center;gap:12px">\n    <i class="ti ti-circle-check" style="font-size:20px;color:#16a34a;flex-shrink:0"></i>\n    <div style="font-size:13px;font-weight:700;color:#166534">Disponible maintenant</div>\n  </div>\n  {% elif boutique.disponibilite_type == \'reservation\' %}\n  <div style="background:var(--card-bg);border:1px solid var(--border);border-radius:var(--radius);padding:14px 20px;margin-bottom:20px;display:flex;align-items:center;gap:12px">\n    <i class="ti ti-calendar-event" style="font-size:20px;color:var(--primary);flex-shrink:0"></i>\n    <div style="font-size:13px;font-weight:700">Sur reservation / rendez-vous uniquement</div>\n  </div>\n  {% endif %}\n',
    'affiche un badge Disponible maintenant / Sur reservation en plus du bloc horaires existant',
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# app.py -- corrige le tri des boutiques pour prioriser Business (plan le plus cher, 25000 FCFA) avant Premium/Pro/Starter/Gratuit
# ─────────────────────────────────────────────────────────────
path = 'app.py'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '    boutiques = db.execute(\'\'\'\n        SELECT b.*, c.nom as cat_nom FROM boutiques b\n        JOIN categories c ON b.categorie_id = c.id\n        WHERE b.actif = 1\n        ORDER BY CASE WHEN b.plan="premium" THEN 0 WHEN b.plan="pro" THEN 1 ELSE 2 END, b.badge_verifie DESC\n        LIMIT 8\n    \'\'\').fetchall()',
    '    boutiques = db.execute(\'\'\'\n        SELECT b.*, c.nom as cat_nom FROM boutiques b\n        JOIN categories c ON b.categorie_id = c.id\n        WHERE b.actif = 1\n        ORDER BY CASE WHEN b.plan IN ("premium","business") THEN 0 WHEN b.plan="pro" THEN 1 ELSE 2 END, b.badge_verifie DESC\n        LIMIT 8\n    \'\'\').fetchall()',
    "priorise les boutiques Business dans le tri de la section boutiques en avant (page d'accueil) -- Business etait auparavant traite comme Gratuit/Starter",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    '        SELECT b.*, c.nom as cat_nom, COUNT(a.id) as nb_annonces\n        FROM boutiques b JOIN categories c ON b.categorie_id=c.id\n        LEFT JOIN annonces a ON a.boutique_id=b.id AND a.statut="active"\n        WHERE b.actif=1 GROUP BY b.id\n        ORDER BY CASE WHEN b.plan="premium" THEN 0 WHEN b.plan="pro" THEN 1 ELSE 2 END, b.badge_verifie DESC\n    \'\'\').fetchall()',
    '        SELECT b.*, c.nom as cat_nom, COUNT(a.id) as nb_annonces\n        FROM boutiques b JOIN categories c ON b.categorie_id=c.id\n        LEFT JOIN annonces a ON a.boutique_id=b.id AND a.statut="active"\n        WHERE b.actif=1 GROUP BY b.id\n        ORDER BY CASE WHEN b.plan IN ("premium","business") THEN 0 WHEN b.plan="pro" THEN 1 ELSE 2 END, b.badge_verifie DESC\n    \'\'\').fetchall()',
    "priorise les boutiques Business dans le tri de la page Toutes les boutiques -- meme bug que sur la page d'accueil",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# app.py -- boutiques() selectionne aussi l'icone de categorie
# ─────────────────────────────────────────────────────────────
path = 'app.py'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    'SELECT b.*, c.nom as cat_nom, COUNT(a.id) as nb_annonces',
    'SELECT b.*, c.nom as cat_nom, c.icon as cat_icon, COUNT(a.id) as nb_annonces',
    'ajoute c.icon (cat_icon) a la requete de la page Toutes les boutiques, pour afficher une icone par categorie',
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/base.html -- ajoute le CSS manquant pour le badge Verifie et la bordure Business
# ─────────────────────────────────────────────────────────────
path = 'templates/base.html'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '    .plan-badge.business { background: linear-gradient(135deg,#0a0a0a,#1a1a1a); color: #F5C518; border: 1px solid #F5C518; letter-spacing: 0.5px; }',
    '    .plan-badge.business { background: linear-gradient(135deg,#0a0a0a,#1a1a1a); color: #F5C518; border: 1px solid #F5C518; letter-spacing: 0.5px; }\n    .badge-verifie { display: inline-flex; align-items: center; gap: 3px; background: var(--primary-light); color: var(--primary); font-size: 10px; font-weight: 700; padding: 3px 9px; border-radius: 20px; }\n    .boutique-card.tier-business { border: 1.5px solid #F5C518; }',
    'ajoute le style manquant .badge-verifie (jamais defini) et une bordure doree pour les cartes boutiques plan Business, coherente avec .plan-badge.business deja existant',
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/boutiques.html -- redesign de la carte boutique (logo, icone categorie, hierarchie des plans, 0 annonce)
# ─────────────────────────────────────────────────────────────
path = 'templates/pages/boutiques.html'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '      <a href="/boutique/{{ b.slug }}" class="boutique-card" style="padding:18px">\n        <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">\n          <div class="boutique-avatar">{{ b.nom[:2].upper() }}</div>\n          <div>\n            <div class="boutique-name">{{ b.nom }}</div>\n            <div class="boutique-cat">{{ b.cat_nom }}</div>\n          </div>\n        </div>\n        <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;line-height:1.5">{{ b.description[:80] }}…</div>\n        <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:6px">\n          {% if b.badge_verifie %}\n            <span class="badge-verifie"><i class="ti ti-shield-check" style="font-size:10px"></i> Vérifié</span>\n          {% endif %}\n          <span class="badge-plan {{ b.plan }}">{{ b.plan|capitalize }}</span>\n        </div>\n        <div style="font-size:11px;color:var(--text-light)"><i class="ti ti-speakerphone" style="font-size:12px;color:var(--primary)"></i> {{ b.nb_annonces }} annonce{{ \'s\' if b.nb_annonces > 1 else \'\' }}</div>\n      </a>',
    '      <a href="/boutique/{{ b.slug }}" class="boutique-card{{ \' tier-business\' if b.plan == \'business\' else \'\' }}" style="padding:18px">\n        <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">\n          <div class="boutique-logo" style="width:46px;height:46px;font-size:15px;margin:0">{% if b.logo %}<img src="{{ url_for(\'static\', filename=\'uploads/\' + b.logo) }}" alt="">{% else %}{{ b.nom[:2].upper() }}{% endif %}</div>\n          <div>\n            <div class="boutique-name">{{ b.nom }}</div>\n            <div class="boutique-cat"><i class="ti ti-{{ b.cat_icon or \'tag\' }}" style="font-size:11px;margin-right:2px"></i>{{ b.cat_nom }}</div>\n          </div>\n        </div>\n        <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;line-height:1.5">{{ b.description[:80] }}…</div>\n        <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:6px">\n          {% if b.badge_verifie %}\n            <span class="badge-verifie">{% if b.plan == \'business\' %}<i class="ti ti-crown" style="font-size:10px"></i>{% else %}<i class="ti ti-shield-check" style="font-size:10px"></i>{% endif %} Vérifié</span>\n          {% endif %}\n          <span class="plan-badge {{ b.plan }}">{{ b.plan|capitalize }}</span>\n        </div>\n        <div style="font-size:11px;color:var(--text-light)"><i class="ti ti-speakerphone" style="font-size:12px;color:var(--primary)"></i> {% if b.nb_annonces > 0 %}{{ b.nb_annonces }} annonce{{ \'s\' if b.nb_annonces > 1 else \'\' }}{% else %}Nouvelle boutique{% endif %}</div>\n      </a>',
    "corrige les classes CSS de la carte boutique (boutique-avatar -> boutique-logo, badge-plan -> plan-badge, qui existaient deja stylees dans base.html mais n'etaient pas utilisees), affiche le logo de la boutique si present, ajoute l'icone de categorie, couronne pour Verifie Business, et 'Nouvelle boutique' au lieu de '0 annonce'",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# app.py -- recherche() selectionne aussi le logo de la boutique
# ─────────────────────────────────────────────────────────────
path = 'app.py'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    "        SELECT a.*, c.icon as cat_icon, c.slug as cat_slug, v.nom as ville_nom,\n               b.plan as boutique_plan, qr.nom as quartier_nom,\n               (SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url,\n               CASE WHEN datetime(a.created_at) >= datetime('now', '-48 hours') THEN 1 ELSE 0 END as is_new\n        {base} ORDER BY {order} LIMIT ? OFFSET ?",
    "        SELECT a.*, c.icon as cat_icon, c.slug as cat_slug, v.nom as ville_nom,\n               b.plan as boutique_plan, b.logo as boutique_logo, qr.nom as quartier_nom,\n               (SELECT url FROM photos WHERE annonce_id=a.id AND principale=1 LIMIT 1) as photo_url,\n               CASE WHEN datetime(a.created_at) >= datetime('now', '-48 hours') THEN 1 ELSE 0 END as is_new\n        {base} ORDER BY {order} LIMIT ? OFFSET ?",
    "ajoute b.logo (boutique_logo) a la requete de recherche, pour afficher le logo du vendeur en vignette quand l'annonce n'a pas de photo",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/base.html -- ajoute le badge Business (dore) sur les cartes d'annonces
# ─────────────────────────────────────────────────────────────
path = 'templates/base.html'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '    .ad-badge.premium { background: #ede9fe; color: var(--premium); }',
    '    .ad-badge.premium { background: #ede9fe; color: var(--premium); }\n    .ad-badge.business { background: linear-gradient(135deg,#0a0a0a,#1a1a1a); color: #F5C518; border: 1px solid #F5C518; }',
    "ajoute .ad-badge.business (dore, coherent avec .plan-badge.business), qui n'existait pas -- les annonces de boutiques Business n'avaient aucun badge",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/recherche.html -- redesign de la carte annonce (logo en fallback photo, badge Business)
# ─────────────────────────────────────────────────────────────
path = 'templates/pages/recherche.html'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '              <div class="ad-img">\n                {% if a.photo_url %}\n                  <img src="/static/uploads/thumb_{{ a.photo_url }}" alt="{{ a.titre }}" style="width:100%;height:100%;object-fit:cover">\n                {% else %}\n                  <i class="ti ti-{{ a.cat_icon }}"></i>\n                {% endif %}\n                <div class="ad-badges">\n                  {% if a.boutique_plan == \'premium\' %}<span class="ad-badge premium">Premium</span>\n                  {% elif a.boutique_plan == \'pro\' %}<span class="ad-badge pro">Pro</span>{% endif %}\n                  {% if a.urgent %}<span class="ad-badge urgent">🔴 Urgent</span>{% endif %}\n                  {% if a.is_new %}<span class="ad-badge nouveau">Nouveau</span>{% endif %}\n                </div>\n              </div>',
    '              <div class="ad-img"{% if not a.photo_url and a.boutique_logo %} style="background:var(--primary-light)"{% endif %}>\n                {% if a.photo_url %}\n                  <img src="/static/uploads/thumb_{{ a.photo_url }}" alt="{{ a.titre }}" style="width:100%;height:100%;object-fit:cover">\n                {% elif a.boutique_logo %}\n                  <img src="/static/uploads/{{ a.boutique_logo }}" alt="{{ a.titre }}" style="width:64px;height:64px;object-fit:cover;border-radius:50%;border:1px solid var(--border)">\n                {% else %}\n                  <i class="ti ti-{{ a.cat_icon }}"></i>\n                {% endif %}\n                <div class="ad-badges">\n                  {% if a.boutique_plan == \'business\' %}<span class="ad-badge business">Business</span>\n                  {% elif a.boutique_plan == \'premium\' %}<span class="ad-badge premium">Premium</span>\n                  {% elif a.boutique_plan == \'pro\' %}<span class="ad-badge pro">Pro</span>{% endif %}\n                  {% if a.urgent %}<span class="ad-badge urgent">🔴 Urgent</span>{% endif %}\n                  {% if a.is_new %}<span class="ad-badge nouveau">Nouveau</span>{% endif %}\n                </div>\n              </div>',
    "affiche le logo de la boutique en vignette ronde (plutot qu'une simple icone de categorie) quand l'annonce n'a pas de photo, et ajoute le badge Business manquant (les annonces de vendeurs Business n'affichaient aucun badge)",
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
# database.py -- table site_config (si absente) + config par defaut levee investisseur
# ─────────────────────────────────────────────────────────────
print("=== database.py (config investisseur) ===")
path = 'database.py'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '        "ALTER TABLE boutiques ADD COLUMN disponibilite_type TEXT",\n    ]\n    for sql in migrations:\n        try:\n            c.execute(sql)\n        except Exception:\n            pass\n\n    # Seed quartiers',
    '        "ALTER TABLE boutiques ADD COLUMN disponibilite_type TEXT",\n        "CREATE TABLE IF NOT EXISTS site_config (cle TEXT PRIMARY KEY, valeur TEXT)",\n    ]\n    for sql in migrations:\n        try:\n            c.execute(sql)\n        except Exception:\n            pass\n\n    # Levee investisseur -- valeurs par defaut (modifiables depuis l\'admin)\n    _inv_defaults = [\n        (\'investisseur_ouverture\', \'2026-07-27\'),\n        (\'investisseur_cloture\', \'2026-09-25\'),\n        (\'investisseur_places_dispo\', \'10\'),\n        (\'investisseur_pct_dispo\', \'49\'),\n        (\'investisseur_actif\', \'1\'),\n    ]\n    for _k, _v in _inv_defaults:\n        try:\n            c.execute("INSERT OR IGNORE INTO site_config (cle, valeur) VALUES (?, ?)", (_k, _v))\n        except Exception:\n            pass\n\n    # Seed quartiers',
    "ajoute CREATE TABLE IF NOT EXISTS site_config (deja utilisee en prod mais jamais tracee en migration) + seed des valeurs par defaut de la levee investisseur (ouverture 2026-07-27, cloture 2026-09-25, 10 places, 49% dispo, bandeau actif)",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# app.py -- expose la config investisseur a index() et admin(), ajoute la route de mise a jour
# ─────────────────────────────────────────────────────────────
print("=== app.py (config investisseur) ===")
path = 'app.py'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    "    db.close()\n    return render_template('pages/index.html',\n        villes=villes, categories=categories, stats=stats,\n        annonces_recentes=annonces, boutiques_vedettes=boutiques,\n        mes_favoris_ids=mes_favoris_ids, bon_plan=bon_plan,\n           boutique_du_jour=boutique_du_jour)",
    '    _inv_rows = db.execute("SELECT cle, valeur FROM site_config WHERE cle LIKE \'investisseur_%\'").fetchall()\n    investisseur = {r[\'cle\'].replace(\'investisseur_\', \'\'): r[\'valeur\'] for r in _inv_rows}\n    investisseur.setdefault(\'actif\', \'0\')\n    investisseur.setdefault(\'cloture\', \'\')\n    investisseur.setdefault(\'places_dispo\', \'0\')\n    investisseur.setdefault(\'pct_dispo\', \'0\')\n    db.close()\n    return render_template(\'pages/index.html\',\n        villes=villes, categories=categories, stats=stats,\n        annonces_recentes=annonces, boutiques_vedettes=boutiques,\n        mes_favoris_ids=mes_favoris_ids, bon_plan=bon_plan,\n           boutique_du_jour=boutique_du_jour, investisseur=investisseur)',
    "index() : recupere la config site_config investisseur_* et la passe au template sous investisseur",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    '    _cfg_periode = db.execute("SELECT valeur FROM site_config WHERE cle=\'plan_gratuit_periode\'").fetchone()\n    plan_gratuit_periode = _cfg_periode[0] if _cfg_periode else \'monthly\'',
    '    _cfg_periode = db.execute("SELECT valeur FROM site_config WHERE cle=\'plan_gratuit_periode\'").fetchone()\n    plan_gratuit_periode = _cfg_periode[0] if _cfg_periode else \'monthly\'\n    _inv_rows_adm = db.execute("SELECT cle, valeur FROM site_config WHERE cle LIKE \'investisseur_%\'").fetchall()\n    investisseur_cfg = {r[\'cle\'].replace(\'investisseur_\', \'\'): r[\'valeur\'] for r in _inv_rows_adm}\n    investisseur_cfg.setdefault(\'actif\', \'0\')\n    investisseur_cfg.setdefault(\'cloture\', \'\')\n    investisseur_cfg.setdefault(\'places_dispo\', \'0\')\n    investisseur_cfg.setdefault(\'pct_dispo\', \'0\')',
    "admin() : recupere la config investisseur pour prefill le formulaire admin",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    "    return render_template('pages/admin.html', stats=stats, vendeurs=vendeurs, plan_gratuit_periode=plan_gratuit_periode,\n        boutiques=boutiques_all, annonces=annonces_all, paiements=paiements_all,\n        offres_emploi=offres_emploi, villes=villes, categories=categories,\n            boutiques_en_attente=boutiques_en_attente, ambassadeurs=ambassadeurs)",
    "    return render_template('pages/admin.html', stats=stats, vendeurs=vendeurs, plan_gratuit_periode=plan_gratuit_periode,\n        boutiques=boutiques_all, annonces=annonces_all, paiements=paiements_all,\n        offres_emploi=offres_emploi, villes=villes, categories=categories,\n            boutiques_en_attente=boutiques_en_attente, ambassadeurs=ambassadeurs, investisseur_cfg=investisseur_cfg)",
    "admin() : passe investisseur_cfg au template admin.html",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    '    flash(f"Plan gratuit : mode {new_val} activé.", \'success\')\n    return redirect(url_for(\'admin\'))\n\n\n\n@app.route(\'/admin/boutiques-importees\')',
    '    flash(f"Plan gratuit : mode {new_val} activé.", \'success\')\n    return redirect(url_for(\'admin\'))\n\n\n@app.route(\'/admin/config/investisseur\', methods=[\'POST\'])\n@admin_required\ndef admin_config_investisseur():\n    db = get_db()\n    places = request.form.get(\'places_dispo\', \'\').strip()\n    pct = request.form.get(\'pct_dispo\', \'\').strip()\n    cloture = request.form.get(\'cloture\', \'\').strip()\n    actif = \'1\' if request.form.get(\'actif\') == \'on\' else \'0\'\n    if places:\n        db.execute("INSERT OR REPLACE INTO site_config (cle, valeur) VALUES (\'investisseur_places_dispo\', ?)", (places,))\n    if pct:\n        db.execute("INSERT OR REPLACE INTO site_config (cle, valeur) VALUES (\'investisseur_pct_dispo\', ?)", (pct,))\n    if cloture:\n        db.execute("INSERT OR REPLACE INTO site_config (cle, valeur) VALUES (\'investisseur_cloture\', ?)", (cloture,))\n    db.execute("INSERT OR REPLACE INTO site_config (cle, valeur) VALUES (\'investisseur_actif\', ?)", (actif,))\n    db.commit()\n    db.close()\n    flash(\'Configuration de la levée investisseur mise à jour.\', \'success\')\n    return redirect(url_for(\'admin\'))\n\n\n@app.route(\'/admin/boutiques-importees\')',
    "ajoute la route /admin/config/investisseur (POST) pour mettre a jour places_dispo, pct_dispo, cloture, actif",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/admin.html -- carte de controle de la levee investisseur
# ─────────────────────────────────────────────────────────────
print("=== templates/pages/admin.html (controle levee investisseur) ===")
path = 'templates/pages/admin.html'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '<div style="background:white;border:1px solid var(--border);border-radius:var(--radius);padding:16px 20px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between;">\n  <div>\n    <div style="font-weight:700;font-size:14px;color:var(--text)">&#9881; Quota plan Gratuit</div>\n    <div style="font-size:12px;color:var(--text-muted);margin-top:2px">\n      Mode actuel : <strong>{{ \'Quotidien (24h)\' if plan_gratuit_periode == \'daily\' else \'Mensuel\' }}</strong>\n    </div>\n  </div>\n  <form action="/admin/config/toggle-plan-periode" method="POST">\n    <button type="submit" style="background:{{ \'#10b981\' if plan_gratuit_periode == \'daily\' else \'#6b7280\' }};color:white;border:none;padding:8px 16px;border-radius:8px;font-weight:600;font-size:13px;cursor:pointer;">\n      {{ \'Daily actif - Passer en Mensuel\' if plan_gratuit_periode == \'daily\' else \'Activer le Daily (24h)\' }}\n    </button>\n  </form>\n</div>',
    '<div style="background:white;border:1px solid var(--border);border-radius:var(--radius);padding:16px 20px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between;">\n  <div>\n    <div style="font-weight:700;font-size:14px;color:var(--text)">&#9881; Quota plan Gratuit</div>\n    <div style="font-size:12px;color:var(--text-muted);margin-top:2px">\n      Mode actuel : <strong>{{ \'Quotidien (24h)\' if plan_gratuit_periode == \'daily\' else \'Mensuel\' }}</strong>\n    </div>\n  </div>\n  <form action="/admin/config/toggle-plan-periode" method="POST">\n    <button type="submit" style="background:{{ \'#10b981\' if plan_gratuit_periode == \'daily\' else \'#6b7280\' }};color:white;border:none;padding:8px 16px;border-radius:8px;font-weight:600;font-size:13px;cursor:pointer;">\n      {{ \'Daily actif - Passer en Mensuel\' if plan_gratuit_periode == \'daily\' else \'Activer le Daily (24h)\' }}\n    </button>\n  </form>\n</div>\n\n<div style="background:#0F172A;border:1px solid rgba(0,191,179,.3);border-radius:var(--radius);padding:16px 20px;margin-bottom:20px">\n  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">\n    <div style="font-weight:700;font-size:14px;color:#fff">Levée investisseur</div>\n    <div style="font-size:11px;color:{{ \'#5EEAD4\' if investisseur_cfg.actif == \'1\' else \'#94A3B8\' }}">{{ \'Bandeau actif sur le site\' if investisseur_cfg.actif == \'1\' else \'Bandeau masqué\' }}</div>\n  </div>\n  <form action="/admin/config/investisseur" method="POST" style="display:flex;flex-wrap:wrap;gap:12px;align-items:end">\n    <div>\n      <label style="display:block;font-size:11px;color:#94A3B8;margin-bottom:4px">Places restantes (/10)</label>\n      <input type="number" name="places_dispo" min="0" max="10" value="{{ investisseur_cfg.places_dispo }}" style="width:80px;padding:6px 8px;border-radius:6px;border:1px solid #334155;background:#1E293B;color:#fff">\n    </div>\n    <div>\n      <label style="display:block;font-size:11px;color:#94A3B8;margin-bottom:4px">% disponible</label>\n      <input type="number" name="pct_dispo" min="0" max="49" value="{{ investisseur_cfg.pct_dispo }}" style="width:80px;padding:6px 8px;border-radius:6px;border:1px solid #334155;background:#1E293B;color:#fff">\n    </div>\n    <div>\n      <label style="display:block;font-size:11px;color:#94A3B8;margin-bottom:4px">Clôture (AAAA-MM-JJ)</label>\n      <input type="date" name="cloture" value="{{ investisseur_cfg.cloture }}" style="padding:6px 8px;border-radius:6px;border:1px solid #334155;background:#1E293B;color:#fff">\n    </div>\n    <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:#fff;padding-bottom:8px">\n      <input type="checkbox" name="actif" {{ \'checked\' if investisseur_cfg.actif == \'1\' else \'\' }}> Afficher le bandeau\n    </label>\n    <button type="submit" style="background:#00BFB3;color:#0F172A;border:none;padding:8px 16px;border-radius:8px;font-weight:700;font-size:13px;cursor:pointer">Mettre à jour</button>\n  </form>\n</div>',
    "ajoute une carte admin pour piloter la levee investisseur (places restantes, % dispo, date de cloture, afficher/masquer le bandeau)",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/index.html -- bandeau investisseur (compte a rebours + places restantes)
# ─────────────────────────────────────────────────────────────
print("=== templates/pages/index.html (bandeau investisseur) ===")
path = 'templates/pages/index.html'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '</section>\n\n<div class="stats-banner">',
    '</section>\n\n{% if investisseur.actif == \'1\' %}\n<div style="max-width:1100px;margin:24px auto 0;padding:0 16px">\n  <div style="background:#0F172A;border-radius:16px;padding:24px 28px;position:relative;overflow:hidden">\n    <div style="position:absolute;top:-60px;right:-60px;width:200px;height:200px;border-radius:50%;background:rgba(0,191,179,.15)"></div>\n    <div style="position:relative;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:20px">\n      <div style="flex:1;min-width:240px">\n        <div style="display:inline-flex;align-items:center;gap:6px;background:rgba(0,191,179,.2);border:1px solid rgba(0,191,179,.4);color:#5EEAD4;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;margin-bottom:10px">\n          <span style="width:6px;height:6px;border-radius:50%;background:#22C55E;display:inline-block"></span> Levée de fonds en cours\n        </div>\n        <div style="font-size:19px;font-weight:800;color:#fff;margin-bottom:4px">helloBiz ouvre son capital aux investisseurs</div>\n        <div style="font-size:13px;color:#94A3B8">Dossier et conditions disponibles sur demande — candidature étudiée individuellement.</div>\n      </div>\n      <div style="display:flex;gap:22px;align-items:center;flex-wrap:wrap">\n        <div style="text-align:center">\n          <div id="inv-countdown-val" data-cloture="{{ investisseur.cloture }}" style="font-size:26px;font-weight:900;color:#00BFB3">--</div>\n          <div style="font-size:10.5px;color:#94A3B8;text-transform:uppercase;letter-spacing:.05em">jours restants</div>\n        </div>\n        <div style="text-align:center">\n          <div style="font-size:26px;font-weight:900;color:#fff">{{ investisseur.pct_dispo }}%</div>\n          <div style="font-size:10.5px;color:#94A3B8;text-transform:uppercase;letter-spacing:.05em">parts dispo</div>\n        </div>\n        <div style="text-align:center">\n          <div style="font-size:26px;font-weight:900;color:#fff">{{ investisseur.places_dispo }}/10</div>\n          <div style="font-size:10.5px;color:#94A3B8;text-transform:uppercase;letter-spacing:.05em">places restantes</div>\n        </div>\n        <a href="https://wa.me/242057731857?text={{ \'Bonjour, je suis intéressé(e) par une participation au capital helloBiz.\' | urlencode }}"\n           target="_blank" rel="noopener"\n           onclick="if(typeof gtag===\'function\'){gtag(\'event\',\'cta_investisseur_click\',{\'page\':\'accueil\'});}"\n           style="background:#00BFB3;color:#0F172A;padding:12px 22px;border-radius:10px;font-size:13.5px;font-weight:800;white-space:nowrap;text-decoration:none">\n          Devenir actionnaire\n        </a>\n      </div>\n    </div>\n  </div>\n</div>\n<script>\n(function(){\n  var el = document.getElementById(\'inv-countdown-val\');\n  if(!el) return;\n  var cloture = el.getAttribute(\'data-cloture\');\n  if(!cloture) return;\n  var end = new Date(cloture + \'T23:59:59\');\n  var now = new Date();\n  var days = Math.ceil((end - now) / 86400000);\n  el.textContent = days > 0 ? days : 0;\n})();\n</script>\n{% endif %}\n\n<div class="stats-banner">',
    "ajoute le bandeau investisseur juste apres le hero (fenetre 60 jours a partir du 2026-07-27, cloture 2026-09-25, CTA WhatsApp pre-rempli, compte a rebours JS cote client)",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# app.py -- ajoute la route /investisseurs (page dediee, remplace le lien WhatsApp direct)
# ─────────────────────────────────────────────────────────────
print("=== app.py (route /investisseurs) ===")
path = 'app.py'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    "@app.route('/cgu')\ndef cgu():\n    villes, categories, quartiers = get_base_data()\n    return render_template('pages/cgu.html', villes=villes, categories=categories)",
    '@app.route(\'/cgu\')\ndef cgu():\n    villes, categories, quartiers = get_base_data()\n    return render_template(\'pages/cgu.html\', villes=villes, categories=categories)\n\n\n@app.route(\'/investisseurs\')\ndef investisseurs():\n    villes, categories, quartiers = get_base_data()\n    db = get_db()\n    _inv_rows = db.execute("SELECT cle, valeur FROM site_config WHERE cle LIKE \'investisseur_%\'").fetchall()\n    investisseur = {r[\'cle\'].replace(\'investisseur_\', \'\'): r[\'valeur\'] for r in _inv_rows}\n    investisseur.setdefault(\'actif\', \'0\')\n    investisseur.setdefault(\'cloture\', \'\')\n    investisseur.setdefault(\'places_dispo\', \'0\')\n    investisseur.setdefault(\'pct_dispo\', \'0\')\n    db.close()\n    return render_template(\'pages/investisseurs.html\', villes=villes, categories=categories, investisseur=investisseur)',
    "ajoute la route /investisseurs (infos completes, conditions, processus, FAQ) juste apres /cgu",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/index.html -- le bouton Devenir actionnaire pointe vers /investisseurs au lieu de WhatsApp direct
# ─────────────────────────────────────────────────────────────
print("=== templates/pages/index.html (lien Devenir actionnaire) ===")
path = 'templates/pages/index.html'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '        <a href="https://wa.me/242057731857?text={{ \'Bonjour, je suis intéressé(e) par une participation au capital helloBiz.\' | urlencode }}"\n           target="_blank" rel="noopener"\n           onclick="if(typeof gtag===\'function\'){gtag(\'event\',\'cta_investisseur_click\',{\'page\':\'accueil\'});}"\n           style="background:#00BFB3;color:#0F172A;padding:12px 22px;border-radius:10px;font-size:13.5px;font-weight:800;white-space:nowrap;text-decoration:none">\n          Devenir actionnaire\n        </a>',
    '        <a href="{{ url_for(\'investisseurs\') }}"\n           onclick="if(typeof gtag===\'function\'){gtag(\'event\',\'cta_investisseur_click\',{\'page\':\'accueil\'});}"\n           style="background:#00BFB3;color:#0F172A;padding:12px 22px;border-radius:10px;font-size:13.5px;font-weight:800;white-space:nowrap;text-decoration:none">\n          Devenir actionnaire\n        </a>',
    "le bouton Devenir actionnaire renvoie maintenant vers la page /investisseurs (infos + FAQ + processus) plutot que d'ouvrir WhatsApp directement -- WhatsApp reste le CTA final en bas de cette page, apres lecture",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/investisseurs.html -- NOUVEAU fichier : page complete (conditions, processus, FAQ)
# ─────────────────────────────────────────────────────────────
print("=== templates/pages/investisseurs.html (nouveau fichier) ===")
path = 'templates/pages/investisseurs.html'
try:
    _existing = get_file(path)
except Exception:
    _existing = None
if _existing and 'INVESTISSEURS_PAGE_V1' in _existing:
    print("  -> deja cree, aucun changement")
else:
    put_file(path, '<!-- INVESTISSEURS_PAGE_V1 -->\n{% extends "base.html" %}\n{% block title %}Devenir actionnaire · helloBiz{% endblock %}\n{% block description %}helloBiz ouvre son capital à des investisseurs pré-seed. Conditions, processus et FAQ pour devenir actionnaire.{% endblock %}\n{% block content %}\n\n<div style="background:#0F172A">\n  <div style="max-width:900px;margin:0 auto;padding:56px 20px 48px;position:relative;overflow:hidden">\n    <div style="position:absolute;top:-80px;right:-80px;width:280px;height:280px;border-radius:50%;background:rgba(0,191,179,.12)"></div>\n    <div style="position:relative">\n      <div style="display:inline-flex;align-items:center;gap:6px;background:rgba(0,191,179,.2);border:1px solid rgba(0,191,179,.4);color:#5EEAD4;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;margin-bottom:16px">\n        <span style="width:6px;height:6px;border-radius:50%;background:#22C55E;display:inline-block"></span> Levée de fonds en cours\n      </div>\n      <h1 style="font-size:32px;font-weight:900;color:#fff;margin-bottom:12px;line-height:1.2">Devenir actionnaire de helloBiz</h1>\n      <p style="font-size:15.5px;color:#94A3B8;max-width:560px;margin-bottom:28px">helloBiz Congo ouvre jusqu\'à 49% de son capital à des investisseurs, sur un tour pré-seed limité dans le temps. Le fondateur reste toujours majoritaire.</p>\n      <div style="display:flex;gap:28px;flex-wrap:wrap">\n        <div>\n          <div id="inv-countdown-val-page" data-cloture="{{ investisseur.cloture }}" style="font-size:28px;font-weight:900;color:#00BFB3">--</div>\n          <div style="font-size:10.5px;color:#94A3B8;text-transform:uppercase;letter-spacing:.05em">jours restants</div>\n        </div>\n        <div>\n          <div style="font-size:28px;font-weight:900;color:#fff">{{ investisseur.pct_dispo }}%</div>\n          <div style="font-size:10.5px;color:#94A3B8;text-transform:uppercase;letter-spacing:.05em">parts disponibles</div>\n        </div>\n        <div>\n          <div style="font-size:28px;font-weight:900;color:#fff">{{ investisseur.places_dispo }}/10</div>\n          <div style="font-size:10.5px;color:#94A3B8;text-transform:uppercase;letter-spacing:.05em">places restantes</div>\n        </div>\n      </div>\n    </div>\n  </div>\n</div>\n\n<div style="max-width:900px;margin:0 auto;padding:44px 20px">\n\n  <!-- CONDITIONS -->\n  <div style="margin-bottom:44px">\n    <div style="font-size:11px;font-weight:700;color:#00BFB3;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px">Conditions de la levée</div>\n    <h2 style="font-size:22px;font-weight:800;color:var(--text);margin-bottom:20px">Des chiffres simples et fixes</h2>\n    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px">\n      <div style="background:#0F172A;border-radius:12px;padding:18px">\n        <div style="font-size:20px;font-weight:900;color:#00BFB3">85 M FCFA</div>\n        <div style="font-size:12px;color:#94A3B8;margin-top:2px">Valorisation pré-money</div>\n      </div>\n      <div style="background:#0F172A;border-radius:12px;padding:18px">\n        <div style="font-size:20px;font-weight:900;color:#fff">1,67 M FCFA</div>\n        <div style="font-size:12px;color:#94A3B8;margin-top:2px">Prix fixe par 1% du capital</div>\n      </div>\n      <div style="background:#0F172A;border-radius:12px;padding:18px">\n        <div style="font-size:20px;font-weight:900;color:#fff">500 000 FCFA</div>\n        <div style="font-size:12px;color:#94A3B8;margin-top:2px">Ticket minimum (≈0,3%)</div>\n      </div>\n      <div style="background:#0F172A;border-radius:12px;padding:18px">\n        <div style="font-size:20px;font-weight:900;color:#fff">49% / 51%</div>\n        <div style="font-size:12px;color:#94A3B8;margin-top:2px">Cession max. / plancher fondateur</div>\n      </div>\n      <div style="background:#0F172A;border-radius:12px;padding:18px">\n        <div style="font-size:20px;font-weight:900;color:#fff">10 max</div>\n        <div style="font-size:12px;color:#94A3B8;margin-top:2px">Nombre de souscripteurs</div>\n      </div>\n      <div style="background:#0F172A;border-radius:12px;padding:18px">\n        <div style="font-size:20px;font-weight:900;color:#fff">4 à 6 ans</div>\n        <div style="font-size:12px;color:#94A3B8;margin-top:2px">Horizon de sortie visé</div>\n      </div>\n    </div>\n  </div>\n\n  <!-- PROCESSUS -->\n  <div style="margin-bottom:44px">\n    <div style="font-size:11px;font-weight:700;color:#00BFB3;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px">Comment ça se passe</div>\n    <h2 style="font-size:22px;font-weight:800;color:var(--text);margin-bottom:8px">Une sélection dans les deux sens</h2>\n    <p style="font-size:14px;color:var(--text-muted);margin-bottom:24px">Chaque candidature est étudiée individuellement — et l\'échange sert aussi à vérifier que le profil de helloBiz vous convient à vous. Ce n\'est pas une réservation automatique.</p>\n    <div>\n      {% set steps = [\n        ("1", "Premier contact", "Vous manifestez votre intérêt via WhatsApp. On échange en quelques messages sur votre profil et vos attentes."),\n        ("2", "Appel de découverte", "Un échange plus complet (30 min environ) : présentation de helloBiz, questions-réponses, et vérification mutuelle que ça vous convient."),\n        ("3", "Dossier complet", "Si l\'intérêt est confirmé des deux côtés, vous recevez le dossier investisseur complet (traction, projections, valorisation détaillée)."),\n        ("4", "Signature", "Signature du bulletin de souscription et du pacte d\'actionnaires, qui fixent votre participation et vos droits."),\n        ("5", "Virement", "Virement du montant souscrit sur le compte BSCA BANK de helloBiz, sous 15 jours après la clôture de la fenêtre."),\n        ("6", "Confirmation", "Votre participation est actée, le compteur de places est mis à jour, et vous recevez votre premier rapport mensuel."),\n      ] %}\n      {% for num, titre, desc in steps %}\n      <div style="display:flex;gap:16px;margin-bottom:18px">\n        <div style="width:32px;height:32px;border-radius:50%;background:#0F172A;color:#00BFB3;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;flex-shrink:0">{{ num }}</div>\n        <div>\n          <div style="font-weight:700;font-size:14.5px;color:var(--text);margin-bottom:2px">{{ titre }}</div>\n          <div style="font-size:13.5px;color:var(--text-muted);line-height:1.5">{{ desc }}</div>\n        </div>\n      </div>\n      {% endfor %}\n    </div>\n  </div>\n\n  <!-- FAQ -->\n  <div style="margin-bottom:44px">\n    <div style="font-size:11px;font-weight:700;color:#00BFB3;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px">Questions fréquentes</div>\n    <h2 style="font-size:22px;font-weight:800;color:var(--text);margin-bottom:20px">Tout ce qu\'il faut savoir</h2>\n    {% set faqs = [\n      ("Qui reste aux commandes de helloBiz ?", "Le fondateur, Dony TCHICAYA, conserve toujours au minimum 51% du capital et la direction opérationnelle complète. Les investisseurs n\'ont pas de droit de veto sur la gestion courante."),\n      ("Ai-je un droit de regard sur les décisions importantes ?", "Les décisions majeures (cession de plus de 25% des actifs, changement d\'objet social, dissolution) requièrent l\'accord des investisseurs représentant au moins 30% du capital investi. La gestion quotidienne reste au fondateur."),\n      ("Quels documents dois-je signer ?", "Un bulletin de souscription (montant et participation) et un pacte d\'actionnaires (droits, gouvernance, verrou de majorité à 51%, clauses de sortie)."),\n      ("Puis-je revendre mes parts plus tard ?", "Oui, avec un droit de préemption pour les autres actionnaires et le fondateur, et une clause de sortie conjointe (tag-along) si le fondateur cède des actions."),\n      ("Quels sont mes droits pendant la durée de l\'investissement ?", "Un rapport mensuel complet (chiffre d\'affaires, métriques, roadmap) et une priorité pro-rata pour participer à un futur tour de financement."),\n      ("Que se passe-t-il si le plafond de 49% n\'est pas atteint ?", "Le solde non souscrit reste acquis au fondateur. Rien n\'est forcé : le tour se clôture dès que l\'un des trois seuils est atteint (49% cédé, 10 souscripteurs, ou fin de la fenêtre de 60 jours)."),\n      ("Comment se fait le paiement ?", "Par virement bancaire vers le compte BSCA BANK de helloBiz, dans les 15 jours suivant la clôture de la fenêtre de souscription."),\n      ("Quel est le principal risque ?", "Comme pour toute prise de participation dans une société en démarrage, il existe un risque de perte totale du capital investi. Ce n\'est pas un placement garanti."),\n    ] %}\n    {% for q, a in faqs %}\n    <details style="background:#0F172A;border-radius:10px;padding:14px 18px;margin-bottom:10px">\n      <summary style="cursor:pointer;font-weight:700;font-size:14px;color:#fff;list-style:none">{{ q }}</summary>\n      <div style="font-size:13.5px;color:#94A3B8;margin-top:10px;line-height:1.55">{{ a }}</div>\n    </details>\n    {% endfor %}\n  </div>\n\n  <!-- CTA FINAL -->\n  <div style="background:linear-gradient(135deg,#0F172A,#0D2E2C);border-radius:16px;padding:36px 28px;text-align:center">\n    <div style="font-size:20px;font-weight:800;color:#fff;margin-bottom:8px">Prêt à échanger ?</div>\n    <p style="font-size:13.5px;color:#94A3B8;max-width:480px;margin:0 auto 22px">Écrivez-nous sur WhatsApp pour un premier échange. Aucun engagement à ce stade — c\'est le début d\'une conversation, dans les deux sens.</p>\n    <a href="https://wa.me/242057731857?text={{ "Bonjour, je suis intéressé(e) par une participation au capital helloBiz. J\'ai lu la page investisseurs et j\'aimerais échanger." | urlencode }}"\n       target="_blank" rel="noopener"\n       onclick="if(typeof gtag===\'function\'){gtag(\'event\',\'cta_investisseur_page_click\',{\'page\':\'investisseurs\'});}"\n       style="display:inline-block;background:#00BFB3;color:#0F172A;padding:13px 28px;border-radius:10px;font-size:14px;font-weight:800;text-decoration:none">\n      Écrire sur WhatsApp\n    </a>\n    <div style="font-size:11px;color:#64748B;margin-top:16px">Document confidentiel · helloBiz Congo · hellobizcongo.com</div>\n  </div>\n\n</div>\n\n<script>\n(function(){\n  var el = document.getElementById(\'inv-countdown-val-page\');\n  if(!el) return;\n  var cloture = el.getAttribute(\'data-cloture\');\n  if(!cloture) return;\n  var end = new Date(cloture + \'T23:59:59\');\n  var now = new Date();\n  var days = Math.ceil((end - now) / 86400000);\n  el.textContent = days > 0 ? days : 0;\n})();\n</script>\n\n{% endblock %}\n')
    print("  -> nouveau fichier cree sur le serveur")

# ─────────────────────────────────────────────────────────────
# app.py -- recherche + filtre "non verifiees" sur la table boutiques admin
# ─────────────────────────────────────────────────────────────
print("=== app.py (recherche boutiques admin) ===")
path = 'app.py'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    "    boutiques_all = db.execute('''\n        SELECT b.*, v.nom as vendeur_nom, v.email as vendeur_email,\n               COUNT(av.id) as nb_avis,\n               ROUND(COALESCE(AVG(av.note), 0), 1) as note_moy\n        FROM boutiques b\n        JOIN vendeurs v ON b.vendeur_id=v.id\n        LEFT JOIN avis av ON av.boutique_id=b.id\n        GROUP BY b.id\n        ORDER BY\n            CASE WHEN COUNT(av.id) >= 5 AND AVG(av.note) < 2.5 THEN 0\n                 WHEN COUNT(av.id) >= 3 AND AVG(av.note) < 3.0 THEN 1\n                 ELSE 2 END,\n            b.created_at DESC\n        LIMIT 50\n    ''').fetchall()",
    "    q_boutique = request.args.get('q_boutique', '').strip()\n    filtre_boutique = request.args.get('filtre_boutique', '')\n    _b_conditions = []\n    _b_params = []\n    if filtre_boutique == 'non_verifiees':\n        _b_conditions.append('b.actif=1 AND b.badge_verifie=0')\n    if q_boutique:\n        _b_conditions.append('(b.nom LIKE ? OR v.nom LIKE ? OR v.email LIKE ?)')\n        _b_params += [f'%{q_boutique}%', f'%{q_boutique}%', f'%{q_boutique}%']\n    _b_where = ('WHERE ' + ' AND '.join(_b_conditions)) if _b_conditions else ''\n    _b_limit = 'LIMIT 300' if _b_conditions else 'LIMIT 50'\n    boutiques_all = db.execute(f'''\n        SELECT b.*, v.nom as vendeur_nom, v.email as vendeur_email,\n               COUNT(av.id) as nb_avis,\n               ROUND(COALESCE(AVG(av.note), 0), 1) as note_moy\n        FROM boutiques b\n        JOIN vendeurs v ON b.vendeur_id=v.id\n        LEFT JOIN avis av ON av.boutique_id=b.id\n        {_b_where}\n        GROUP BY b.id\n        ORDER BY\n            CASE WHEN COUNT(av.id) >= 5 AND AVG(av.note) < 2.5 THEN 0\n                 WHEN COUNT(av.id) >= 3 AND AVG(av.note) < 3.0 THEN 1\n                 ELSE 2 END,\n            b.created_at DESC\n        {_b_limit}\n    ''', _b_params).fetchall()",
    "ajoute la recherche (nom/vendeur/email) et le filtre non_verifiees sur la liste des boutiques admin, avec limite relevee a 300 quand un filtre est actif",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    "    return render_template('pages/admin.html', stats=stats, vendeurs=vendeurs, plan_gratuit_periode=plan_gratuit_periode,\n        boutiques=boutiques_all, annonces=annonces_all, paiements=paiements_all,\n        offres_emploi=offres_emploi, villes=villes, categories=categories,\n            boutiques_en_attente=boutiques_en_attente, ambassadeurs=ambassadeurs, investisseur_cfg=investisseur_cfg)",
    "    return render_template('pages/admin.html', stats=stats, vendeurs=vendeurs, plan_gratuit_periode=plan_gratuit_periode,\n        boutiques=boutiques_all, annonces=annonces_all, paiements=paiements_all,\n        offres_emploi=offres_emploi, villes=villes, categories=categories,\n            boutiques_en_attente=boutiques_en_attente, ambassadeurs=ambassadeurs, investisseur_cfg=investisseur_cfg,\n            q_boutique=q_boutique, filtre_boutique=filtre_boutique)",
    "transmet q_boutique et filtre_boutique au template admin pour prefill du formulaire",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# templates/pages/admin.html -- barre de recherche boutiques + lien filtre non verifiees
# ─────────────────────────────────────────────────────────────
print("=== templates/pages/admin.html (recherche boutiques) ===")
path = 'templates/pages/admin.html'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    '  {% if stats.boutiques_non_verifiees > 0 %}\n  <a href="#" onclick="showTab(\'boutiques\');return false;" style="display:flex;align-items:center;gap:8px;background:#fef9c3;border:1px solid #eab308;color:#713f12;padding:10px 16px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none">\n    🟡 {{ stats.boutiques_non_verifiees }} boutique(s) active(s) non verifiee(s)\n  </a>\n  {% endif %}',
    '  {% if stats.boutiques_non_verifiees > 0 %}\n  <a href="/admin?filtre_boutique=non_verifiees#boutiques" style="display:flex;align-items:center;gap:8px;background:#fef9c3;border:1px solid #eab308;color:#713f12;padding:10px 16px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none">\n    🟡 {{ stats.boutiques_non_verifiees }} boutique(s) active(s) non verifiee(s)\n  </a>\n  {% endif %}',
    "le compteur de boutiques non verifiees devient un lien filtrant reellement la liste (au lieu de juste changer d'onglet)",
)
changed = changed or ch

c, ch = apply_patch(
    c,
    '  <div id="panel-boutiques" style="display:none;margin-bottom:32px">\n    <div style="background:white;border:1px solid var(--border);border-radius:var(--radius);overflow-x:auto;box-shadow:var(--shadow)">',
    '  <div id="panel-boutiques" style="display:none;margin-bottom:32px">\n    <form method="GET" action="/admin#boutiques" style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap">\n      <input type="text" name="q_boutique" value="{{ q_boutique or \'\' }}" placeholder="Rechercher une boutique, un vendeur, un email..." style="flex:1;min-width:220px;padding:9px 12px;border:1px solid var(--border);border-radius:8px;font-size:13px">\n      <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-muted)">\n        <input type="checkbox" name="filtre_boutique" value="non_verifiees" {{ \'checked\' if filtre_boutique == \'non_verifiees\' else \'\' }}> Non vérifiées uniquement\n      </label>\n      <button type="submit" style="background:var(--primary);color:white;border:none;padding:9px 16px;border-radius:8px;font-weight:600;font-size:13px;cursor:pointer">Rechercher</button>\n      {% if q_boutique or filtre_boutique %}<a href="/admin#boutiques" style="font-size:12px;color:var(--text-muted)">Réinitialiser</a>{% endif %}\n    </form>\n    <div style="background:white;border:1px solid var(--border);border-radius:var(--radius);overflow-x:auto;box-shadow:var(--shadow)">',
    "ajoute une barre de recherche (nom/vendeur/email) + case a cocher non verifiees au-dessus de la table boutiques",
)
changed = changed or ch

if changed:
    put_file(path, c)
    print("  -> fichier mis a jour sur le serveur")
else:
    print("  -> aucun changement necessaire")

# ─────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────
# app.py -- diagnostic TEMPORAIRE : capture la traceback reelle de l'erreur 500 sur /mot-de-passe-oublie
# ─────────────────────────────────────────────────────────────
print("=== app.py (diagnostic temporaire mot-de-passe-oublie) ===")
path = 'app.py'
c = get_file(path)
changed = False

c, ch = apply_patch(
    c,
    "@app.route('/mot-de-passe-oublie', methods=['GET', 'POST'])\ndef mot_de_passe_oublie():\n    villes, categories, quartiers = get_base_data()\n    if request.method == 'POST':",
    "@app.route('/mot-de-passe-oublie', methods=['GET', 'POST'])\ndef mot_de_passe_oublie():\n    import traceback as _tb_diag\n    try:\n        return _mot_de_passe_oublie_impl()\n    except Exception as _e_diag:\n        return '<pre>DIAG500 ' + _tb_diag.format_exc() + '</pre>', 500\n\ndef _mot_de_passe_oublie_impl():\n    villes, categories, quartiers = get_base_data()\n    if request.method == 'POST':",
    "enrobe temporairement la vue mot_de_passe_oublie pour afficher la traceback exacte en cas d'erreur 500 (diagnostic, a retirer ensuite)",
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
for _fname, _out in [("app.py", "live_snapshot_app.py"), ("database.py", "live_snapshot_database.py"), ("templates/pages/annonce.html", "live_snapshot_annonce.html"), ("templates/pages/boutique.html", "live_snapshot_boutique.html"), ("templates/pages/creer_boutique.html", "live_snapshot_creer_boutique.html"), ("templates/pages/deposer_annonce.html", "live_snapshot_deposer_annonce.html"), ("templates/pages/admin.html", "live_snapshot_admin.html"), ("templates/pages/cgu.html", "live_snapshot_cgu.html"), ("templates/pages/dashboard.html", "live_snapshot_dashboard.html"), ("templates/pages/tarifs.html", "live_snapshot_tarifs.html"), ("templates/pages/modifier_boutique.html", "live_snapshot_modifier_boutique.html"), ("templates/pages/boutiques.html", "live_snapshot_boutiques_liste.html"), ("static/css/style.css", "live_snapshot_style.css"), ("templates/base.html", "live_snapshot_base.html"), ("templates/pages/recherche.html", "live_snapshot_recherche.html"), ("templates/pages/index.html", "live_snapshot_index.html")]:
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
