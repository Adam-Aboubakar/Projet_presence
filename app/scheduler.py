from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import atexit
import logging
import os

scheduler = BackgroundScheduler()


def ouvrir_sessions_prevues():
    from app import db
    from app.models import Session

    with scheduler.app.app_context():
        maintenant = datetime.now()
        sessions_a_ouvrir = Session.query.filter(
            Session.statut == 'planifiee',
            Session.heure_debut <= maintenant,
            Session.heure_fin >= maintenant
        ).all()

        for session in sessions_a_ouvrir:
            session.statut = 'en_cours'
            db.session.commit()
            print(f"[SCHEDULER] Session ouverte : {session.nom}")


def _verifier_seuils_absences(personne_id):
    """Vérifie si la personne a atteint un seuil d'absences et envoie l'email configuré."""
    from app.models import SeuilAbsence, Presence, Personne
    from app.auth.email import envoyer_email

    nb_absences = Presence.query.filter_by(
        personne_id=personne_id,
        statut='absent',
        justification_absence=None
    ).count()

    seuils = SeuilAbsence.query.filter_by(est_actif=True)\
        .order_by(SeuilAbsence.niveau.desc()).all()

    if not seuils:
        return  # Aucun seuil configuré — pas d'email

    personne = Personne.query.get(personne_id)
    if not personne:
        return

    for seuil in seuils:
        if nb_absences >= seuil.nb_absences:
            if personne.email:
                message = seuil.message_email\
                    .replace('{prenom}', personne.prenom)\
                    .replace('{nom}', personne.nom)\
                    .replace('{nb_absences}', str(nb_absences))
                try:
                    envoyer_email(
                        destinataire=personne.email,
                        sujet=seuil.sujet_email,
                        corps_html=f"<p>{message}</p>"
                    )
                    print(f"[SCHEDULER] Email seuil envoyé à {personne.email} — {nb_absences} absences")
                except Exception as e:
                    logging.error(f"[SCHEDULER] Erreur email seuil : {str(e)}")
            break  # Un seul seuil déclenché à la fois


def fermer_sessions_terminees():
    from app import db
    from app.models import Session, Presence, Personne, EmploiDuTemps

    with scheduler.app.app_context():
        maintenant = datetime.now()

        sessions_a_fermer = Session.query.filter(
            Session.statut == 'en_cours',
            Session.heure_fin < maintenant
        ).all()

        for session in sessions_a_fermer:
            session.statut = 'terminee'
            print(f"[SCHEDULER] Fermeture session : {session.nom}")

            personnes_ayant_pointe = {
                p.personne_id for p in Presence.query.filter_by(
                    session_id=session.id
                ).filter(Presence.statut.in_(['present', 'retard'])).all()
            }

            departement = niveau = groupe = None
            if session.emploi_du_temps_id:
                emploi = EmploiDuTemps.query.get(session.emploi_du_temps_id)
                if emploi:
                    departement = emploi.departement
                    niveau      = emploi.niveau
                    groupe      = emploi.groupe

            print(f"[SCHEDULER] Filtres — dept:{departement} niveau:{niveau} groupe:{groupe}")

            query = Personne.query.filter_by(est_actif=True)
            if departement:
                query = query.filter(Personne.departement.ilike(departement))
            if niveau:
                query = query.filter(Personne.niveau_ou_poste.ilike(niveau))
            if groupe:
                query = query.filter(Personne.groupe_ou_site.ilike(groupe))

            toutes_personnes = query.all()
            print(f"[SCHEDULER] {len(toutes_personnes)} personnes concernees")

            for personne in toutes_personnes:
                if personne.id not in personnes_ayant_pointe:
                    absence = Presence(
                        personne_id=personne.id,
                        session_id=session.id,
                        statut='absent',
                        methode_validation='automatique',
                        horodatage=maintenant
                    )
                    db.session.add(absence)
                    # Email géré uniquement par les seuils configurés par l'admin
                    _verifier_seuils_absences(personne.id)

            db.session.commit()
            print(f"[SCHEDULER] Session {session.nom} traitee")


def init_scheduler(app):
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return

    scheduler.app = app

    scheduler.add_job(
        func=ouvrir_sessions_prevues,
        trigger=IntervalTrigger(minutes=1),
        id='ouvrir_sessions',
        name='Ouvrir sessions planifiees',
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1
    )

    scheduler.add_job(
        func=fermer_sessions_terminees,
        trigger=IntervalTrigger(minutes=1),
        id='fermer_sessions',
        name='Fermer sessions terminees',
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1
    )

    scheduler.start()

    with app.app_context():
        ouvrir_sessions_prevues()
        fermer_sessions_terminees()

    atexit.register(lambda: scheduler.shutdown())