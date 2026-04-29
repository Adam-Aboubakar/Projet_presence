from flask import request, jsonify, send_file
from datetime import datetime
from app.rapports import rapports_bp
from app.rapports.utils import (
    generer_pdf_etudiant,
    generer_excel_resume,
    generer_excel_detail,
    generer_excel_complet
)
from app.models import Presence, Session, Personne
from app.auth.decorateurs import role_requis


# ============================================================
# PDF — Rapport complet étudiant
# ============================================================
@rapports_bp.route('/api/pdf/etudiant/<string:personne_id>', methods=['GET'])
@role_requis('enseignant')
def pdf_etudiant(personne_id):
    date_debut_str = request.args.get('date_debut')
    date_fin_str = request.args.get('date_fin')

    if not date_debut_str or not date_fin_str:
        return jsonify({'succes': False, 'message': 'date_debut et date_fin obligatoires'}), 400

    try:
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'succes': False, 'message': 'Format date invalide. Utiliser YYYY-MM-DD'}), 400

    if date_fin < date_debut:
        return jsonify({'succes': False, 'message': 'date_fin doit être après date_debut'}), 400

    personne = Personne.query.get_or_404(personne_id)
    buffer = generer_pdf_etudiant(personne_id, date_debut, date_fin)

    if not buffer:
        return jsonify({'succes': False, 'message': 'Erreur génération PDF'}), 500

    nom_fichier = f"rapport_{personne.nom}_{personne.prenom}_{date_debut_str}_{date_fin_str}.pdf"

    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=nom_fichier
    )


# ============================================================
# EXCEL — Résumé groupe
# ============================================================
@rapports_bp.route('/api/excel/groupe/resume', methods=['GET'])
@role_requis('enseignant')
def excel_resume():
    groupe = request.args.get('groupe')
    date_debut_str = request.args.get('date_debut')
    date_fin_str = request.args.get('date_fin')

    if not groupe or not date_debut_str or not date_fin_str:
        return jsonify({'succes': False, 'message': 'groupe, date_debut et date_fin obligatoires'}), 400

    try:
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'succes': False, 'message': 'Format date invalide. Utiliser YYYY-MM-DD'}), 400

    buffer = generer_excel_resume(groupe, date_debut, date_fin)
    nom_fichier = f"resume_{groupe}_{date_debut_str}_{date_fin_str}.xlsx"

    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=nom_fichier
    )


# ============================================================
# EXCEL — Détail groupe
# ============================================================
@rapports_bp.route('/api/excel/groupe/detail', methods=['GET'])
@role_requis('enseignant')
def excel_detail():
    groupe = request.args.get('groupe')
    date_debut_str = request.args.get('date_debut')
    date_fin_str = request.args.get('date_fin')

    if not groupe or not date_debut_str or not date_fin_str:
        return jsonify({'succes': False, 'message': 'groupe, date_debut et date_fin obligatoires'}), 400

    try:
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'succes': False, 'message': 'Format date invalide. Utiliser YYYY-MM-DD'}), 400

    buffer = generer_excel_detail(groupe, date_debut, date_fin)
    nom_fichier = f"detail_{groupe}_{date_debut_str}_{date_fin_str}.xlsx"

    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=nom_fichier
    )


# ============================================================
# EXCEL — Complet groupe (résumé + détail)
# ============================================================
@rapports_bp.route('/api/excel/groupe/complet', methods=['GET'])
@role_requis('enseignant')
def excel_complet():
    groupe = request.args.get('groupe')
    date_debut_str = request.args.get('date_debut')
    date_fin_str = request.args.get('date_fin')

    if not groupe or not date_debut_str or not date_fin_str:
        return jsonify({'succes': False, 'message': 'groupe, date_debut et date_fin obligatoires'}), 400

    try:
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'succes': False, 'message': 'Format date invalide. Utiliser YYYY-MM-DD'}), 400

    buffer = generer_excel_complet(groupe, date_debut, date_fin)
    nom_fichier = f"complet_{groupe}_{date_debut_str}_{date_fin_str}.xlsx"

    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=nom_fichier
    )


# ============================================================
# STATS — Session
# ============================================================
@rapports_bp.route('/api/stats/session/<string:session_id>', methods=['GET'])
@role_requis('enseignant')
def stats_session(session_id):
    session = Session.query.get_or_404(session_id)
    presences = Presence.query.filter_by(session_id=session_id).all()

    total = len(presences)
    present = sum(1 for p in presences if p.statut == 'present')
    retard = sum(1 for p in presences if p.statut == 'retard')
    absent = sum(1 for p in presences if p.statut == 'absent')

    return jsonify({
        'succes': True,
        'session': session.nom,
        'date': session.heure_debut.strftime('%d/%m/%Y'),
        'stats': {
            'total': total,
            'present': present,
            'retard': retard,
            'absent': absent,
            'taux_presence': round((present + retard) / total * 100, 1) if total > 0 else 0
        }
    }), 200


# ============================================================
# STATS — Étudiant
# ============================================================
@rapports_bp.route('/api/stats/etudiant/<string:personne_id>', methods=['GET'])
@role_requis('enseignant')
def stats_etudiant(personne_id):
    personne = Personne.query.get_or_404(personne_id)
    presences = Presence.query.filter_by(personne_id=personne_id).all()

    total = len(presences)
    present = sum(1 for p in presences if p.statut == 'present')
    retard = sum(1 for p in presences if p.statut == 'retard')
    absent_just = sum(1 for p in presences if p.statut == 'absent' and p.justification_absence)
    absent_injust = sum(1 for p in presences if p.statut == 'absent' and not p.justification_absence)

    return jsonify({
        'succes': True,
        'etudiant': f'{personne.prenom} {personne.nom}',
        'stats': {
            'total': total,
            'present': present,
            'retard': retard,
            'absent_justifie': absent_just,
            'absent_injustifie': absent_injust,
            'taux_presence': round((present + retard) / total * 100, 1) if total > 0 else 0
        }
    }), 200