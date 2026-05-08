import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from app.models import Presence, Session, Personne, Configuration


# ============================================================
# UTILITAIRES COMMUNS
# ============================================================

def get_config():
    """Récupérer la configuration de l'établissement."""
    return Configuration.query.first()


def couleur_statut(statut):
    """Retourne la couleur selon le statut."""
    return {
        'present': colors.HexColor('#27AE60'),
        'retard': colors.HexColor('#F39C12'),
        'absent': colors.HexColor('#E74C3C'),
    }.get(statut, colors.black)


def style_excel_header():
    """Style pour les en-têtes Excel."""
    fill = PatternFill(start_color="1A5276", end_color="1A5276", fill_type="solid")
    font = Font(bold=True, color="FFFFFF", size=11)
    alignment = Alignment(horizontal="center", vertical="center")
    return fill, font, alignment


def bordure_excel():
    """Bordure fine pour les cellules Excel."""
    side = Side(style='thin', color="CCCCCC")
    return Border(left=side, right=side, top=side, bottom=side)


# ============================================================
# PDF — Rapport complet étudiant
# ============================================================

def generer_pdf_etudiant(personne_id, date_debut, date_fin):
    """
    Génère un PDF complet pour un étudiant sur une période.
    Retourne les bytes du PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    config = get_config()
    personne = Personne.query.get(personne_id)
    if not personne:
        return None

    styles = getSampleStyleSheet()
    titre_style = ParagraphStyle('titre', parent=styles['Title'],
                                  fontSize=16, textColor=colors.HexColor('#1A5276'),
                                  alignment=TA_CENTER)
    sous_titre_style = ParagraphStyle('sous_titre', parent=styles['Normal'],
                                       fontSize=11, textColor=colors.HexColor('#555555'),
                                       alignment=TA_CENTER)
    normal_style = styles['Normal']

    elements = []

    # En-tête établissement
   # nom_etab = config.nom_etablissement if config else "Établissement"
    nom_etab = (config.nom_etablissement if config and config.nom_etablissement else "Établissement")
    elements.append(Paragraph(nom_etab, titre_style))
    elements.append(Paragraph("Rapport de Présence", sous_titre_style))
    elements.append(Spacer(1, 0.5*cm))

    # Infos étudiant
    infos_data = [
        ['Nom complet', f'{personne.prenom} {personne.nom}'],
        ['Identifiant', personne.identifiant or '-'],
        ['Filière / Département', personne.departement or '-'],
        ['Groupe', personne.groupe_ou_site or '-'],
        ['Période', f'{date_debut.strftime("%d/%m/%Y")} → {date_fin.strftime("%d/%m/%Y")}'],
        ['Généré le', datetime.now().strftime("%d/%m/%Y à %H:%M")],
    ]

    infos_table = Table(infos_data, colWidths=[5*cm, 12*cm])
    infos_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#D6EAF8')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('ROWBACKGROUNDS', (1, 0), (1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(infos_table)
    elements.append(Spacer(1, 0.5*cm))

    # Récupérer les présences sur la période
    presences = Presence.query.join(Session).filter(
        Presence.personne_id == personne_id,
        Session.heure_debut >= datetime.combine(date_debut, datetime.min.time()),
        Session.heure_debut <= datetime.combine(date_fin, datetime.max.time())
    ).order_by(Session.heure_debut).all()

    # Tableau des présences
    elements.append(Paragraph("Détail des Présences", ParagraphStyle(
        'section', parent=styles['Heading2'],
        textColor=colors.HexColor('#1A5276'), fontSize=12
    )))
    elements.append(Spacer(1, 0.3*cm))

    tableau_data = [['Session', 'Date', 'Heure', 'Statut', 'Modifié par']]

    total = present = retard = absent_just = absent_injust = 0

    for p in presences:
        session = Session.query.get(p.session_id)
        if not session:
            continue

        total += 1
        statut_affiche = p.statut.upper()

        if p.statut == 'present':
            present += 1
        elif p.statut == 'retard':
            retard += 1
        elif p.statut == 'absent':
            if p.justification_absence:
                absent_just += 1
            else:
                absent_injust += 1

        modifie = p.modifie_par if p.modifie_par else '-'
        heure = p.horodatage.strftime('%H:%M') if p.horodatage else '-'

        tableau_data.append([
            session.nom[:30],
            session.heure_debut.strftime('%d/%m/%Y'),
            heure,
            statut_affiche,
            modifie
        ])

    if len(tableau_data) > 1:
        t = Table(tableau_data, colWidths=[6*cm, 3*cm, 2*cm, 3*cm, 3*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A5276')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(t)
    else:
        elements.append(Paragraph("Aucune présence enregistrée sur cette période.",
                                   normal_style))

    elements.append(Spacer(1, 0.5*cm))

    # Résumé statistiques
    elements.append(Paragraph("Résumé", ParagraphStyle(
        'section', parent=styles['Heading2'],
        textColor=colors.HexColor('#1A5276'), fontSize=12
    )))

    taux = round((present + retard) / total * 100, 1) if total > 0 else 0

    stats_data = [
        ['Total sessions', str(total), '100%'],
        ['Présent', str(present), f'{round(present/total*100,1) if total else 0}%'],
        ['Retard', str(retard), f'{round(retard/total*100,1) if total else 0}%'],
        ['Absent justifié', str(absent_just), f'{round(absent_just/total*100,1) if total else 0}%'],
        ['Absent injustifié', str(absent_injust), f'{round(absent_injust/total*100,1) if total else 0}%'],
        ['Taux de présence', f'{taux}%', ''],
    ]

    stats_table = Table(stats_data, colWidths=[7*cm, 4*cm, 6*cm])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#D6EAF8')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#D5F5E3')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(stats_table)

    # Mention conseil de discipline si nécessaire
    if absent_injust >= 3:
        elements.append(Spacer(1, 0.5*cm))
        mention = f"⚠️ Attention : {absent_injust} absences injustifiées — Vérifier le règlement de l'établissement."
        elements.append(Paragraph(mention, ParagraphStyle(
            'alerte', parent=styles['Normal'],
            textColor=colors.HexColor('#E74C3C'),
            fontSize=10, fontName='Helvetica-Bold'
        )))

    doc.build(elements)
    buffer.seek(0)
    return buffer


# ============================================================
# EXCEL — Résumé groupe
# ============================================================

def generer_excel_resume(groupe, date_debut, date_fin):
    """Génère un Excel résumé — une ligne par étudiant."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Résumé"

    fill_header, font_header, align_header = style_excel_header()
    bordure = bordure_excel()
    config = get_config()

    # Titre
    ws.merge_cells('A1:H1')
    ws['A1'] = f"{config.nom_etablissement if config else 'Établissement'} — Rapport Résumé Groupe {groupe}"
    ws['A1'].font = Font(bold=True, size=14, color="1A5276")
    ws['A1'].alignment = Alignment(horizontal="center")

    ws.merge_cells('A2:H2')
    ws['A2'] = f"Période : {date_debut.strftime('%d/%m/%Y')} → {date_fin.strftime('%d/%m/%Y')}"
    ws['A2'].alignment = Alignment(horizontal="center")

    # En-têtes
    headers = ['Nom', 'Prénom', 'Identifiant', 'Présent', 'Retard',
               'Absent Justifié', 'Absent Injustifié', 'Taux de Présence']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=header)
        cell.fill = fill_header
        cell.font = font_header
        cell.alignment = align_header
        cell.border = bordure

    # Données
    personnes = Personne.query.filter_by(
        groupe_ou_site=groupe,
        est_actif=True
    ).order_by(Personne.nom).all()

    row = 5
    for personne in personnes:
        presences = Presence.query.join(Session).filter(
            Presence.personne_id == personne.id,
            Session.heure_debut >= datetime.combine(date_debut, datetime.min.time()),
            Session.heure_debut <= datetime.combine(date_fin, datetime.max.time())
        ).all()

        total = len(presences)
        present = sum(1 for p in presences if p.statut == 'present')
        retard = sum(1 for p in presences if p.statut == 'retard')
        absent_just = sum(1 for p in presences if p.statut == 'absent' and p.justification_absence)
        absent_injust = sum(1 for p in presences if p.statut == 'absent' and not p.justification_absence)
        taux = round((present + retard) / total * 100, 1) if total > 0 else 0

        donnees = [personne.nom, personne.prenom, personne.identifiant,
                   present, retard, absent_just, absent_injust, f'{taux}%']

        bg = "FFFFFF" if row % 2 == 0 else "F9F9F9"
        fill_row = PatternFill(start_color=bg, end_color=bg, fill_type="solid")

        for col, val in enumerate(donnees, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.fill = fill_row
            cell.border = bordure
            cell.alignment = Alignment(horizontal="center")

            # Colorier le taux selon la valeur
            if col == 8:
                if taux >= 80:
                    cell.font = Font(color="27AE60", bold=True)
                elif taux >= 60:
                    cell.font = Font(color="F39C12", bold=True)
                else:
                    cell.font = Font(color="E74C3C", bold=True)

        row += 1

    # Ajuster largeurs colonnes
    largeurs = [20, 15, 15, 10, 10, 18, 20, 18]
    for i, largeur in enumerate(largeurs, 1):
        from openpyxl.utils import get_column_letter
        ws.column_dimensions[get_column_letter(i)].width = largeur

        

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ============================================================
# EXCEL — Détail groupe
# ============================================================
def generer_excel_detail(groupe, date_debut, date_fin):
    """Génère un Excel détail — une ligne par session, colonnes = étudiants."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Détail"

    fill_header, font_header, align_header = style_excel_header()
    bordure = bordure_excel()
    config = get_config()

    # Récupérer les étudiants du groupe
    personnes = Personne.query.filter_by(
        groupe_ou_site=groupe,
        est_actif=True
    ).order_by(Personne.nom).all()

    nb_cols = max(3 + len(personnes), 6)
    from openpyxl.utils import get_column_letter
    derniere_col = get_column_letter(nb_cols)

    # Titre
    ws.merge_cells(f'A1:{derniere_col}1')
    ws['A1'] = f"{config.nom_etablissement if config else 'Établissement'} — Rapport Détail Groupe {groupe}"
    ws['A1'].font = Font(bold=True, size=14, color="1A5276")
    ws['A1'].alignment = Alignment(horizontal="center")

    # Période
    ws.merge_cells(f'A2:{derniere_col}2')
    ws['A2'] = f"Période : {date_debut.strftime('%d/%m/%Y')} → {date_fin.strftime('%d/%m/%Y')}"
    ws['A2'].alignment = Alignment(horizontal="center")
    ws['A2'].font = Font(size=11, color="555555")

    # En-têtes ligne 4
    headers = ['Session', 'Date', 'Heure'] + [f'{p.prenom} {p.nom}' for p in personnes]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=header)
        cell.fill = fill_header
        cell.font = font_header
        cell.alignment = align_header
        cell.border = bordure

    # Récupérer les sessions sur la période
    sessions = Session.query.filter(
        Session.heure_debut >= datetime.combine(date_debut, datetime.min.time()),
        Session.heure_debut <= datetime.combine(date_fin, datetime.max.time()),
        Session.statut == 'terminee'
    ).order_by(Session.heure_debut).all()

    # Données à partir ligne 5
    fill_present = PatternFill(start_color="D5F5E3", end_color="D5F5E3", fill_type="solid")
    fill_retard  = PatternFill(start_color="FDEBD0", end_color="FDEBD0", fill_type="solid")
    fill_absent  = PatternFill(start_color="FADBD8", end_color="FADBD8", fill_type="solid")

    for row_idx, session in enumerate(sessions, 5):
        ws.cell(row=row_idx, column=1, value=session.nom).border = bordure
        ws.cell(row=row_idx, column=2,
                value=session.heure_debut.strftime('%d/%m/%Y')).border = bordure
        ws.cell(row=row_idx, column=3,
                value=session.heure_debut.strftime('%H:%M')).border = bordure

        for col_idx, personne in enumerate(personnes, 4):
            presence = Presence.query.filter_by(
                personne_id=personne.id,
                session_id=session.id
            ).first()

            if presence:
                statut = presence.statut.upper()
                cell = ws.cell(row=row_idx, column=col_idx, value=statut)
                if presence.statut == 'present':
                    cell.fill = fill_present
                elif presence.statut == 'retard':
                    cell.fill = fill_retard
                else:
                    cell.fill = fill_absent
            else:
                cell = ws.cell(row=row_idx, column=col_idx, value='-')

            cell.border = bordure
            cell.alignment = Alignment(horizontal="center")

    # Largeurs colonnes
    ws.column_dimensions[get_column_letter(1)].width = 25
    ws.column_dimensions[get_column_letter(2)].width = 12
    ws.column_dimensions[get_column_letter(3)].width = 8
    for i in range(4, 4 + len(personnes)):
        ws.column_dimensions[get_column_letter(i)].width = 18

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ============================================================
# EXCEL — Complet (résumé + détail)
# ============================================================

def generer_excel_complet(groupe, date_debut, date_fin):
    """Génère un Excel avec 2 onglets : Résumé + Détail."""
    from openpyxl.utils import get_column_letter

    wb_resume = openpyxl.load_workbook(
        generer_excel_resume(groupe, date_debut, date_fin)
    )
    wb_detail = openpyxl.load_workbook(
        generer_excel_detail(groupe, date_debut, date_fin)
    )

    wb_final = openpyxl.Workbook()
    wb_final.remove(wb_final.active)

    for ws_src in wb_resume.worksheets:
        ws_copy = wb_final.create_sheet(title="Résumé")
        for row in ws_src.iter_rows():
            for cell in row:
                new_cell = ws_copy.cell(row=cell.row, column=cell.column, value=cell.value)
                if cell.has_style:
                    new_cell.font = cell.font.copy()
                    new_cell.fill = cell.fill.copy()
                    new_cell.border = cell.border.copy()
                    new_cell.alignment = cell.alignment.copy()
        # Copier les largeurs de colonnes
        for col, dim in ws_src.column_dimensions.items():
            ws_copy.column_dimensions[col].width = dim.width
        # Copier les cellules fusionnées
        for merge in ws_src.merged_cells.ranges:
            ws_copy.merge_cells(str(merge))

    for ws_src in wb_detail.worksheets:
        ws_copy = wb_final.create_sheet(title="Détail")
        for row in ws_src.iter_rows():
            for cell in row:
                new_cell = ws_copy.cell(row=cell.row, column=cell.column, value=cell.value)
                if cell.has_style:
                    new_cell.font = cell.font.copy()
                    new_cell.fill = cell.fill.copy()
                    new_cell.border = cell.border.copy()
                    new_cell.alignment = cell.alignment.copy()
        # Copier les largeurs de colonnes
        for col, dim in ws_src.column_dimensions.items():
            ws_copy.column_dimensions[col].width = dim.width
        # Copier les cellules fusionnées
        for merge in ws_src.merged_cells.ranges:
            ws_copy.merge_cells(str(merge))

    buffer = io.BytesIO()
    wb_final.save(buffer)
    buffer.seek(0)
    return buffer