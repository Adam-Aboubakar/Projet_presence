from flask import request, jsonify
from datetime import datetime, timezone, timedelta
from app.sessions import sessions_bp
from app.models import db, Session, Presence, Personne, EmploiDuTemps, JourFerie, JournalSecurite, CarteRFID
from app.auth.decorateurs import role_requis
from flask_login import current_user


def journaliser(type_evenement, description, severite='INFO', personne_id=None):
    entree = JournalSecurite(
        type_evenement=type_evenement,
        description=description,
        severite=severite,
        utilisateur_id=current_user.id if current_user.is_authenticated else None,
        personne_id=personne_id,
        adresse_ip=request.remote_addr
    )
    db.session.add(entree)

    # Envoyer alerte email si WARNING ou CRITIQUE
    from app.journal.routes import envoyer_alerte
    envoyer_alerte(entree)


# ============================================================
# CAS 1 — Créer une session manuellement (mode école)
# ============================================================
@sessions_bp.route('/api/creer', methods=['POST'])
@role_requis('enseignant')
def creer_session():
    data = request.get_json()

    nom = data.get('nom', '').strip()
    lieu = data.get('lieu', '').strip()
    heure_debut = data.get('heure_debut')
    heure_fin = data.get('heure_fin')
    tolerance = data.get('tolerance_retard_minutes', 10)

    if not nom or not heure_debut or not heure_fin:
        return jsonify({'succes': False, 'message': 'nom, heure_debut et heure_fin obligatoires'}), 400

    try:
        debut = datetime.fromisoformat(heure_debut)
        fin = datetime.fromisoformat(heure_fin)
    except ValueError:
        return jsonify({'succes': False, 'message': 'Format datetime invalide. Utiliser ISO 8601'}), 400

    if fin <= debut:
        return jsonify({'succes': False, 'message': 'heure_fin doit être après heure_debut'}), 400

    session = Session(
        nom=nom,
        lieu=lieu,
        heure_debut=debut,
        heure_fin=fin,
        tolerance_retard_minutes=tolerance,
        type_session='cours',
        statut='planifiee',
       # cree_par=current_user.id
       cree_par=current_user.id if current_user.is_authenticated else None
    )
    db.session.add(session)

    journaliser('session_creee', f'Session créée : {nom}')
    db.session.commit()

    return jsonify({
        'succes': True,
        'message': 'Session créée avec succès',
        'session_id': session.id
    }), 201


# ============================================================
# CAS 2 — Générer sessions depuis emploi du temps (mode école)
# ============================================================
@sessions_bp.route('/api/generer', methods=['POST'])
@role_requis('enseignant')
def generer_sessions():
    """
    Génère toutes les sessions d'un emploi du temps
    entre date_debut et date_fin en sautant les jours fériés.
    """
    data = request.get_json()
    emploi_id = data.get('emploi_id')

    emploi = EmploiDuTemps.query.get_or_404(emploi_id)

    # Vérifier que l'enseignant est bien le propriétaire
    if emploi.enseignant_id != current_user.id:
        return jsonify({'succes': False, 'message': 'Accès refusé'}), 403

    if not emploi.date_debut_validite or not emploi.date_fin_validite:
        return jsonify({'succes': False, 'message': 'Dates de validité manquantes dans l\'emploi du temps'}), 400

    # Récupérer les jours fériés
    jours_feries = {
        jf.date for jf in JourFerie.query.filter(
            JourFerie.date >= emploi.date_debut_validite,
            JourFerie.date <= emploi.date_fin_validite
        ).all()
    }

    from datetime import date, timedelta
    sessions_creees = 0
    date_courante = emploi.date_debut_validite

    while date_courante <= emploi.date_fin_validite:
        # Vérifier que c'est le bon jour de la semaine
        if date_courante.weekday() == emploi.jour_semaine:
            # Vérifier que ce n'est pas un jour férié
            if date_courante not in jours_feries:
                debut = datetime.combine(date_courante, emploi.heure_debut)
                fin = datetime.combine(date_courante, emploi.heure_fin)

                # Vérifier qu'une session n'existe pas déjà
                existante = Session.query.filter_by(
                    nom=emploi.nom_cours,
                    heure_debut=debut
                ).first()

                if not existante:
                    session = Session(
                        nom=f"{emploi.nom_cours} — {emploi.groupe or 'Tous'}",
                        lieu=emploi.salle,
                        heure_debut=debut,
                        heure_fin=fin,
                        tolerance_retard_minutes=emploi.tolerance_retard_minutes,
                        type_session='cours',
                        statut='planifiee',
                        cree_par=current_user.id if current_user.is_authenticated else None,
                        emploi_du_temps_id=emploi.id
                    )
                    db.session.add(session)
                    sessions_creees += 1

        date_courante += timedelta(days=1)

    journaliser('sessions_generees',
                f'{sessions_creees} sessions générées depuis emploi du temps {emploi.nom_cours}')
    db.session.commit()

    return jsonify({
        'succes': True,
        'message': f'{sessions_creees} sessions générées avec succès',
        'sessions_creees': sessions_creees
    }), 201


# ============================================================
# CAS 3 — Ouvrir une session
# ============================================================
@sessions_bp.route('/api/<string:session_id>/ouvrir', methods=['PUT'])
@role_requis('enseignant')
def ouvrir_session(session_id):
    session = Session.query.get_or_404(session_id)

    if session.statut == 'en_cours':
        return jsonify({'succes': False, 'message': 'Session déjà ouverte'}), 400
    if session.statut == 'terminee':
        return jsonify({'succes': False, 'message': 'Session déjà terminée'}), 400
    if session.statut == 'annulee':
        return jsonify({'succes': False, 'message': 'Session annulée'}), 400

    session.statut = 'en_cours'

    journaliser('session_ouverte', f'Session ouverte : {session.nom}')
    db.session.commit()

    return jsonify({'succes': True, 'message': 'Session ouverte — pointages acceptés'}), 200


# ============================================================
# CAS 4 — Fermer une session + marquer absents
# ============================================================
@sessions_bp.route('/api/<string:session_id>/fermer', methods=['PUT'])
@role_requis('enseignant')
def fermer_session(session_id):
    session = Session.query.get_or_404(session_id)

    if session.statut != 'en_cours':
        return jsonify({'succes': False, 'message': 'La session doit être en cours pour être fermée'}), 400

    session.statut = 'terminee'

    personnes_ayant_pointe = {
        p.personne_id for p in Presence.query.filter_by(session_id=session_id).all()
        if p.statut in ['present', 'retard']
    }

    # APRÈS
    # Filtrer par département, niveau, groupe selon l'emploi du temps
    departement = None
    niveau = None
    groupe = None

    if session.emploi_du_temps_id:
        from app.models import EmploiDuTemps
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
    absents_count = 0

    for personne in toutes_personnes:
        if personne.id not in personnes_ayant_pointe:
            absence = Presence(
                personne_id=personne.id,
                session_id=session_id,
                statut='absent',
                methode_validation='automatique',
                horodatage=datetime.now(timezone.utc)
            )
            db.session.add(absence)
            absents_count += 1

            # Email absence immédiat
            if personne.email:
                try:
                    from app.auth.email import envoyer_email
                    from flask import current_app
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
                                <td style="padding:10px; border:1px solid #dee2e6;">{session.heure_debut.strftime('%d/%m/%Y %H:%M')}</td>
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
                    current_app.logger.error(f"Erreur email absence : {str(e)}")

            # Vérifier seuils conseil de discipline
            _verifier_seuils_absences(personne.id)

    journaliser('session_fermee',
                f'Session fermée : {session.nom} — {absents_count} absents marqués')
    db.session.commit()

    return jsonify({
        'succes': True,
        'message': f'Session fermée — {absents_count} absents marqués automatiquement'
    }), 200
# ============================================================
# CAS 5 — Annuler une session
# ============================================================
@sessions_bp.route('/api/<string:session_id>/annuler', methods=['PUT'])
@role_requis('enseignant')
def annuler_session(session_id):
    session = Session.query.get_or_404(session_id)

    if session.statut == 'terminee':
        return jsonify({'succes': False, 'message': 'Impossible d\'annuler une session terminée'}), 400
    if session.statut == 'en_cours':
        return jsonify({'succes': False, 'message': 'Fermez d\'abord la session avant de l\'annuler'}), 400

    session.statut = 'annulee'
    journaliser('session_annulee', f'Session annulée : {session.nom}', severite='WARNING')
    db.session.commit()

    return jsonify({'succes': True, 'message': 'Session annulée'}), 200


# ============================================================
# GET — Liste des sessions
# ============================================================
@sessions_bp.route('/api/liste', methods=['GET'])
@role_requis('enseignant')
def liste_sessions():
    statut = request.args.get('statut')
    query = Session.query

    if statut:
        query = query.filter_by(statut=statut)

    sessions = query.order_by(Session.heure_debut.desc()).limit(50).all()

    return jsonify({
        'succes': True,
        'sessions': [{
            'id': s.id,
            'nom': s.nom,
            'lieu': s.lieu,
            'heure_debut': s.heure_debut.isoformat(),
            'heure_fin': s.heure_fin.isoformat(),
            'statut': s.statut,
            'tolerance_retard_minutes': s.tolerance_retard_minutes,
            'type_session': s.type_session
        } for s in sessions]
    }), 200


# ============================================================
# FONCTION INTERNE — Vérifier seuils absences
# ============================================================
def _verifier_seuils_absences(personne_id):
    """
    Vérifie si la personne a atteint un seuil d'absences
    et déclenche l'action correspondante.
    """
    from app.models import SeuilAbsence
    from app.auth.email import envoyer_email

    # Compter les absences injustifiées
    nb_absences = Presence.query.filter_by(
        personne_id=personne_id,
        statut='absent',
        justification_absence=None
    ).count()

    # Récupérer les seuils actifs triés par niveau
    seuils = SeuilAbsence.query.filter_by(est_actif=True)\
        .order_by(SeuilAbsence.niveau.desc()).all()

    personne = Personne.query.get(personne_id)
    if not personne:
        return

    for seuil in seuils:
        if nb_absences >= seuil.nb_absences:
            # Envoyer email
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
                except Exception:
                    pass

            journaliser(
                'seuil_absence_atteint',
                f'{personne.prenom} {personne.nom} — {nb_absences} absences — niveau {seuil.niveau} — action: {seuil.action}',
                severite='WARNING',
                personne_id=personne_id
            )
            break  # Un seul seuil déclenché à la fois

from flask import render_template, redirect, url_for, flash

# ── PAGES WEB ────────────────────────────────────────────────

@sessions_bp.route('/')
@role_requis('enseignant')
def liste():
    from app.models import Configuration
    config = Configuration.get_config()
    mode = config.mode if config else 'ecole'

    emploi_id = request.args.get('emploi')
    emploi_filtre = None

    if emploi_id:
        emploi_filtre = EmploiDuTemps.query.filter_by(
            id=emploi_id,
            enseignant_id=current_user.id
        ).first_or_404()
        sessions = Session.query.filter_by(
            emploi_du_temps_id=emploi_filtre.id
        ).order_by(Session.heure_debut.desc()).limit(100).all()
    else:
        sessions = Session.query.filter(
            db.or_(
                Session.cree_par == current_user.id,
                Session.emploi_du_temps_id.in_(
                    db.session.query(EmploiDuTemps.id).filter_by(enseignant_id=current_user.id)
                )
            )
        ).order_by(Session.heure_debut.desc()).limit(100).all()

    return render_template('sessions/liste.html',
        sessions=sessions,
        mode=mode,
        emploi_filtre=emploi_filtre
    )

@sessions_bp.route('/api/session-active', methods=['GET'])
def session_active():
    """Route publique pour l'écran de pointage."""
    from datetime import datetime, timezone
    maintenant = datetime.now(timezone.utc)

    salle = request.args.get('salle')

    query = Session.query.filter_by(statut='en_cours').filter(
        Session.heure_debut <= maintenant,
        Session.heure_fin >= maintenant
    )

    if salle:
        query = query.filter(Session.lieu == salle)

    seance = query.first()

    if not seance:
        return jsonify({'session': None}), 200

    return jsonify({
        'session': {
            'id': seance.id,
            'nom': seance.nom,
            'lieu': seance.lieu or 'N/A',
            'heure_debut': seance.heure_debut.isoformat(),
            'heure_fin': seance.heure_fin.isoformat(),
            'statut': seance.statut
        }
    }), 200


@sessions_bp.route('/api/verifier-rfid', methods=['POST'])
def verifier_rfid():
    """Vérifie si une carte RFID a déjà pointé pour la session en cours."""
    from app.utils.chiffrement import dechiffrer_texte
    from datetime import datetime, timezone
    
    data = request.get_json()
    numero_rfid = data.get('numero_rfid', '').strip().upper()
    
    if not numero_rfid:
        return jsonify({'succes': False, 'message': 'RFID manquant'}), 400
    
    # Trouver la personne
    personne = None
    cartes_actives = CarteRFID.query.filter_by(statut='actif').all()
    for carte in cartes_actives:
        try:
            if dechiffrer_texte(carte.numero_rfid) == numero_rfid:
                personne = Personne.query.get(carte.personne_id)
                break
        except:
            continue
    
    if not personne:
        return jsonify({'succes': False, 'statut': 'carte_inconnue', 'message': 'Carte inconnue'}), 403
    
    # Trouver session en cours
    maintenant = datetime.now(timezone.utc)
    seance = Session.query.filter_by(statut='en_cours').filter(
        Session.heure_debut <= maintenant,
        Session.heure_fin >= maintenant
    ).first()
    
    if not seance:
        return jsonify({'succes': False, 'statut': 'pas_de_session', 'message': 'Aucune session en cours'}), 404
    
    # Vérifier doublon
    presence_existante = Presence.query.filter_by(
        personne_id=personne.id,
        session_id=seance.id
    ).filter(Presence.statut.in_(['present', 'retard'])).first()
    
    if presence_existante:
        return jsonify({
            'succes': False,
            'statut': 'deja_pointe',
            'personne': f'{personne.prenom} {personne.nom}',
            'message': 'Déjà enregistré pour cette session'
        }), 200
    
    return jsonify({
        'succes': True,
        'statut': 'ok',
        'personne': f'{personne.prenom} {personne.nom}',
        'message': 'Carte valide — procéder à la reconnaissance faciale'
    }), 200
@sessions_bp.route('/<string:session_id>')
@role_requis('enseignant')
def detail(session_id):
    from app.models import Configuration
    config = Configuration.get_config()
    mode = config.mode if config else 'ecole'
    seance = Session.query.get_or_404(session_id)
    presences = Presence.query.filter_by(session_id=session_id)\
        .order_by(Presence.horodatage).all()

    presences_detail = []
    for p in presences:
        personne = Personne.query.get(p.personne_id)
        presences_detail.append({
            'presence': p,
            'personne': personne
        })

    total = len(presences)
    presents = sum(1 for p in presences if p.statut == 'present')
    retards  = sum(1 for p in presences if p.statut == 'retard')
    absents  = sum(1 for p in presences if p.statut == 'absent')

    groupe = None
    if seance.emploi_du_temps_id:
        emploi = EmploiDuTemps.query.get(seance.emploi_du_temps_id)
        if emploi:
            groupe = emploi.groupe

    return render_template('sessions/detail.html',
        session=seance,
        presences_detail=presences_detail,
        total=total, presents=presents,
        retards=retards, absents=absents,
        mode=mode,
        groupe=groupe
    )