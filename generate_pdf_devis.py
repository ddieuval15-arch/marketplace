"""
Génération PDF — Devis & Factures helloBiz
Utilise ReportLab (disponible sur PythonAnywhere free tier).
"""
import os
import tempfile
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                 Table, TableStyle, HRFlowable, Image)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

# Couleurs
DARK       = HexColor('#0A0A0A')
CYAN       = HexColor('#00b7aa')
GREY_DARK  = HexColor('#374151')
GREY_MID   = HexColor('#6b7280')
GREY_LIGHT = HexColor('#f9fafb')
GREY_BORDER= HexColor('#e5e7eb')
GREEN      = HexColor('#16a34a')

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


def fmt_fcfa(val):
    try:
        v = int(float(val))
        return f"{v:,}".replace(',', ' ') + ' FCFA'
    except Exception:
        return '0 FCFA'


def generate_pdf(doc, lignes, profil, upload_folder):
    """
    Génère le PDF et retourne le chemin du fichier temporaire.
    doc      : sqlite3.Row (devis table)
    lignes   : list of sqlite3.Row (devis_lignes table)
    profil   : dict (devis_profil)
    upload_folder : str — chemin vers static/uploads/
    """
    # Convertir sqlite3.Row → dict pour pouvoir utiliser .get()
    if hasattr(doc, 'keys'):
        doc = dict(doc)
    if hasattr(profil, 'keys'):
        profil = dict(profil)
    lignes = [dict(l) if hasattr(l, 'keys') else l for l in lignes]

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', prefix='hellobiz_')
    tmp.close()
    out_path = tmp.name

    pdf = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )

    styles = getSampleStyleSheet()

    def style(name='Normal', **kw):
        return ParagraphStyle(name, parent=styles['Normal'], **kw)

    s_normal   = style('sn',  fontSize=9,  textColor=GREY_DARK,  leading=13)
    s_muted    = style('sm',  fontSize=8,  textColor=GREY_MID,   leading=12)
    s_bold     = style('sb',  fontSize=10, textColor=GREY_DARK,  fontName='Helvetica-Bold', leading=14)
    s_total    = style('st',  fontSize=12, textColor=GREEN,       fontName='Helvetica-Bold', alignment=TA_RIGHT)
    s_right    = style('sr',  fontSize=9,  textColor=GREY_DARK,  alignment=TA_RIGHT, leading=13)
    s_center   = style('sc',  fontSize=9,  textColor=GREY_DARK,  alignment=TA_CENTER, leading=13)
    s_footer   = style('sf',  fontSize=7,  textColor=GREY_MID,   leading=10)

    story = []

    # ── HEADER SOMBRE ─────────────────────────────────────────────────
    doc_type = 'FACTURE' if doc['type'] == 'facture' else 'DEVIS'
    statut_map = {
        'brouillon': ('Brouillon', '#9ca3af'),
        'envoye':    ('Envoyé',    '#d97706'),
        'accepte':   ('Accepté',   '#16a34a'),
        'refuse':    ('Refusé',    '#dc2626'),
        'paye':      ('Payé',      '#2563eb'),
    }
    statut_label, statut_hex = statut_map.get(doc['statut'], ('—', '#9ca3af'))

    # Logo
    logo_cell = ''
    logo_path = profil.get('logo_path')
    if logo_path:
        full = os.path.join(upload_folder, logo_path)
        if os.path.exists(full):
            logo_cell = Image(full, width=40*mm, height=14*mm, kind='proportional')

    emetteur_info = '\n'.join(filter(None, [
        profil.get('nom', ''),
        profil.get('rccm', '') and f"RCCM : {profil['rccm']}",
        profil.get('adresse', ''),
        profil.get('telephone', ''),
    ]))

    header_data = [[
        logo_cell or Paragraph(
            f'<font color="#00b7aa"><b>{profil.get("nom","helloBiz")}</b></font>',
            style('hn', fontSize=14, textColor=CYAN, fontName='Helvetica-Bold')
        ),
        Paragraph(
            f'<font color="#ffffff" size="16"><b>{doc_type}</b></font><br/>'
            f'<font color="#9ca3af" size="9">{doc["numero"]}</font><br/>'
            f'<font color="#9ca3af" size="9">{doc["date_creation"]}</font>',
            style('hr', fontSize=9, alignment=TA_RIGHT, textColor=white)
        )
    ]]

    header_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), DARK),
        ('VALIGN',     (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 8*mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8*mm),
        ('TOPPADDING',   (0, 0), (-1, -1), 7*mm),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 7*mm),
    ])
    header_tbl = Table(header_data, colWidths=[PAGE_W - 2*MARGIN - 50*mm, 50*mm])
    header_tbl.setStyle(header_style)
    story.append(header_tbl)
    story.append(Spacer(1, 5*mm))

    # Infos émetteur sous le header
    if emetteur_info:
        story.append(Paragraph(
            emetteur_info.replace('\n', '<br/>'),
            style('ei', fontSize=8, textColor=GREY_MID, leading=12)
        ))
        story.append(Spacer(1, 4*mm))

    # ── ÉMETTEUR / CLIENT ─────────────────────────────────────────────
    story.append(HRFlowable(width='100%', thickness=0.5, color=GREY_BORDER))
    story.append(Spacer(1, 4*mm))

    bloc_data = [[
        [
            Paragraph('<b>ÉMETTEUR</b>', style('eml', fontSize=8, textColor=GREY_MID, fontName='Helvetica-Bold')),
            Spacer(1, 2*mm),
            Paragraph(f'<b>{profil.get("nom","")}</b>', s_bold),
            Paragraph(profil.get('adresse',''), s_muted),
            Paragraph(profil.get('telephone',''), s_muted),
            Paragraph(profil.get('email',''), s_muted),
        ],
        [
            Paragraph('<b>CLIENT</b>', style('cll', fontSize=8, textColor=GREY_MID, fontName='Helvetica-Bold')),
            Spacer(1, 2*mm),
            Paragraph(f'<b>{doc["client_nom"]}</b>', s_bold),
            Paragraph(doc.get('client_contact','') or '', s_muted),
            Paragraph(f'Valable jusqu\'au {doc["date_validite"]}' if doc.get('date_validite') else '', s_muted),
        ],
    ]]

    bloc_tbl = Table(bloc_data, colWidths=[(PAGE_W - 2*MARGIN)/2]*2)
    bloc_tbl.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 4*mm),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(bloc_tbl)
    story.append(Spacer(1, 5*mm))

    # ── TABLEAU DES LIGNES ────────────────────────────────────────────
    col_w = [PAGE_W - 2*MARGIN - 22*mm - 30*mm - 30*mm,  22*mm, 30*mm, 30*mm]
    rows = [
        [
            Paragraph('<b>Description</b>', style('th', fontSize=9, textColor=white, fontName='Helvetica-Bold')),
            Paragraph('<b>Qté</b>', style('thc', fontSize=9, textColor=white, fontName='Helvetica-Bold', alignment=TA_CENTER)),
            Paragraph('<b>Prix unit.</b>', style('thr', fontSize=9, textColor=white, fontName='Helvetica-Bold', alignment=TA_RIGHT)),
            Paragraph('<b>Total</b>', style('thr2', fontSize=9, textColor=white, fontName='Helvetica-Bold', alignment=TA_RIGHT)),
        ]
    ]
    for i, l in enumerate(lignes):
        qte_val = int(l['quantite']) if float(l['quantite']) == int(l['quantite']) else l['quantite']
        rows.append([
            Paragraph(l['description'], s_normal),
            Paragraph(str(qte_val), s_center),
            Paragraph(fmt_fcfa(l['prix_unitaire']), s_right),
            Paragraph(fmt_fcfa(l['total']), s_right),
        ])

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl_style = [
        # Header
        ('BACKGROUND', (0,0), (-1,0), DARK),
        ('TEXTCOLOR',  (0,0), (-1,0), white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('TOPPADDING', (0,0), (-1,0), 6),
        ('BOTTOMPADDING',(0,0),(-1,0), 6),
        # Lignes
        ('FONTSIZE',   (0,1), (-1,-1), 9),
        ('TOPPADDING', (0,1), (-1,-1), 6),
        ('BOTTOMPADDING',(0,1),(-1,-1), 6),
        ('LINEBELOW',  (0,1), (-1,-1), 0.5, GREY_BORDER),
        # Alternance fond léger sur rangées paires
        *[('BACKGROUND', (0,i), (-1,i), GREY_LIGHT) for i in range(2, len(rows), 2)],
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING',(0,0), (-1,-1), 4),
    ]
    tbl.setStyle(TableStyle(tbl_style))
    story.append(tbl)
    story.append(Spacer(1, 4*mm))

    # ── TOTAL ─────────────────────────────────────────────────────────
    sous_total  = doc.get('sous_total') or doc.get('total', 0)
    remise_pct  = doc.get('remise_pct') or 0
    remise_mont = sous_total * remise_pct / 100 if remise_pct else 0
    total_final = doc.get('total', 0)

    total_data = [
        ['', Paragraph('Sous-total', s_muted), Paragraph(fmt_fcfa(sous_total), s_right)],
    ]
    if remise_pct:
        s_red = style('sr2', fontSize=9, textColor=HexColor('#dc2626'), alignment=TA_RIGHT)
        total_data.append([
            '',
            Paragraph(f'Remise ({int(remise_pct)} %)', s_muted),
            Paragraph(f'- {fmt_fcfa(remise_mont)}', s_red),
        ])
    total_data.append([
        '',
        Paragraph('<b>Total TTC</b>', style('tt', fontSize=11, textColor=GREY_DARK, fontName='Helvetica-Bold')),
        Paragraph(fmt_fcfa(total_final), s_total),
    ])

    total_tbl = Table(total_data, colWidths=[PAGE_W - 2*MARGIN - 60*mm - 40*mm, 60*mm, 40*mm])
    total_tbl.setStyle(TableStyle([
        ('LINEABOVE', (1, len(total_data)-1), (-1, len(total_data)-1), 0.5, GREY_BORDER),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(total_tbl)

    # Montant en lettres
    montant_lettres = doc.get('montant_lettres', '')
    if montant_lettres:
        s_lettres = style('sl', fontSize=8, textColor=GREY_MID, leading=11)
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph(f'Arrêté à la somme de : <i>{montant_lettres}</i>', s_lettres))

    # ── CONDITIONS ────────────────────────────────────────────────────
    cond = doc.get('conditions') or profil.get('conditions','')
    if cond:
        story.append(Spacer(1, 4*mm))
        story.append(HRFlowable(width='100%', thickness=0.5, color=GREY_BORDER))
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph(cond, s_muted))

    # ── FOOTER LÉGAL ─────────────────────────────────────────────────
    story.append(Spacer(1, 6*mm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=GREY_BORDER))
    story.append(Spacer(1, 3*mm))

    footer_parts = []
    if profil.get('nom'):
        footer_parts.append(f'<b>{profil["nom"]}</b>')
    if profil.get('rccm'):
        footer_parts.append(f'RCCM : {profil["rccm"]}')
    if profil.get('adresse'):
        footer_parts.append(profil['adresse'])
    if profil.get('banque'):
        footer_parts.append(profil['banque'])

    footer_data = [[
        Paragraph(' — '.join(footer_parts), s_footer),
        Paragraph('Généré via <b>helloBiz</b>', style('fg', fontSize=7, textColor=GREY_MID, alignment=TA_RIGHT, leading=10)),
    ]]
    footer_tbl = Table(footer_data, colWidths=[(PAGE_W-2*MARGIN)*0.7, (PAGE_W-2*MARGIN)*0.3])
    footer_tbl.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(footer_tbl)

    pdf.build(story)
    return out_path
