from flask import request, jsonify, render_template
from datetime import datetime, timezone, timedelta
from app.presences import presences_bp
from app.models import db, Presence, Session, Personne, CarteRFID, JournalSecurite, Photo, Configuration
from app.utils.chiffrement import dechiffrer_texte
from app.auth.decorateurs import role_requis
from flask_login import current_user
from app import csrf


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
    from app.journal.routes import envoyer_alerte
    envoyer_alerte(entree)


# ============================================================
# CAS 1 — Pointage RFID + Reconnaissance faciale (Raspberry Pi)
# ============================================================
@presences_bp.route('/api/pointer', methods=['POST'])
@csrf.exempt
def pointer():
    import base64
    import tempfile
    import os
    from deepface import DeepFace
    from app.utils.chiffrement import dechiffrer_fichier
    import cv2 as cv2_local

    data = request.get_json(force=True, silent=True) or {}
    numero_rfid = (data.get('numero_rfid') or '').strip().upper()
    photo_base64 = data.get('photo', None)

    if not numero_rfid:
        return jsonify({'succes': False, 'message': 'Numéro RFID manquant'}), 400

    # Étape 1 — Trouver la carte RFID
    personne = None
    carte_trouvee = None
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
                    'Tentative pointage carte inconnue', severite='CRITIQUE')
        db.session.commit()
        return jsonify({'succes': False, 'message': 'Carte inconnue'}), 403

    if not personne.est_actif:
        return jsonify({'succes': False, 'message': 'Personne inactive'}), 403

    # Étape 2 — Vérification DeepFace
    if photo_base64:
        photo_principale = Photo.query.filter_by(
            personne_id=personne.id,
            est_principale=True
        ).first()

        if not photo_principale:
            return jsonify({
                'succes': False,
                'message': 'Aucune photo de référence enregistrée'
            }), 403

        try:
            chemin_complet = os.path.join('app', 'static', photo_principale.chemin_fichier)
            with open(chemin_complet, 'rb') as f:
                donnees_chiffrees = f.read()
            photo_dechiffree = dechiffrer_fichier(donnees_chiffrees)

            chemin_ref = os.path.join(tempfile.gettempdir(), 'ref_photo.jpg')
            with open(chemin_ref, 'wb') as f_ref:
                f_ref.write(photo_dechiffree)

            photo_b64_clean = photo_base64.strip().replace('\n', '').replace('\r', '').replace(' ', '')
            photo_b64_padded = photo_b64_clean + '=' * (4 - len(photo_b64_clean) % 4)
            photo_bytes = base64.b64decode(photo_b64_padded)
            chemin_live = os.path.join(tempfile.gettempdir(), 'live_photo.jpg')
            with open(chemin_live, 'wb') as f_live:
                f_live.write(photo_bytes)

            cascade = cv2_local.CascadeClassifier(
                cv2_local.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            img_check = cv2_local.imread(chemin_live)
            gris = cv2_local.cvtColor(img_check, cv2_local.COLOR_BGR2GRAY)
            visages = cascade.detectMultiScale(gris, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))

            if len(visages) == 0:
                os.unlink(chemin_ref)
                os.unlink(chemin_live)
                return jsonify({
                    'succes': False,
                    'statut': 'pas_de_visage',
                    'message': 'Aucun visage detecte — regardez la camera'
                }), 400

            config = Configuration.get_config()
            seuil = config.seuil_similarite if config else 0.40

            result = DeepFace.verify(
                img1_path=chemin_live,
                img2_path=chemin_ref,
                enforce_detection=False,
                anti_spoofing=True
            )

            os.unlink(chemin_ref)
            os.unlink(chemin_live)

            if not result['verified'] or result['distance'] > seuil:
                journaliser(
                    'pointage_visage_refuse',
                    f'Visage non reconnu pour {personne.prenom} {personne.nom} — distance: {result["distance"]:.3f}',
                    severite='INFO',
                    personne_id=personne.id
                )
                db.session.commit()
                return jsonify({
                    'succes': False,
                    'message': 'Visage non reconnu — tentative de fraude possible'
                }), 403

        except Exception as e:
            return jsonify({
                'succes': False,
                'message': f'Erreur reconnaissance faciale : {str(e)}'
            }), 500

    # Étape 3 — Session en cours
    maintenant = datetime.now(timezone.utc)
    seance = Session.query.filter_by(statut='en_cours').filter(
        Session.heure_debut <= maintenant,
        Session.heure_fin >= maintenant
    ).first()

    if not seance:
        return jsonify({'succes': False, 'message': 'Aucune session en cours'}), 404

    # Étape 4 — Doublon
    presence_existante = Presence.query.filter_by(
        personne_id=personne.id,
        session_id=seance.id
    ).filter(Presence.statut.in_(['present', 'retard'])).first()

    if presence_existante:
        return jsonify({
            'succes': False,
            'message': f'{personne.prenom} {personne.nom} a déjà pointé pour cette session'
        }), 400

    # Étape 5 — Statut présent / retard
    heure_limite = seance.heure_debut + timedelta(minutes=seance.tolerance_retard_minutes)
    if heure_limite.tzinfo is None:
        from datetime import timezone as tz
        heure_limite = heure_limite.replace(tzinfo=tz.utc)
    statut = 'present' if maintenant <= heure_limite else 'retard'

    # Étape 6 — Enregistrer
    presence = Presence(
        personne_id=personne.id,
        session_id=seance.id,
        carte_rfid_id=carte_trouvee.id,
        statut=statut,
        methode_validation='rfid_visage' if photo_base64 else 'rfid',
        horodatage=maintenant
    )
    db.session.add(presence)

    journaliser(
        'pointage_valide',
        f'{personne.prenom} {personne.nom} — {statut} — session: {seance.nom}',
        personne_id=personne.id
    )
    db.session.commit()

    return jsonify({
        'succes': True,
        'message': f'Présence enregistrée — {statut.upper()}',
        'statut': statut,
        'personne': f'{personne.prenom} {personne.nom}'
    }), 200


# ============================================================
# CAS 2 — Modifier manuellement une présence
# ============================================================
@presences_bp.route('/api/<string:presence_id>/modifier', methods=['PUT'])
@role_requis('enseignant')
def modifier_presence(presence_id):
    presence = Presence.query.get_or_404(presence_id)
    data = request.get_json(force=True, silent=True) or {}

    nouveau_statut = data.get('statut', '').strip()
    justification  = data.get('justification', '').strip()

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

    ancien_statut               = presence.statut
    presence.statut             = nouveau_statut
    presence.modifie_par        = current_user.id
    presence.modifie_le         = datetime.now(timezone.utc)
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
# GET — Liste des présences d'une session (API mobile + web)
# ============================================================
@presences_bp.route('/api/session/<string:session_id>/liste', methods=['GET'])
@role_requis('enseignant')
def liste_presences(session_id):
    Session.query.get_or_404(session_id)
    presences = Presence.query.filter_by(session_id=session_id)\
        .order_by(Presence.horodatage).all()

    return jsonify({
        'succes': True,
        'presences': [{
            'id':                        p.id,
            'personne_id':               p.personne_id,
            'statut':                    p.statut,
            'horodatage':                p.horodatage.isoformat() if p.horodatage else None,
            'methode_validation':        p.methode_validation,
            'justification_modification': p.justification_modification
        } for p in presences]
    }), 200


# ============================================================
# GET — Historique des présences d'une personne (API mobile)
# ============================================================
@presences_bp.route('/api/personne/<string:personne_id>', methods=['GET'])
@role_requis('enseignant')
def historique_personne(personne_id):
    Personne.query.get_or_404(personne_id)
    presences = Presence.query.filter_by(personne_id=personne_id)\
        .order_by(Presence.horodatage.desc()).limit(50).all()

    total    = len(presences)
    presents = sum(1 for p in presences if p.statut == 'present')
    retards  = sum(1 for p in presences if p.statut == 'retard')
    absents  = sum(1 for p in presences if p.statut == 'absent')

    return jsonify({
        'succes': True,
        'statistiques': {
            'total':          total,
            'presents':       presents,
            'retards':        retards,
            'absents':        absents,
            'taux_presence':  round((presents + retards) / total * 100, 1) if total > 0 else 0
        },
        'presences': [{
            'id':         p.id,
            'session_id': p.session_id,
            'statut':     p.statut,
            'horodatage': p.horodatage.isoformat() if p.horodatage else None,
        } for p in presences]
    }), 200


# ============================================================
# PAGE WEB — Liste des sessions avec présences
# ============================================================
@presences_bp.route('/')
@role_requis('enseignant')
def liste():
    from app.models import Configuration
    config = Configuration.get_config()
    mode   = config.mode if config else 'ecole'

    sessions = Session.query.filter(
        Session.statut.in_(['terminee', 'en_cours'])
    ).order_by(Session.heure_debut.desc()).limit(50).all()

    sessions_avec_stats = []
    for s in sessions:
        presences = Presence.query.filter_by(session_id=s.id).all()
        total    = len(presences)
        presents = sum(1 for p in presences if p.statut == 'present')
        retards  = sum(1 for p in presences if p.statut == 'retard')
        absents  = sum(1 for p in presences if p.statut == 'absent')
        sessions_avec_stats.append({
            'session':  s,
            'total':    total,
            'presents': presents,
            'retards':  retards,
            'absents':  absents,
            'taux':     round((presents + retards) / total * 100) if total > 0 else 0
        })

    return render_template('presences/liste.html',
        sessions_avec_stats=sessions_avec_stats, mode=mode)


# ============================================================
# PAGE WEB — Détail des présences d'une session
# ============================================================
@presences_bp.route('/session/<string:session_id>')
@role_requis('enseignant')
def detail_session(session_id):
    from app.models import Configuration
    config = Configuration.get_config()
    mode   = config.mode if config else 'ecole'

    session  = Session.query.get_or_404(session_id)
    presences = Presence.query.filter_by(session_id=session_id)\
        .order_by(Presence.horodatage).all()

    presences_detail = []
    for p in presences:
        personne = Personne.query.get(p.personne_id)
        presences_detail.append({'presence': p, 'personne': personne})

    total    = len(presences)
    presents = sum(1 for p in presences if p.statut == 'present')
    retards  = sum(1 for p in presences if p.statut == 'retard')
    absents  = sum(1 for p in presences if p.statut == 'absent')

    return render_template('presences/detail_session.html',
        session=session,
        presences_detail=presences_detail,
        total=total, presents=presents,
        retards=retards, absents=absents,
        mode=mode)