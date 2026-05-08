from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit

scheduler = BackgroundScheduler()

def ouvrir_sessions_prevues():
    """Ouvre automatiquement les sessions planifiées à l'heure prévue."""
    from app import db
    from app.models import Session
    from datetime import datetime, timezone, timedelta

    with scheduler.app.app_context():
        maintenant = datetime.now(timezone.utc)
        
        # Trouver les sessions planifiées dont l'heure de début est passée
        sessions_a_ouvrir = Session.query.filter(
            Session.statut == 'planifiee',
            Session.heure_debut <= maintenant,
            Session.heure_fin >= maintenant
        ).all()

        for session in sessions_a_ouvrir:
            session.statut = 'en_cours'
            db.session.commit()


def fermer_sessions_terminees():
    """Ferme automatiquement les sessions dont l'heure de fin est passée."""
    from app import db
    from app.models import Session, Presence, Personne
    from datetime import datetime, timezone

    with scheduler.app.app_context():
        maintenant = datetime.now(timezone.utc)

        sessions_a_fermer = Session.query.filter(
            Session.statut == 'en_cours',
            Session.heure_fin < maintenant
        ).all()

        for session in sessions_a_fermer:
            session.statut = 'terminee'

            # Marquer absents ceux qui n'ont pas pointé
            personnes_ayant_pointe = {
                p.personne_id for p in Presence.query.filter_by(
                    session_id=session.id
                ).filter(Presence.statut.in_(['present', 'retard'])).all()
            }

            toutes_personnes = Personne.query.filter_by(est_actif=True).all()
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

            db.session.commit()


def init_scheduler(app):
    """Initialiser et démarrer le scheduler."""
    scheduler.app = app

    # Vérifier toutes les minutes si des sessions doivent être ouvertes
    scheduler.add_job(
        func=ouvrir_sessions_prevues,
        trigger=IntervalTrigger(minutes=1),
        id='ouvrir_sessions',
        name='Ouvrir sessions planifiées',
        replace_existing=True
    )

    # Vérifier toutes les minutes si des sessions doivent être fermées
    scheduler.add_job(
        func=fermer_sessions_terminees,
        trigger=IntervalTrigger(minutes=1),
        id='fermer_sessions',
        name='Fermer sessions terminées',
        replace_existing=True
    )

    scheduler.start()

    # Arrêter proprement le scheduler à la fermeture de l'app
    atexit.register(lambda: scheduler.shutdown())