from flask import request, jsonify, send_file, render_template
from datetime import datetime
from app.rapports import rapports_bp
from app.rapports.utils import (
    generer_pdf_etudiant,
    generer_excel_resume,
    generer_excel_detail,
    generer_excel_complet,
    generer_excel_session
)
from app.models import Presence, Session, Personne, db
from app.auth.decorateurs import role_requis


# ============================================================
# PDF — Rapport complet étudiant
# ============================================================
@rapports_bp.route('/api/pdf/etudiant/<string:personne_id>', methods=['GET'])
@role_requis('enseignant')
def pdf_etudiant(personne_id):
    date_debut_str = request.args.get('date_debut')
    date_fin_str   = request.args.get('date_fin')

    if not date_debut_str or not date_fin_str:
        return jsonify({'succes': False, 'message': 'date_debut et date_fin obligatoires'}), 400

    try:
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        date_fin   = datetime.strptime(date_fin_str,   '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'succes': False, 'message': 'Format date invalide. Utiliser YYYY-MM-DD'}), 400

    if date_fin < date_debut:
        return jsonify({'succes': False, 'message': 'date_fin doit être après date_debut'}), 400

    personne = Personne.query.get_or_404(personne_id)
    buffer   = generer_pdf_etudiant(personne_id, date_debut, date_fin)

    if not buffer:
        return jsonify({'succes': False, 'message': 'Erreur génération PDF'}), 500

    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"rapport_{personne.nom}_{personne.prenom}_{date_debut_str}_{date_fin_str}.pdf"
    )


# ============================================================
# EXCEL — Résumé groupe
# ============================================================
@rapports_bp.route('/api/excel/groupe/resume', methods=['GET'])
@role_requis('enseignant')
def excel_resume():
    groupe         = request.args.get('groupe')
    date_debut_str = request.args.get('date_debut')
    date_fin_str   = request.args.get('date_fin')

    if not groupe or not date_debut_str or not date_fin_str:
        return jsonify({'succes': False, 'message': 'groupe, date_debut et date_fin obligatoires'}), 400

    try:
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        date_fin   = datetime.strptime(date_fin_str,   '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'succes': False, 'message': 'Format date invalide. Utiliser YYYY-MM-DD'}), 400

    return send_file(
        generer_excel_resume(groupe, date_debut, date_fin),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"resume_{groupe}_{date_debut_str}_{date_fin_str}.xlsx"
    )


# ============================================================
# EXCEL — Détail groupe
# ============================================================
@rapports_bp.route('/api/excel/groupe/detail', methods=['GET'])
@role_requis('enseignant')
def excel_detail():
    groupe         = request.args.get('groupe')
    date_debut_str = request.args.get('date_debut')
    date_fin_str   = request.args.get('date_fin')

    if not groupe or not date_debut_str or not date_fin_str:
        return jsonify({'succes': False, 'message': 'groupe, date_debut et date_fin obligatoires'}), 400

    try:
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        date_fin   = datetime.strptime(date_fin_str,   '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'succes': False, 'message': 'Format date invalide. Utiliser YYYY-MM-DD'}), 400

    return send_file(
        generer_excel_detail(groupe, date_debut, date_fin),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"detail_{groupe}_{date_debut_str}_{date_fin_str}.xlsx"
    )


# ============================================================
# EXCEL — Complet groupe (résumé + détail)
# ============================================================
@rapports_bp.route('/api/excel/groupe/complet', methods=['GET'])
@role_requis('enseignant')
def excel_complet():
    groupe         = request.args.get('groupe')
    date_debut_str = request.args.get('date_debut')
    date_fin_str   = request.args.get('date_fin')

    if not groupe or not date_debut_str or not date_fin_str:
        return jsonify({'succes': False, 'message': 'groupe, date_debut et date_fin obligatoires'}), 400

    try:
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        date_fin   = datetime.strptime(date_fin_str,   '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'succes': False, 'message': 'Format date invalide. Utiliser YYYY-MM-DD'}), 400

    return send_file(
        generer_excel_complet(groupe, date_debut, date_fin),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"complet_{groupe}_{date_debut_str}_{date_fin_str}.xlsx"
    )


# ============================================================
# EXCEL — Session unique
# ============================================================
@rapports_bp.route('/api/excel/session/<string:session_id>', methods=['GET'])
@role_requis('enseignant')
def excel_session(session_id):
    seance = Session.query.get_or_404(session_id)
    return send_file(
        generer_excel_session(session_id),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"session_{seance.nom}_{seance.heure_debut.strftime('%Y-%m-%d')}.xlsx"
    )


# ============================================================
# STATS — Session (API mobile)
# ============================================================
@rapports_bp.route('/api/stats/session/<string:session_id>', methods=['GET'])
@role_requis('enseignant')
def stats_session(session_id):
    session   = Session.query.get_or_404(session_id)
    presences = Presence.query.filter_by(session_id=session_id).all()

    total   = len(presences)
    present = sum(1 for p in presences if p.statut == 'present')
    retard  = sum(1 for p in presences if p.statut == 'retard')
    absent  = sum(1 for p in presences if p.statut == 'absent')

    return jsonify({
        'succes':  True,
        'session': session.nom,
        'date':    session.heure_debut.strftime('%d/%m/%Y'),
        'stats': {
            'total':          total,
            'present':        present,
            'retard':         retard,
            'absent':         absent,
            'taux_presence':  round((present + retard) / total * 100, 1) if total > 0 else 0
        }
    }), 200


# ============================================================
# STATS — Étudiant (API mobile)
# ============================================================
@rapports_bp.route('/api/stats/etudiant/<string:personne_id>', methods=['GET'])
@role_requis('enseignant')
def stats_etudiant(personne_id):
    personne  = Personne.query.get_or_404(personne_id)
    presences = Presence.query.filter_by(personne_id=personne_id).all()

    total         = len(presences)
    present       = sum(1 for p in presences if p.statut == 'present')
    retard        = sum(1 for p in presences if p.statut == 'retard')
    absent_just   = sum(1 for p in presences if p.statut == 'absent' and p.justification_absence)
    absent_injust = sum(1 for p in presences if p.statut == 'absent' and not p.justification_absence)

    return jsonify({
        'succes':   True,
        'etudiant': f'{personne.prenom} {personne.nom}',
        'stats': {
            'total':              total,
            'present':            present,
            'retard':             retard,
            'absent_justifie':    absent_just,
            'absent_injustifie':  absent_injust,
            'taux_presence':      round((present + retard) / total * 100, 1) if total > 0 else 0
        }
    }), 200


# ============================================================
# PAGE WEB — Liste des rapports
# ============================================================
@rapports_bp.route('/')
@role_requis('enseignant')
def liste():
    from app.models import Configuration
    config = Configuration.get_config()
    mode   = config.mode if config else 'ecole'

    groupes = db.session.query(Personne.groupe_ou_site)\
        .filter(Personne.groupe_ou_site != None)\
        .distinct().all()
    groupes = [g[0] for g in groupes if g[0]]

    return render_template('rapports/liste.html', groupes=groupes, mode=mode)