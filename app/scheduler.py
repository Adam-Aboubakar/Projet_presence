from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit
from app.models import Session, Presence, Personne, EmploiDuTemps

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
    from app.auth.email import envoyer_email
    from datetime import datetime, timezone
    import logging

    with scheduler.app.app_context():
        maintenant = datetime.now(timezone.utc)

        sessions_a_fermer = Session.query.filter(
            Session.statut == 'en_cours',
            Session.heure_fin < maintenant
        ).all()

        for session in sessions_a_fermer:
            session.statut = 'terminee'

            personnes_ayant_pointe = {
                p.personne_id for p in Presence.query.filter_by(
                    session_id=session.id
                ).filter(Presence.statut.in_(['present', 'retard'])).all()
            }

            # APRÈS
            departement = None
            niveau = None
            groupe = None

            if session.emploi_du_temps_id:
                emploi = EmploiDuTemps.query.get(session.emploi_du_temps_id)
                if emploi:
                    departement = emploi.departement
                    niveau = emploi.niveau
                    groupe = emploi.groupe

            query = Personne.query.filter_by(est_actif=True)
            if departement:
                query = query.filter_by(departement=departement)
            if niveau:
                query = query.filter_by(niveau_ou_poste=niveau)
            if groupe:
                query = query.filter_by(groupe_ou_site=groupe)

            toutes_personnes = query.all()

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

                    # Email absence immédiat
                    if personne.email:
                        try:
                            corps_html = f"""
                            <div style="font-family:Arial,sans-serif; max-width:600px; margin:0 auto;">
                                <h2 style="color:#e74c3c;">⚠️ Absence enregistrée</h2>
                                <p>Bonjour <strong>{personne.prenom} {personne.nom}</strong>,</p>
                                <p>Une absence a été enregistrée pour la session suivante :</p>
                                <table style="width:100%; border-collapse:collapse; margin:20px 0;">
                                    <tr style="background:#f8f9fa;">
                                        <td style="padding:10px; border:1px solid #dee2e6;"><strong>Session</strong></td>
                                        <td style="padding:10px; border:1px solid #dee2e6;">{session.nom}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding:10px; border:1px solid #dee2e6;"><strong>Date</strong></td>
                                        <td style="padding:10px; border:1px solid #dee2e6;">{session.heure_debut.strftime('%d/%m/%Y %H:%M') if session.heure_debut else '—'}</td>
                                    </tr>
                                </table>
                                <p style="color:#7f8c8d; font-size:13px;">
                                    Si vous pensez qu'il s'agit d'une erreur, contactez votre responsable.
                                </p>
                                <hr style="border:none; border-top:1px solid #ecf0f1; margin:20px 0;">
                                <p style="color:#95a5a6; font-size:12px; text-align:center;">
                                    Système de Gestion de Présence — Email automatique, ne pas répondre.
                                </p>
                            </div>
                            """
                            envoyer_email(
                                destinataire=personne.email,
                                sujet=f"Absence enregistrée — {session.nom}",
                                corps_html=corps_html
                            )
                        except Exception as e:
                            logging.error(f"Erreur email absence scheduler : {str(e)}")

            db.session.commit()

def init_scheduler(app):
    """Initialiser et démarrer le scheduler."""
    scheduler.app = app

    scheduler.add_job(
        func=ouvrir_sessions_prevues,
        trigger=IntervalTrigger(minutes=1),
        id='ouvrir_sessions',
        name='Ouvrir sessions planifiées',
        replace_existing=True
    )

    scheduler.add_job(
        func=fermer_sessions_terminees,
        trigger=IntervalTrigger(minutes=1),
        id='fermer_sessions',
        name='Fermer sessions terminées',
        replace_existing=True
    )

    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())            