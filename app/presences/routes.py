from flask import request, jsonify
from datetime import datetime, timezone, timedelta
from app.presences import presences_bp
from app.models import db, Presence, Session, Personne, CarteRFID, JournalSecurite
from app.utils.chiffrement import dechiffrer_texte
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
# CAS 1 — Pointage RFID (Raspberry Pi — Semaine 3)
# ============================================================
@presences_bp.route('/api/pointer', methods=['POST'])
def pointer():
    """
    Reçoit le numéro RFID du Raspberry Pi.
    Trouve la personne, vérifie la session en cours,
    et enregistre la présence.
    """
    data = request.get_json()
    numero_rfid = data.get('numero_rfid', '').strip().upper()

    if not numero_rfid:
        return jsonify({'succes': False, 'message': 'Numéro RFID manquant'}), 400

    # Étape 1 — Trouver la carte RFID
    personne = None
    cartes_actives = CarteRFID.query.filter_by(statut='actif').all()
    for carte in cartes_actives:
        try:
            if dechiffrer_texte(carte.numero_rfid) == numero_rfid:
                personne = Personne.query.get(carte.personne_id)
                carte_trouvee = carte
                break
        except Exception:
            continue

    if not personne:
        journaliser('pointage_carte_inconnue',
                    f'Tentative pointage carte inconnue', severite='CRITIQUE')
        db.session.commit()
        return jsonify({'succes': False, 'message': 'Carte inconnue'}), 403

    if not personne.est_actif:
        return jsonify({'succes': False, 'message': 'Personne inactive'}), 403

    # Étape 2 — Trouver une session en cours
    maintenant = datetime.now(timezone.utc)
    session = Session.query.filter_by(statut='en_cours').filter(
        Session.heure_debut <= maintenant,
        Session.heure_fin >= maintenant
    ).first()

    if not session:
        return jsonify({'succes': False, 'message': 'Aucune session en cours'}), 404

    # Étape 3 — Vérifier doublon
    presence_existante = Presence.query.filter_by(
        personne_id=personne.id,
        session_id=session.id
    ).filter(Presence.statut.in_(['present', 'retard'])).first()

    if presence_existante:
        return jsonify({
            'succes': False,
            'message': f'{personne.prenom} {personne.nom} a déjà pointé pour cette session'
        }), 400

    # Étape 4 — Déterminer statut (présent ou retard)
    heure_limite = session.heure_debut + timedelta(minutes=session.tolerance_retard_minutes)
    statut = 'present' if maintenant <= heure_limite else 'retard'

    # Étape 5 — Enregistrer la présence
    presence = Presence(
        personne_id=personne.id,
        session_id=session.id,
        carte_rfid_id=carte_trouvee.id,
        horodatage=maintenant,
        statut=statut,
        methode_validation='rfid'
    )
    db.session.add(presence)

    journaliser(
        'pointage_effectue',
        f'{personne.prenom} {personne.nom} — statut: {statut}',
        personne_id=personne.id
    )
    db.session.commit()

    return jsonify({
        'succes': True,
        'nom': personne.nom_complet(),
        'statut': statut,
        'message': f'Pointage enregistré — {statut.upper()}'
    }), 201


# ============================================================
# CAS 2 — Modifier manuellement une présence
# ============================================================
@presences_bp.route('/api/<string:presence_id>/modifier', methods=['PUT'])
@role_requis('enseignant')
def modifier_presence(presence_id):
    presence = Presence.query.get_or_404(presence_id)
    data = request.get_json()

    nouveau_statut = data.get('statut', '').strip()
    justification = data.get('justification', '').strip()

    if nouveau_statut not in ['present', 'retard', 'absent']:
        return jsonify({
            'succes': False,
            'message': 'Statut invalide. Valeurs: present, retard, absent'
        }), 400

    if not justification:
        return jsonify({
            'succes': False,
            'message': 'Justification obligatoire pour toute modification manuelle'
        }), 400

    ancien_statut = presence.statut
    presence.statut = nouveau_statut
    presence.modifie_par = current_user.id
    presence.modifie_le = datetime.now(timezone.utc)
    presence.justification_modification = justification
    presence.methode_validation = 'manuel'

    journaliser(
        'presence_modifiee',
        f'Présence modifiée : {ancien_statut} → {nouveau_statut} — justification: {justification}',
        severite='WARNING',
        personne_id=presence.personne_id
    )
    db.session.commit()

    return jsonify({'succes': True, 'message': 'Présence modifiée avec succès'}), 200


# ============================================================
# GET — Liste des présences d'une session
# ============================================================
@presences_bp.route('/api/<string:session_id>/liste', methods=['GET'])
@role_requis('enseignant')
def liste_presences(session_id):
    Session.query.get_or_404(session_id)
    presences = Presence.query.filter_by(session_id=session_id)\
        .order_by(Presence.horodatage).all()

    return jsonify({
        'succes': True,
        'presences': [{
            'id': p.id,
            'personne_id': p.personne_id,
            'statut': p.statut,
            'horodatage': p.horodatage.isoformat() if p.horodatage else None,
            'methode_validation': p.methode_validation,
            'justification_modification': p.justification_modification
        } for p in presences]
    }), 200


# ============================================================
# GET — Historique des présences d'une personne
# ============================================================
@presences_bp.route('/api/personne/<string:personne_id>', methods=['GET'])
@role_requis('enseignant')
def historique_personne(personne_id):
    Personne.query.get_or_404(personne_id)
    presences = Presence.query.filter_by(personne_id=personne_id)\
        .order_by(Presence.horodatage.desc()).limit(50).all()

    # Calculer les statistiques
    total = len(presences)
    presents = sum(1 for p in presences if p.statut == 'present')
    retards = sum(1 for p in presences if p.statut == 'retard')
    absents = sum(1 for p in presences if p.statut == 'absent')

    return jsonify({
        'succes': True,
        'statistiques': {
            'total': total,
            'presents': presents,
            'retards': retards,
            'absents': absents,
            'taux_presence': round((presents + retards) / total * 100, 1) if total > 0 else 0
        },
        'presences': [{
            'id': p.id,
            'session_id': p.session_id,
            'statut': p.statut,
            'horodatage': p.horodatage.isoformat() if p.horodatage else None,
        } for p in presences]
    }), 200

from flask import render_template

@presences_bp.route('/')
@role_requis('enseignant')
def liste():
    from app.models import Configuration
    config = Configuration.get_config()
    mode = config.mode if config else 'ecole'
    
    # Sessions terminées et en cours avec leurs stats
    sessions = Session.query.filter(
        Session.statut.in_(['terminee', 'en_cours'])
    ).order_by(Session.heure_debut.desc()).limit(50).all()
    
    sessions_avec_stats = []
    for s in sessions:
        presences = Presence.query.filter_by(session_id=s.id).all()
        total = len(presences)
        presents = sum(1 for p in presences if p.statut == 'present')
        retards = sum(1 for p in presences if p.statut == 'retard')
        absents = sum(1 for p in presences if p.statut == 'absent')
        sessions_avec_stats.append({
            'session': s,
            'total': total,
            'presents': presents,
            'retards': retards,
            'absents': absents,
            'taux': round((presents + retards) / total * 100) if total > 0 else 0
        })
    
    return render_template('presences/liste.html',
        sessions_avec_stats=sessions_avec_stats, mode=mode)


@presences_bp.route('/session/<string:session_id>')
@role_requis('enseignant')
def detail_session(session_id):
    from app.models import Configuration
    config = Configuration.get_config()
    mode = config.mode if config else 'ecole'
    
    session = Session.query.get_or_404(session_id)
    presences = Presence.query.filter_by(session_id=session_id)\
        .order_by(Presence.horodatage).all()
    
    presences_detail = []
    for p in presences:
        personne = Personne.query.get(p.personne_id)
        presences_detail.append({'presence': p, 'personne': personne})
    
    total = len(presences)
    presents = sum(1 for p in presences if p.statut == 'present')
    retards = sum(1 for p in presences if p.statut == 'retard')
    absents = sum(1 for p in presences if p.statut == 'absent')
    
    return render_template('presences/detail_session.html',
        session=session,
        presences_detail=presences_detail,
        total=total, presents=presents,
        retards=retards, absents=absents,
        mode=mode)

