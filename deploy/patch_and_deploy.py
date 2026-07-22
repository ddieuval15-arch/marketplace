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

PA_USER = os.environ.get("PA_USERNAME", "donytchicaya")
PA_TOKEN = os.environ["PA_API_TOKEN"]
DOMAIN = os.environ.get("PA_DOMAIN", f"{PA_USER}.pythonanywhere.com")

API_BASE = f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}"
HEADERS = {"Authorization": f"Token {PA_TOKEN}"}
APP_ROOT = f"/home/{PA_USER}/hellobiz/marketplace"

def get_file(path):
    url = f"{API_BASE}/files/path{APP_ROOT}/{path}/"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def put_file(path, content):
    url = f"{API_BASE}/files/path{APP_ROOT}/{path}/"
    r = requests.post(url, headers=HEADERS, files={"content": content.encode("utf-8")}, timeout=30)
    r.raise_for_status()

def reload_app():
    url = f"{API_BASE}/webapps/{DOMAIN}/reload/"
    r = requests.post(url, headers=HEADERS, timeout=60)
    print(f"[RELOAD] status={r.status_code}")
    r.raise_for_status()

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
print("=== reload de l'application ===")
reload_app()
print("=== TERMINE ===")

# trigger: relance apres ajout du secret PA_API_TOKEN
