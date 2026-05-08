from flask import request, jsonify
from datetime import datetime, timezone, timedelta, time
from app.emplois import emplois_bp
from app.models import db, EmploiDuTemps, Session, JourFerie, JournalSecurite, Configuration
from app.auth.decorateurs import role_requis
from flask_login import current_user


def journaliser(type_evenement, description, severite='INFO'):
    """Ajouter une entrée dans le journal de sécurité."""
    entree = JournalSecurite(
        type_evenement=type_evenement,
        description=description,
        severite=severite,
        utilisateur_id=current_user.id if current_user.is_authenticated else None,
        adresse_ip=request.remote_addr
    )
    db.session.add(entree)
    from app.journal.routes import envoyer_alerte
    envoyer_alerte(entree)


# ============================================================
# CAS 1 — Créer un emploi du temps
# ============================================================
@emplois_bp.route('/api/creer', methods=['POST'])
@role_requis('enseignant')
def creer_emploi():
    """
    Créer un emploi du temps pour le semestre.
    Génère automatiquement toutes les sessions
    entre date_debut_validite et date_fin_validite.
    """
    data = request.get_json()

    # Validation des champs obligatoires
    champs_requis = ['nom_cours', 'jour_semaine', 'heure_debut', 'heure_fin',
                     'date_debut_validite', 'date_fin_validite']
    for champ in champs_requis:
        if not data.get(champ):
            return jsonify({'succes': False, 'message': f'{champ} obligatoire'}), 400

    try:
        heure_debut = datetime.strptime(data['heure_debut'], '%H:%M').time()
        heure_fin = datetime.strptime(data['heure_fin'], '%H:%M').time()
        date_debut = datetime.strptime(data['date_debut_validite'], '%Y-%m-%d').date()
        date_fin = datetime.strptime(data['date_fin_validite'], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'succes': False, 'message': 'Format invalide. Heure: HH:MM, Date: YYYY-MM-DD'}), 400

    if heure_fin <= heure_debut:
        return jsonify({'succes': False, 'message': 'heure_fin doit être après heure_debut'}), 400

    if date_fin <= date_debut:
        return jsonify({'succes': False, 'message': 'date_fin_validite doit être après date_debut_validite'}), 400

    # Gestion de la pause
    a_pause = data.get('a_pause', False)
    heure_debut_pause = None
    duree_pause_minutes = None

    if a_pause:
        if not data.get('heure_debut_pause') or not data.get('duree_pause_minutes'):
            return jsonify({'succes': False, 'message': 'heure_debut_pause et duree_pause_minutes obligatoires si a_pause=True'}), 400
        try:
            heure_debut_pause = datetime.strptime(data['heure_debut_pause'], '%H:%M').time()
        except ValueError:
            return jsonify({'succes': False, 'message': 'Format heure_debut_pause invalide. Utiliser HH:MM'}), 400
        duree_pause_minutes = int(data['duree_pause_minutes'])

    # Créer l'emploi du temps
    emploi = EmploiDuTemps(
        #enseignant_id=current_user.id if current_user.is_authenticated else None,
        #enseignant_id='5c39490c-1fdc-4a83-aef1-8300d6b63475',  # ID admin pour test
        enseignant_id=current_user.id if current_user.is_authenticated else None,
        nom_cours=data['nom_cours'],
        groupe=data.get('groupe'),
        salle=data.get('salle'),
        jour_semaine=int(data['jour_semaine']),
        heure_debut=heure_debut,
        heure_fin=heure_fin,
        tolerance_retard_minutes=data.get('tolerance_retard_minutes', 10),
        est_actif=True,
        date_debut_validite=date_debut,
        date_fin_validite=date_fin,
        a_pause=a_pause,
        heure_debut_pause=heure_debut_pause,
        duree_pause_minutes=duree_pause_minutes
    )
    db.session.add(emploi)
    db.session.flush()  # Pour avoir l'ID avant de générer les sessions

    # Générer automatiquement toutes les sessions du semestre
    sessions_creees = _generer_sessions(emploi)

    journaliser('emploi_cree',
                f'Emploi du temps créé : {emploi.nom_cours} — {sessions_creees} sessions générées')
    db.session.commit()

    return jsonify({
        'succes': True,
        'message': f'Emploi du temps créé — {sessions_creees} sessions générées',
        'emploi_id': emploi.id,
        'sessions_creees': sessions_creees
    }), 201


# ============================================================
# CAS 2 — Modifier un emploi du temps
# Modifications appliquées aux sessions FUTURES uniquement
# ============================================================
@emplois_bp.route('/api/<string:emploi_id>/modifier', methods=['PUT'])
@role_requis('enseignant')
def modifier_emploi(emploi_id):
    """
    Modifier un emploi du temps existant.
    Les sessions passées ne sont pas modifiées.
    Les sessions futures sont supprimées et régénérées.
    """
    emploi = EmploiDuTemps.query.get_or_404(emploi_id)

    # Vérifier que c'est bien l'enseignant propriétaire
    if current_user.is_authenticated and emploi.enseignant_id != current_user.id:
        return jsonify({'succes': False, 'message': 'Accès refusé — ce n\'est pas votre emploi du temps'}), 403

    data = request.get_json()
    maintenant = datetime.now(timezone.utc)

    # Mettre à jour les champs modifiés
    if 'nom_cours' in data:
        emploi.nom_cours = data['nom_cours']
    if 'groupe' in data:
        emploi.groupe = data['groupe']
    if 'salle' in data:
        emploi.salle = data['salle']
    if 'tolerance_retard_minutes' in data:
        emploi.tolerance_retard_minutes = data['tolerance_retard_minutes']
    if 'heure_debut' in data:
        emploi.heure_debut = datetime.strptime(data['heure_debut'], '%H:%M').time()
    if 'heure_fin' in data:
        emploi.heure_fin = datetime.strptime(data['heure_fin'], '%H:%M').time()
    if 'date_fin_validite' in data:
        emploi.date_fin_validite = datetime.strptime(data['date_fin_validite'], '%Y-%m-%d').date()
    if 'a_pause' in data:
        emploi.a_pause = data['a_pause']
    if 'heure_debut_pause' in data:
        emploi.heure_debut_pause = datetime.strptime(data['heure_debut_pause'], '%H:%M').time()
    if 'duree_pause_minutes' in data:
        emploi.duree_pause_minutes = data['duree_pause_minutes']

    # Supprimer les sessions FUTURES non commencées
    Session.query.filter(
        Session.emploi_du_temps_id == emploi_id,
        Session.heure_debut > maintenant,
        Session.statut == 'planifiee'
    ).delete()

    # Régénérer les sessions futures
    sessions_creees = _generer_sessions(emploi, depuis_aujourd_hui=True)

    journaliser('emploi_modifie',
                f'Emploi du temps modifié : {emploi.nom_cours} — {sessions_creees} sessions régénérées')
    db.session.commit()

    return jsonify({
        'succes': True,
        'message': f'Emploi du temps modifié — {sessions_creees} sessions régénérées',
        'sessions_creees': sessions_creees
    }), 200


# ============================================================
# CAS 3 — Ajouter une séance exceptionnelle
# ============================================================
@emplois_bp.route('/api/seance-exceptionnelle', methods=['POST'])
@role_requis('enseignant')
def seance_exceptionnelle():
    """
    Ajouter une séance exceptionnelle (rattrapage, cours supplémentaire).
    Cette séance n'est pas liée à l'emploi du temps récurrent.
    """
    data = request.get_json()

    champs_requis = ['nom', 'date', 'heure_debut', 'heure_fin']
    for champ in champs_requis:
        if not data.get(champ):
            return jsonify({'succes': False, 'message': f'{champ} obligatoire'}), 400

    try:
        date_seance = datetime.strptime(data['date'], '%Y-%m-%d').date()
        heure_debut = datetime.strptime(data['heure_debut'], '%H:%M').time()
        heure_fin = datetime.strptime(data['heure_fin'], '%H:%M').time()
    except ValueError:
        return jsonify({'succes': False, 'message': 'Format invalide'}), 400

    if heure_fin <= heure_debut:
        return jsonify({'succes': False, 'message': 'heure_fin doit être après heure_debut'}), 400

    # Vérifier que ce n'est pas un jour férié
    from datetime import date
    jour_ferie = JourFerie.query.filter_by(date=date_seance).first()
    if jour_ferie:
        return jsonify({'succes': False,
                        'message': f'Cette date est un jour férié : {jour_ferie.nom}'}), 400

    session = Session(
        nom=data['nom'],
        lieu=data.get('lieu', ''),
        heure_debut=datetime.combine(date_seance, heure_debut),
        heure_fin=datetime.combine(date_seance, heure_fin),
        tolerance_retard_minutes=data.get('tolerance_retard_minutes', 10),
        type_session='cours',
        statut='planifiee',
        est_exceptionnelle=True,
        cree_par=current_user.id if current_user.is_authenticated else None
    )
    db.session.add(session)

    journaliser('seance_exceptionnelle_creee',
                f'Séance exceptionnelle créée : {data["nom"]} le {date_seance}')
    db.session.commit()

    return jsonify({
        'succes': True,
        'message': 'Séance exceptionnelle créée',
        'session_id': session.id
    }), 201


# ============================================================
# CAS 4 — Suspendre une séance
# ============================================================
@emplois_bp.route('/api/seance/<string:session_id>/suspendre', methods=['PUT'])
@role_requis('enseignant')
def suspendre_seance(session_id):
    """
    Suspendre une séance spécifique.
    La séance est marquée 'annulee' — historique conservé.
    """
    session = Session.query.get_or_404(session_id)

    if session.statut in ['terminee', 'en_cours']:
        return jsonify({'succes': False,
                        'message': 'Impossible de suspendre une session terminée ou en cours'}), 400

    session.statut = 'annulee'

    journaliser('seance_suspendue', f'Séance suspendue : {session.nom}', severite='WARNING')
    db.session.commit()

    return jsonify({'succes': True, 'message': 'Séance suspendue'}), 200


# ============================================================
# CAS 5 — Reprogrammer une séance suspendue
# ============================================================
@emplois_bp.route('/api/seance/<string:session_id>/reprogrammer', methods=['POST'])
@role_requis('enseignant')
def reprogrammer_seance(session_id):
    """
    Reprogrammer une séance suspendue à une nouvelle date.
    Une nouvelle session est créée à la nouvelle date.
    L'ancienne reste 'annulee' en historique.
    """
    session = Session.query.get_or_404(session_id)
    data = request.get_json()

    nouvelle_date_str = data.get('nouvelle_date')
    if not nouvelle_date_str:
        return jsonify({'succes': False, 'message': 'nouvelle_date obligatoire'}), 400

    try:
        nouvelle_date = datetime.strptime(nouvelle_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'succes': False, 'message': 'Format date invalide. Utiliser YYYY-MM-DD'}), 400

    # Vérifier que ce n'est pas un jour férié
    jour_ferie = JourFerie.query.filter_by(date=nouvelle_date).first()
    if jour_ferie:
        return jsonify({'succes': False,
                        'message': f'Cette date est un jour férié : {jour_ferie.nom}'}), 400

    # Calculer les nouvelles heures
    duree = session.heure_fin - session.heure_debut
    nouvelle_heure_debut = datetime.combine(nouvelle_date, session.heure_debut.time()
                                            if hasattr(session.heure_debut, 'time')
                                            else session.heure_debut)
    nouvelle_heure_fin = nouvelle_heure_debut + duree

    # Créer la nouvelle session
    nouvelle_session = Session(
        nom=f"{session.nom} (reprogrammée)",
        lieu=session.lieu,
        heure_debut=nouvelle_heure_debut,
        heure_fin=nouvelle_heure_fin,
        tolerance_retard_minutes=session.tolerance_retard_minutes,
        type_session=session.type_session,
        statut='planifiee',
        emploi_du_temps_id=session.emploi_du_temps_id,
        est_exceptionnelle=True,
        cree_par=current_user.id if current_user.is_authenticated else None
    )
    db.session.add(nouvelle_session)

    # Marquer l'ancienne session comme reprogrammée
    session.reprogrammee_le = nouvelle_heure_debut

    journaliser('seance_reprogrammee',
                f'Séance reprogrammée : {session.nom} → {nouvelle_date}')
    db.session.commit()

    return jsonify({
        'succes': True,
        'message': f'Séance reprogrammée au {nouvelle_date}',
        'nouvelle_session_id': nouvelle_session.id
    }), 201


# ============================================================
# CAS 6 — Suspendre la pause pour une séance spécifique
# ============================================================
@emplois_bp.route('/api/seance/<string:session_id>/suspendre-pause', methods=['PUT'])
@role_requis('enseignant')
def suspendre_pause_seance(session_id):
    """
    Suspendre la pause pour une séance spécifique uniquement.
    Les autres séances gardent leur pause habituelle.
    """
    session = Session.query.get_or_404(session_id)

    if session.statut in ['terminee']:
        return jsonify({'succes': False,
                        'message': 'Impossible de modifier une session terminée'}), 400

    session.pause_suspendue = True

    journaliser('pause_suspendue', f'Pause suspendue pour la séance : {session.nom}')
    db.session.commit()

    return jsonify({'succes': True, 'message': 'Pause suspendue pour cette séance'}), 200


# ============================================================
# GET — Liste des emplois du temps d'un enseignant
# ============================================================
@emplois_bp.route('/api/liste', methods=['GET'])
@role_requis('enseignant')
def liste_emplois():
    """Liste tous les emplois du temps de l'enseignant connecté."""
    emplois = EmploiDuTemps.query.filter_by(
        enseignant_id=current_user.id if current_user.is_authenticated else None
    ).order_by(EmploiDuTemps.cree_le.desc()).all()

    jours = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

    return jsonify({
        'succes': True,
        'emplois': [{
            'id': e.id,
            'nom_cours': e.nom_cours,
            'groupe': e.groupe,
            'salle': e.salle,
            'jour': jours[e.jour_semaine] if 0 <= e.jour_semaine <= 6 else '?',
            'heure_debut': e.heure_debut.strftime('%H:%M'),
            'heure_fin': e.heure_fin.strftime('%H:%M'),
            'est_actif': e.est_actif,
            'date_debut_validite': e.date_debut_validite.isoformat() if e.date_debut_validite else None,
            'date_fin_validite': e.date_fin_validite.isoformat() if e.date_fin_validite else None,
            'a_pause': e.a_pause,
            'heure_debut_pause': e.heure_debut_pause.strftime('%H:%M') if e.heure_debut_pause else None,
            'duree_pause_minutes': e.duree_pause_minutes
        } for e in emplois]
    }), 200


# ============================================================
# GET — Détail d'un emploi du temps
# ============================================================
@emplois_bp.route('/api/<string:emploi_id>', methods=['GET'])
@role_requis('enseignant')
def detail_emploi(emploi_id):
    """Retourne le détail d'un emploi du temps avec ses sessions."""
    emploi = EmploiDuTemps.query.get_or_404(emploi_id)

    sessions = Session.query.filter_by(
        emploi_du_temps_id=emploi_id
    ).order_by(Session.heure_debut).all()

    return jsonify({
        'succes': True,
        'emploi': {
            'id': emploi.id,
            'nom_cours': emploi.nom_cours,
            'groupe': emploi.groupe,
            'salle': emploi.salle,
            'est_actif': emploi.est_actif,
            'a_pause': emploi.a_pause,
            'heure_debut_pause': emploi.heure_debut_pause.strftime('%H:%M') if emploi.heure_debut_pause else None,
            'duree_pause_minutes': emploi.duree_pause_minutes
        },
        'sessions': [{
            'id': s.id,
            'nom': s.nom,
            'heure_debut': s.heure_debut.isoformat(),
            'heure_fin': s.heure_fin.isoformat(),
            'statut': s.statut,
            'pause_suspendue': s.pause_suspendue,
            'est_exceptionnelle': s.est_exceptionnelle
        } for s in sessions]
    }), 200


# ============================================================
# FONCTION INTERNE — Générer les sessions d'un emploi du temps
# ============================================================
def _generer_sessions(emploi, depuis_aujourd_hui=False):
    """
    Génère toutes les sessions d'un emploi du temps
    en sautant les jours fériés.

    Args:
        emploi: instance EmploiDuTemps
        depuis_aujourd_hui: si True, génère seulement les sessions futures

    Returns:
        Nombre de sessions créées
    """
    from datetime import date, timedelta

    # Récupérer les jours fériés sur la période
    jours_feries = {
        jf.date for jf in JourFerie.query.filter(
            JourFerie.date >= emploi.date_debut_validite,
            JourFerie.date <= emploi.date_fin_validite
        ).all()
    }

    # Déterminer la date de départ
    if depuis_aujourd_hui:
        date_depart = date.today()
    else:
        date_depart = emploi.date_debut_validite

    sessions_creees = 0
    date_courante = date_depart

    while date_courante <= emploi.date_fin_validite:
        # Vérifier que c'est le bon jour de la semaine
        if date_courante.weekday() == emploi.jour_semaine:
            # Vérifier que ce n'est pas un jour férié
            if date_courante not in jours_feries:
                debut = datetime.combine(date_courante, emploi.heure_debut)
                fin = datetime.combine(date_courante, emploi.heure_fin)

                # Vérifier qu'une session n'existe pas déjà
                existante = Session.query.filter_by(
                    emploi_du_temps_id=emploi.id,
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
                        emploi_du_temps_id=emploi.id,
                        est_exceptionnelle=False,
                        pause_suspendue=False
                    )
                    db.session.add(session)
                    sessions_creees += 1

        date_courante += timedelta(days=1)


    return sessions_creees

from flask import render_template

@emplois_bp.route('/')
@role_requis('enseignant')
def liste():
    from app.models import Configuration
    config = Configuration.get_config()
    mode = config.mode if config else 'ecole'
    emplois = EmploiDuTemps.query.filter_by(
        enseignant_id=current_user.id
    ).order_by(EmploiDuTemps.cree_le.desc()).all()
    return render_template('emplois/liste.html', emplois=emplois, mode=mode)