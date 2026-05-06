from flask import request, jsonify, Response
from datetime import datetime, timedelta
import csv
import io
from app.journal import journal_bp
from app.models import db, JournalSecurite, Utilisateur, Personne, Configuration
from app.auth.decorateurs import role_requis
from flask_login import current_user
from flask_mail import Message
from app import mail
from flask import request, jsonify, Response, render_template


# ============================================================
# FONCTION INTERNE — Envoyer alertes email
# Appelée automatiquement après chaque événement CRITIQUE ou WARNING
# ============================================================
def envoyer_alerte(log):
    """
    Envoie un email d'alerte selon la sévérité de l'événement.

    Règle :
        INFO     → aucun email
        WARNING  → email à l'admin uniquement
        CRITIQUE → email au développeur ET à l'admin
    """
    # Pas d'email pour les événements INFO
    if log.severite == 'INFO':
        return

    config = Configuration.query.first()
    if not config:
        return

    email_admin = config.email_admin
    email_dev = config.email_developpeur

    # Corps de l'email
    sujet = f"[{log.severite}] {log.type_evenement}"
    corps = f"""
    <h2>Alerte Sécurité — {log.severite}</h2>
    <table border="1" cellpadding="6" cellspacing="0">
        <tr><td><b>Type</b></td><td>{log.type_evenement}</td></tr>
        <tr><td><b>Description</b></td><td>{log.description or '-'}</td></tr>
        <tr><td><b>Sévérité</b></td><td>{log.severite}</td></tr>
        <tr><td><b>Adresse IP</b></td><td>{log.adresse_ip or '-'}</td></tr>
        <tr><td><b>Horodatage</b></td><td>{log.horodatage.strftime('%d/%m/%Y à %H:%M:%S')}</td></tr>
    </table>
    """

    try:
        # WARNING → admin uniquement
        if log.severite == 'WARNING' and email_admin:
            msg = Message(
                subject=sujet,
                recipients=[email_admin],
                html=corps
            )
            mail.send(msg)

        # CRITIQUE → développeur + admin
        elif log.severite == 'CRITIQUE':
            destinataires = []
            if email_dev:
                destinataires.append(email_dev)
            if email_admin and email_admin not in destinataires:
                destinataires.append(email_admin)

            if destinataires:
                msg = Message(
                    subject=sujet,
                    recipients=destinataires,
                    html=corps
                )
                mail.send(msg)

    except Exception as e:
        # Ne jamais bloquer l'application si l'email échoue
        print(f"[ALERTE EMAIL ECHOUEE] {e}")


# ============================================================
# CAS 1 — Liste des logs avec filtres
# Accessible uniquement par l'admin
# ============================================================
@journal_bp.route('/')
@journal_bp.route('/api/liste', methods=['GET'])
@role_requis('admin')
def liste_logs():
    # Récupérer les paramètres de filtrage
    severite       = request.args.get('severite')
    type_evenement = request.args.get('type')
    date_debut_str = request.args.get('date_debut')
    date_fin_str   = request.args.get('date_fin')
    page           = int(request.args.get('page', 1))
    par_page       = int(request.args.get('par_page', 20))

    query = JournalSecurite.query

    if severite:
        query = query.filter_by(severite=severite.upper())
    if type_evenement:
        query = query.filter_by(type_evenement=type_evenement)
    if date_debut_str:
        try:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d')
            query = query.filter(JournalSecurite.horodatage >= date_debut)
        except ValueError:
            pass
    if date_fin_str:
        try:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(JournalSecurite.horodatage <= date_fin)
        except ValueError:
            pass

    query = query.order_by(JournalSecurite.horodatage.desc())
    total = query.count()
    logs  = query.offset((page - 1) * par_page).limit(par_page).all()
    pages = (total + par_page - 1) // par_page

    # Stats 24h
    depuis_24h    = datetime.utcnow() - timedelta(hours=24)
    infos_24h     = JournalSecurite.query.filter(JournalSecurite.horodatage >= depuis_24h, JournalSecurite.severite == 'INFO').count()
    warnings_24h  = JournalSecurite.query.filter(JournalSecurite.horodatage >= depuis_24h, JournalSecurite.severite == 'WARNING').count()
    critiques_24h = JournalSecurite.query.filter(JournalSecurite.horodatage >= depuis_24h, JournalSecurite.severite == 'CRITIQUE').count()

    config = Configuration.get_config()

    # Si requête API → JSON
    if request.headers.get('Accept') == 'application/json' or request.args.get('format') == 'json':
        return jsonify({
            'succes': True,
            'pagination': {'page': page, 'par_page': par_page, 'total': total, 'pages': pages},
            'logs': [{'id': l.id, 'horodatage': l.horodatage.strftime('%d/%m/%Y %H:%M:%S'),
                      'type_evenement': l.type_evenement, 'severite': l.severite,
                      'description': l.description, 'adresse_ip': l.adresse_ip,
                      'utilisateur_id': l.utilisateur_id} for l in logs]
        }), 200

    # Sinon → template HTML
    return render_template(
        'journal/liste_logs.html',
        logs=logs,
        total=total,
        page=page,
        pages=pages,
        par_page=par_page,
        infos_24h=infos_24h,
        warnings_24h=warnings_24h,
        critiques_24h=critiques_24h,
        severite=severite,
        type_evenement=type_evenement,
        date_debut_str=date_debut_str,
        date_fin_str=date_fin_str,
        config=config
    )

# ============================================================
# CAS 2 — Statistiques de sécurité
# Tableau de bord sécurité pour l'admin
# ============================================================
@journal_bp.route('/api/stats', methods=['GET'])
@role_requis('admin')
def stats_securite():
    """
    Retourne les statistiques de sécurité :
        - Événements par sévérité sur les dernières 24h
        - Top 5 types d'événements les plus fréquents
        - Nombre d'événements sur les 7 derniers jours
    """
    maintenant = datetime.utcnow()
    depuis_24h = maintenant - timedelta(hours=24)
    depuis_7j = maintenant - timedelta(days=7)

    # Événements par sévérité sur 24h
    logs_24h = JournalSecurite.query.filter(
        JournalSecurite.horodatage >= depuis_24h
    ).all()

    info_24h = sum(1 for l in logs_24h if l.severite == 'INFO')
    warning_24h = sum(1 for l in logs_24h if l.severite == 'WARNING')
    critique_24h = sum(1 for l in logs_24h if l.severite == 'CRITIQUE')

    # Top 5 types d'événements sur 7 jours
    from sqlalchemy import func
    top5 = db.session.query(
        JournalSecurite.type_evenement,
        func.count(JournalSecurite.id).label('count')
    ).filter(
        JournalSecurite.horodatage >= depuis_7j
    ).group_by(
        JournalSecurite.type_evenement
    ).order_by(
        func.count(JournalSecurite.id).desc()
    ).limit(5).all()

    # Évolution sur 7 jours — nombre d'événements par jour
    evolution = []
    for i in range(6, -1, -1):
        jour = maintenant - timedelta(days=i)
        debut_jour = jour.replace(hour=0, minute=0, second=0, microsecond=0)
        fin_jour = debut_jour + timedelta(days=1)
        count = JournalSecurite.query.filter(
            JournalSecurite.horodatage >= debut_jour,
            JournalSecurite.horodatage < fin_jour
        ).count()
        evolution.append({
            'date': debut_jour.strftime('%d/%m'),
            'count': count
        })

    return jsonify({
        'succes': True,
        'dernières_24h': {
            'info': info_24h,
            'warning': warning_24h,
            'critique': critique_24h,
            'total': len(logs_24h)
        },
        'top5_evenements': [
            {'type': t, 'count': c} for t, c in top5
        ],
        'evolution_7_jours': evolution
    }), 200


# ============================================================
# CAS 3 — Export CSV des logs
# Pour archivage ou audit externe
# ============================================================
@journal_bp.route('/api/export/csv', methods=['GET'])
@role_requis('admin')
def export_csv():
    """
    Exporte tous les logs en fichier CSV.
    Paramètres GET optionnels : mêmes filtres que /liste
    """
    # Mêmes filtres que liste_logs
    severite = request.args.get('severite')
    date_debut_str = request.args.get('date_debut')
    date_fin_str = request.args.get('date_fin')

    query = JournalSecurite.query

    if severite:
        query = query.filter_by(severite=severite.upper())

    if date_debut_str:
        try:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d')
            query = query.filter(JournalSecurite.horodatage >= date_debut)
        except ValueError:
            return jsonify({'succes': False, 'message': 'Format date invalide'}), 400

    if date_fin_str:
        try:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(JournalSecurite.horodatage <= date_fin)
        except ValueError:
            return jsonify({'succes': False, 'message': 'Format date invalide'}), 400

    logs = query.order_by(JournalSecurite.horodatage.desc()).all()

    # Générer le CSV en mémoire
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')

    # En-têtes CSV
    writer.writerow([
        'ID', 'Date', 'Heure', 'Type Événement', 'Sévérité',
        'Description', 'Adresse IP', 'Utilisateur ID', 'Personne ID'
    ])

    # Données
    for log in logs:
        writer.writerow([
            log.id,
            log.horodatage.strftime('%d/%m/%Y'),
            log.horodatage.strftime('%H:%M:%S'),
            log.type_evenement,
            log.severite,
            log.description or '',
            log.adresse_ip or '',
            log.utilisateur_id or '',
            log.personne_id or ''
        ])

    output.seek(0)
    nom_fichier = f"journal_securite_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={nom_fichier}'}
    )


# ============================================================
# CAS 4 — Détail d'un log
# ============================================================
@journal_bp.route('/api/<string:log_id>', methods=['GET'])
@role_requis('admin')
def detail_log(log_id):
    """Retourne le détail complet d'un événement du journal."""
    log = JournalSecurite.query.get_or_404(log_id)

    return jsonify({
        'succes': True,
        'log': {
            'id': log.id,
            'horodatage': log.horodatage.strftime('%d/%m/%Y %H:%M:%S'),
            'type_evenement': log.type_evenement,
            'severite': log.severite,
            'description': log.description,
            'adresse_ip': log.adresse_ip,
            'resultat': log.resultat,
            'destinataire': log.destinataire,
            'utilisateur_id': log.utilisateur_id,
            'personne_id': log.personne_id,
            'carte_rfid_id': log.carte_rfid_id
        }
    }), 200