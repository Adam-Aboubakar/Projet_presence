from flask import Blueprint, render_template, redirect, url_for, request, session
from flask_login import login_required, current_user
from datetime import datetime, timezone
from babel.dates import format_date

main = Blueprint('main', __name__)


@main.route('/langue/<code>')
def changer_langue(code):
    if code in ['fr', 'en', 'ar']:
        session['langue'] = code
    return redirect(request.referrer or url_for('main.index'))


@main.route('/')
@login_required
def index():
    from app.models import Configuration, Session
    config = Configuration.get_config()
    maintenant = datetime.now(timezone.utc)
    date_formatee = format_date(maintenant, format='full', locale='fr_FR')

    sessions_en_cours = Session.query.filter_by(
        statut='en_cours'
    ).order_by(Session.heure_debut.asc()).all()

    sessions_a_venir = Session.query.filter_by(
        statut='planifiee'
    ).filter(
        Session.heure_debut > maintenant
    ).order_by(Session.heure_debut.asc()).limit(10).all()

    return render_template(
        'accueil.html',
        config=config,
        sessions_en_cours=sessions_en_cours,
        sessions_a_venir=sessions_a_venir,
        maintenant=maintenant,
        date_formatee=date_formatee
    )


@main.route('/mon-espace')
@login_required
def mon_espace():
    if current_user.role == 'admin':
        return redirect(url_for('admin.tableau_de_bord'))
    elif current_user.role == 'enseignant':
        return redirect(url_for('admin.tableau_de_bord'))
    elif current_user.role == 'agent':
        return redirect(url_for('admin.tableau_de_bord'))
    return redirect(url_for('main.index'))


@main.route('/health')
def health():
    return {"status": "ok", "message": "Serveur opérationnel"}