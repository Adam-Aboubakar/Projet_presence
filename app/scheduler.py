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


def fermer_sessions_terminees():
    from app import db
    from app.models import Session, Presence, Personne, EmploiDuTemps
    from app.auth.email import envoyer_email

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

                    if personne.email:
                        try:
                            date_str = session.heure_debut.strftime('%d/%m/%Y %H:%M') if session.heure_debut else '—'
                            corps_html = f"""
                            <div style="font-family:Arial,sans-serif; max-width:600px; margin:0 auto;">
                                <h2 style="color:#e74c3c;">Absence enregistree</h2>
                                <p>Bonjour <strong>{personne.prenom} {personne.nom}</strong>,</p>
                                <p>Une absence a ete enregistree pour la session suivante :</p>
                                <table style="width:100%; border-collapse:collapse; margin:20px 0;">
                                    <tr style="background:#f8f9fa;">
                                        <td style="padding:10px; border:1px solid #dee2e6;"><strong>Session</strong></td>
                                        <td style="padding:10px; border:1px solid #dee2e6;">{session.nom}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding:10px; border:1px solid #dee2e6;"><strong>Date</strong></td>
                                        <td style="padding:10px; border:1px solid #dee2e6;">{date_str}</td>
                                    </tr>
                                </table>
                                <p style="color:#7f8c8d; font-size:13px;">
                                    Si vous pensez qu il s agit d une erreur, contactez votre responsable.
                                </p>
                                <hr style="border:none; border-top:1px solid #ecf0f1; margin:20px 0;">
                                <p style="color:#95a5a6; font-size:12px; text-align:center;">
                                    Systeme de Gestion de Presence — Email automatique, ne pas repondre.
                                </p>
                            </div>
                            """
                            envoyer_email(
                                destinataire=personne.email,
                                sujet=f"Absence enregistree — {session.nom}",
                                corps_html=corps_html
                            )
                            print(f"[SCHEDULER] Email envoye a {personne.email}")
                        except Exception as e:
                            logging.error(f"[SCHEDULER] Erreur email : {str(e)}")

            db.session.commit()
            print(f"[SCHEDULER] Session {session.nom} traitee")


def init_scheduler(app):
    # En debug mode Flask recharge deux fois — on lance le scheduler
    # uniquement dans le processus principal (WERKZEUG_RUN_MAIN=true)
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

    # Exécuter immédiatement au démarrage pour rattraper les sessions manquées
    with app.app_context():
        ouvrir_sessions_prevues()
        fermer_sessions_terminees()

    atexit.register(lambda: scheduler.shutdown())