from flask import Blueprint, render_template, redirect, url_for, request, session
from flask_login import login_required, current_user
from datetime import datetime, timezone, date
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
    from app.models import Configuration, Session, Presence, Personne
    config = Configuration.get_config()
    maintenant = datetime.now(timezone.utc)
    date_formatee = format_date(maintenant, format='full', locale='fr_FR')
    mode = config.mode if config else 'ecole'

    if mode == 'ecole':
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
            date_formatee=date_formatee,
            mode=mode
        )
    else:
        aujourd_hui = date.today()
        debut_jour = datetime(aujourd_hui.year, aujourd_hui.month, aujourd_hui.day, tzinfo=timezone.utc)

        pointages = Presence.query.filter(
            Presence.horodatage >= debut_jour
        ).order_by(Presence.horodatage.desc()).all()

        nb_presents = Presence.query.filter(
            Presence.horodatage >= debut_jour,
            Presence.statut == 'present'
        ).count()

        nb_absents = Personne.query.filter_by(est_actif=True).count() - nb_presents

        return render_template(
            'accueil.html',
            config=config,
            pointages=pointages,
            nb_presents=nb_presents,
            nb_absents=nb_absents,
            maintenant=maintenant,
            date_formatee=date_formatee,
            mode=mode
        )

@main.route('/mon-espace')
@login_required
def mon_espace():
    if current_user.role == 'admin':
        return redirect(url_for('admin.tableau_de_bord'))
    elif current_user.role == 'enseignant':
        return redirect(url_for('emplois.liste'))
    elif current_user.role == 'agent':
        return redirect(url_for('personnes.liste'))
    return redirect(url_for('main.index'))


@main.route('/health')
def health():
    return {"status": "ok", "message": "Serveur opérationnel"}