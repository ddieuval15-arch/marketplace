"""
Module Devis & Factures — helloBiz Business Plan
Injecté dans app.py via : from devis_routes import register_devis_routes
                           register_devis_routes(app, get_db, login_required, save_image, UPLOAD_FOLDER)
"""
import os
import re
import uuid
import datetime
from flask import (render_template, request, redirect, url_for,
                   flash, session, send_file, abort, jsonify)


# ── Helpers ──────────────────────────────────────────────────────────

def _gen_numero(db, boutique_id, type_doc):
    """Génère le prochain numéro séquentiel du mois : DEV-XXX-001 / FACT-XXX-001"""
    boutique = db.execute('SELECT nom FROM boutiques WHERE id=?', (boutique_id,)).fetchone()
    initiales = ''.join(w[0].upper() for w in boutique['nom'].split()[:3]) if boutique else 'BIZ'
    prefix = 'DEV' if type_doc == 'devis' else 'FACT'
    mois = datetime.date.today().strftime('%m%Y')
    # Compte les docs du mois courant
    like = f'{prefix}-{initiales}-%'
    rows = db.execute(
        "SELECT numero FROM devis WHERE boutique_id=? AND type=? AND numero LIKE ? AND strftime('%m%Y', date_creation)=?",
        (boutique_id, type_doc, like, mois)
    ).fetchall()
    seq = len(rows) + 1
    return f"{prefix}-{initiales}-{seq:03d}"


def _get_profil(db, boutique_id):
    profil = db.execute('SELECT * FROM devis_profil WHERE boutique_id=?', (boutique_id,)).fetchone()
    if not profil:
        # Pré-remplir depuis la boutique
        b = db.execute('SELECT * FROM boutiques WHERE id=?', (boutique_id,)).fetchone()
        return {
            'boutique_id': boutique_id,
            'nom': b['nom'] if b else '',
            'rccm': '',
            'adresse': b['adresse'] if b else '',
            'telephone': b['telephone'] if b else '',
            'email': b['email'] if b else '',
            'banque': '',
            'conditions': 'Paiement par Mobile Money (MTN MoMo / Airtel Money) ou espèces.',
            'logo_path': b['logo'] if b else None,
        }
    return dict(profil)


def _calcul_total(lignes):
    return sum(float(l.get('quantite', 1)) * float(l.get('prix_unitaire', 0)) for l in lignes)


def _montant_en_lettres(n):
    """Convertit un entier en lettres françaises (FCFA)."""
    n = int(round(n))
    if n == 0:
        return 'zéro franc CFA'
    units = ['','un','deux','trois','quatre','cinq','six','sept','huit','neuf',
             'dix','onze','douze','treize','quatorze','quinze','seize',
             'dix-sept','dix-huit','dix-neuf']
    tens  = ['','','vingt','trente','quarante','cinquante','soixante','soixante',
             'quatre-vingt','quatre-vingt']

    def _inf1000(n):
        if n == 0: return ''
        if n < 20: return units[n]
        if n < 100:
            d, u = divmod(n, 10)
            if d == 7: return 'soixante-' + units[10 + u]
            if d == 9: return 'quatre-vingt-' + (units[u] if u else 'dix' if False else units[10+u] if u else 'ts'[:-1]+'s')
            if d == 9:
                return 'quatre-vingt-' + (units[u] if u else '')
            if u == 0: return tens[d] + ('s' if d == 8 else '')
            if u == 1 and d != 8: return tens[d] + '-et-un'
            return tens[d] + '-' + units[u]
        h, r = divmod(n, 100)
        pref = ('cent' if h == 1 else units[h] + ' cent')
        if r == 0: return pref + ('s' if h > 1 else '')
        return pref + ' ' + _inf1000(r)

    def _inf1000_fixed(n):
        if n == 0: return ''
        if n < 20: return units[n]
        if n < 100:
            d, u = divmod(n, 10)
            if d == 7: return 'soixante-' + units[10 + u]
            if d == 9: return 'quatre-vingt-' + (units[u] if u else '')
            if u == 0: return tens[d] + ('s' if d == 8 else '')
            if u == 1 and d != 8: return tens[d] + '-et-un'
            return tens[d] + '-' + units[u]
        h, r = divmod(n, 100)
        pref = 'cent' if h == 1 else units[h] + ' cent'
        if r == 0: return pref + ('s' if h > 1 else '')
        return pref + ' ' + _inf1000_fixed(r)

    parts = []
    mil = n // 1_000_000
    n  %= 1_000_000
    if mil:
        parts.append(('un million' if mil == 1 else _inf1000_fixed(mil) + ' millions'))
    mille = n // 1000
    n    %= 1000
    if mille:
        parts.append('mille' if mille == 1 else _inf1000_fixed(mille) + ' mille')
    if n:
        parts.append(_inf1000_fixed(n))
    result = ' '.join(parts).strip()
    return result + (' franc CFA' if result.endswith('un') else ' francs CFA')


def _business_required(db, boutique_id):
    """Vérifie que la boutique a un plan Business."""
    b = db.execute('SELECT plan FROM boutiques WHERE id=?', (boutique_id,)).fetchone()
    return b and b['plan'] == 'business'


# ── Enregistrement des routes ────────────────────────────────────────

def register_devis_routes(app, get_db, login_required, save_image, UPLOAD_FOLDER):

    # ── Dashboard ────────────────────────────────────────────────────
    @app.route('/devis')
    @login_required
    def devis_dashboard():
        db = get_db()
        vendeur_id = session['vendeur_id']
        boutique = db.execute(
            'SELECT * FROM boutiques WHERE vendeur_id=? ORDER BY id LIMIT 1',
            (vendeur_id,)
        ).fetchone()
        if not boutique:
            flash('Vous devez d\'abord créer une boutique.', 'error')
            return redirect(url_for('creer_boutique'))
        if not _business_required(db, boutique['id']):
            flash('Le module Devis & Factures est réservé au plan Business.', 'error')
            return redirect(url_for('dashboard'))

        docs = db.execute(
            '''SELECT d.*, COUNT(l.id) as nb_lignes
               FROM devis d
               LEFT JOIN devis_lignes l ON l.devis_id = d.id
               WHERE d.boutique_id=?
               GROUP BY d.id
               ORDER BY d.date_creation DESC''',
            (boutique['id'],)
        ).fetchall()

        stats = {
            'total_devis':    sum(1 for d in docs if d['type'] == 'devis'),
            'acceptes':       sum(1 for d in docs if d['statut'] == 'accepte'),
            'en_attente':     sum(1 for d in docs if d['statut'] == 'envoye'),
            'ca_genere':      sum(d['total'] for d in docs if d['statut'] in ('accepte', 'paye')),
        }
        profil = _get_profil(db, boutique['id'])
        db.close()
        return render_template('pages/devis/dashboard.html',
                               boutique=boutique, docs=docs, stats=stats, profil=profil)

    # ── Nouveau devis ────────────────────────────────────────────────
    @app.route('/devis/nouveau', methods=['GET', 'POST'])
    @login_required
    def devis_nouveau():
        db = get_db()
        vendeur_id = session['vendeur_id']
        boutique = db.execute(
            'SELECT * FROM boutiques WHERE vendeur_id=? ORDER BY id LIMIT 1',
            (vendeur_id,)
        ).fetchone()
        if not boutique or not _business_required(db, boutique['id']):
            db.close()
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            type_doc       = request.form.get('type_doc', 'devis')
            client_nom     = request.form.get('client_nom', '').strip()
            client_contact = request.form.get('client_contact', '').strip()
            date_validite  = request.form.get('date_validite', '')
            date_emission  = request.form.get('date_emission', '') or datetime.date.today().isoformat()
            notes          = request.form.get('notes', '').strip()
            conditions     = request.form.get('conditions', '').strip()
            remise_pct     = float(request.form.get('remise_pct', 0) or 0)

            descriptions   = request.form.getlist('desc[]')
            quantites      = request.form.getlist('qte[]')
            prix_unitaires = request.form.getlist('pu[]')

            if not client_nom:
                flash('Le nom du client est requis.', 'error')
                db.close()
                return redirect(url_for('devis_nouveau'))

            numero    = _gen_numero(db, boutique['id'], type_doc)
            sous_total = sum(float(q or 0) * float(p or 0) for q, p in zip(quantites, prix_unitaires))
            total      = sous_total * (1 - remise_pct / 100)
            montant_lettres = _montant_en_lettres(total)

            db.execute(
                '''INSERT INTO devis
                   (boutique_id, numero, type, client_nom, client_contact,
                    date_validite, date_emission, statut, notes, conditions,
                    sous_total, remise_pct, total, montant_lettres)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (boutique['id'], numero, type_doc, client_nom, client_contact,
                 date_validite or None, date_emission, 'brouillon', notes, conditions,
                 sous_total, remise_pct, total, montant_lettres)
            )
            devis_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]

            for desc, qte, pu in zip(descriptions, quantites, prix_unitaires):
                if desc.strip():
                    ligne_total = float(qte or 0) * float(pu or 0)
                    db.execute(
                        'INSERT INTO devis_lignes (devis_id, description, quantite, prix_unitaire, total) VALUES (?,?,?,?,?)',
                        (devis_id, desc.strip(), float(qte or 1), float(pu or 0), ligne_total)
                    )
            db.commit()
            db.close()
            flash(f'{numero} créé avec succès.', 'success')
            return redirect(url_for('devis_detail', devis_id=devis_id))

        profil = _get_profil(db, boutique['id'])
        today  = datetime.date.today().isoformat()
        db.close()
        return render_template('pages/devis/nouveau.html', boutique=boutique, profil=profil, today=today)

    # ── Détail / aperçu ──────────────────────────────────────────────
    @app.route('/devis/<int:devis_id>')
    @login_required
    def devis_detail(devis_id):
        db = get_db()
        vendeur_id = session['vendeur_id']
        doc = db.execute('SELECT * FROM devis WHERE id=?', (devis_id,)).fetchone()
        if not doc:
            abort(404)
        boutique = db.execute('SELECT * FROM boutiques WHERE id=? AND vendeur_id=?',
                              (doc['boutique_id'], vendeur_id)).fetchone()
        if not boutique:
            abort(403)
        lignes = db.execute('SELECT * FROM devis_lignes WHERE devis_id=? ORDER BY id',
                            (devis_id,)).fetchall()
        profil = _get_profil(db, boutique['id'])
        db.close()

        # Lien WhatsApp pré-rempli
        montant_fmt = f"{int(doc['total']):,}".replace(',', ' ') + ' FCFA'
        type_label  = 'Devis' if doc['type'] == 'devis' else 'Facture'
        wa_text = (
            f"Bonjour {doc['client_nom']},\n\n"
            f"Veuillez trouver ci-joint votre {type_label} N° {doc['numero']} "
            f"d'un montant de {montant_fmt}.\n\n"
            f"Pour toute question : {profil.get('telephone','')}"
        )
        import urllib.parse
        wa_link = 'https://wa.me/?text=' + urllib.parse.quote(wa_text)
        if doc['client_contact']:
            num = re.sub(r'[^\d+]', '', doc['client_contact'])
            if num:
                wa_link = f'https://wa.me/{num}?text=' + urllib.parse.quote(wa_text)

        return render_template('pages/devis/detail.html',
                               doc=doc, boutique=boutique, lignes=lignes,
                               profil=profil, wa_link=wa_link)

    # ── Mettre à jour le statut ──────────────────────────────────────
    @app.route('/devis/<int:devis_id>/statut', methods=['POST'])
    @login_required
    def devis_statut(devis_id):
        db = get_db()
        vendeur_id = session['vendeur_id']
        doc = db.execute('SELECT * FROM devis WHERE id=?', (devis_id,)).fetchone()
        if not doc:
            abort(404)
        boutique = db.execute('SELECT id FROM boutiques WHERE id=? AND vendeur_id=?',
                              (doc['boutique_id'], vendeur_id)).fetchone()
        if not boutique:
            abort(403)
        nouveau_statut = request.form.get('statut')
        valides = ('brouillon', 'envoye', 'accepte', 'refuse', 'paye', 'en_attente_reglement', 'regle')
        if nouveau_statut in valides:
            db.execute('UPDATE devis SET statut=? WHERE id=?', (nouveau_statut, devis_id))
            db.commit()
        db.close()
        return redirect(url_for('devis_detail', devis_id=devis_id))

    # ── Convertir devis → facture ────────────────────────────────────
    @app.route('/devis/<int:devis_id>/convertir', methods=['POST'])
    @login_required
    def devis_convertir(devis_id):
        db = get_db()
        vendeur_id = session['vendeur_id']
        doc = db.execute('SELECT * FROM devis WHERE id=?', (devis_id,)).fetchone()
        if not doc or doc['type'] != 'devis':
            abort(404)
        boutique = db.execute('SELECT * FROM boutiques WHERE id=? AND vendeur_id=?',
                              (doc['boutique_id'], vendeur_id)).fetchone()
        if not boutique:
            abort(403)

        numero_fact = _gen_numero(db, boutique['id'], 'facture')
        db.execute(
            '''INSERT INTO devis
               (boutique_id, numero, type, client_nom, client_contact,
                date_validite, statut, notes, conditions, total, devis_source_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (boutique['id'], numero_fact, 'facture', doc['client_nom'],
             doc['client_contact'], doc['date_validite'], 'envoye',
             doc['notes'], doc['conditions'], doc['total'], devis_id)
        )
        fact_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]

        # Copier les lignes
        lignes = db.execute('SELECT * FROM devis_lignes WHERE devis_id=?', (devis_id,)).fetchall()
        for l in lignes:
            db.execute(
                'INSERT INTO devis_lignes (devis_id, description, quantite, prix_unitaire, total) VALUES (?,?,?,?,?)',
                (fact_id, l['description'], l['quantite'], l['prix_unitaire'], l['total'])
            )
        # Marquer le devis source comme accepté
        db.execute("UPDATE devis SET statut='accepte' WHERE id=?", (devis_id,))
        db.commit()
        db.close()
        flash(f'Facture {numero_fact} créée.', 'success')
        return redirect(url_for('devis_detail', devis_id=fact_id))

    # ── Supprimer ────────────────────────────────────────────────────
    @app.route('/devis/<int:devis_id>/supprimer', methods=['POST'])
    @login_required
    def devis_supprimer(devis_id):
        db = get_db()
        vendeur_id = session['vendeur_id']
        doc = db.execute('SELECT * FROM devis WHERE id=?', (devis_id,)).fetchone()
        if not doc:
            abort(404)
        boutique = db.execute('SELECT id FROM boutiques WHERE id=? AND vendeur_id=?',
                              (doc['boutique_id'], vendeur_id)).fetchone()
        if not boutique:
            abort(403)
        db.execute('DELETE FROM devis_lignes WHERE devis_id=?', (devis_id,))
        db.execute('DELETE FROM devis WHERE id=?', (devis_id,))
        db.commit()
        db.close()
        flash('Document supprimé.', 'success')
        return redirect(url_for('devis_dashboard'))

    # ── Profil entreprise ────────────────────────────────────────────
    @app.route('/devis/profil', methods=['GET', 'POST'])
    @login_required
    def devis_profil():
        db = get_db()
        vendeur_id = session['vendeur_id']
        boutique = db.execute(
            'SELECT * FROM boutiques WHERE vendeur_id=? ORDER BY id LIMIT 1',
            (vendeur_id,)
        ).fetchone()
        if not boutique or not _business_required(db, boutique['id']):
            db.close()
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            logo_path = None
            if 'logo' in request.files and request.files['logo'].filename:
                f = request.files['logo']
                ext = f.filename.rsplit('.', 1)[-1].lower()
                logo_name = f'devis_logo_{boutique["id"]}_{uuid.uuid4().hex[:8]}.{ext}'
                logo_path = os.path.join(UPLOAD_FOLDER, logo_name)
                f.save(logo_path)
                logo_path = logo_name  # stocker uniquement le nom

            existing = db.execute('SELECT id, logo_path FROM devis_profil WHERE boutique_id=?',
                                  (boutique['id'],)).fetchone()
            if existing:
                if logo_path:
                    db.execute(
                        '''UPDATE devis_profil SET nom=?,rccm=?,adresse=?,telephone=?,
                           email=?,banque=?,conditions=?,logo_path=? WHERE boutique_id=?''',
                        (request.form.get('nom'), request.form.get('rccm'),
                         request.form.get('adresse'), request.form.get('telephone'),
                         request.form.get('email'), request.form.get('banque'),
                         request.form.get('conditions'), logo_path, boutique['id'])
                    )
                else:
                    db.execute(
                        '''UPDATE devis_profil SET nom=?,rccm=?,adresse=?,telephone=?,
                           email=?,banque=?,conditions=? WHERE boutique_id=?''',
                        (request.form.get('nom'), request.form.get('rccm'),
                         request.form.get('adresse'), request.form.get('telephone'),
                         request.form.get('email'), request.form.get('banque'),
                         request.form.get('conditions'), boutique['id'])
                    )
            else:
                db.execute(
                    '''INSERT INTO devis_profil
                       (boutique_id,nom,rccm,adresse,telephone,email,banque,conditions,logo_path)
                       VALUES (?,?,?,?,?,?,?,?,?)''',
                    (boutique['id'], request.form.get('nom'), request.form.get('rccm'),
                     request.form.get('adresse'), request.form.get('telephone'),
                     request.form.get('email'), request.form.get('banque'),
                     request.form.get('conditions'), logo_path)
                )
            db.commit()
            flash('Profil enregistré. Il apparaîtra sur tous vos devis et factures.', 'success')
            db.close()
            return redirect(url_for('devis_profil'))

        profil = _get_profil(db, boutique['id'])
        db.close()
        return render_template('pages/devis/profil.html', boutique=boutique, profil=profil)

    # ── API : auto-complétion lignes depuis les annonces ─────────────
    @app.route('/devis/api/annonces')
    @login_required
    def devis_api_annonces():
        db = get_db()
        vendeur_id = session['vendeur_id']
        boutique = db.execute(
            'SELECT id FROM boutiques WHERE vendeur_id=? ORDER BY id LIMIT 1',
            (vendeur_id,)
        ).fetchone()
        if not boutique:
            return jsonify([])
        annonces = db.execute(
            'SELECT titre, prix FROM annonces WHERE boutique_id=? AND statut="active" ORDER BY titre',
            (boutique['id'],)
        ).fetchall()
        db.close()
        return jsonify([{'titre': a['titre'], 'prix': a['prix']} for a in annonces])
