from flask import request, jsonify, current_app
from datetime import datetime, timezone
import os
import uuid
import cv2
import numpy as np
import base64
from app.photos import photos_bp
from app.models import db, Photo, Personne, JournalSecurite
from app.utils.chiffrement import chiffrer_fichier, dechiffrer_fichier
from app.auth.decorateurs import role_requis
from flask_login import current_user

FORMATS_AUTORISES = {'jpg', 'jpeg', 'png'}
TAILLE_MAX = 5 * 1024 * 1024  # 5MB


def journaliser(type_evenement, description, severite='INFO', personne_id=None):
    """Ajouter une entrée dans le journal de sécurité et envoyer alerte si nécessaire."""
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


def verifier_qualite_photo(donnees_image):
    """
    Vérifier la qualité de la photo via OpenCV.
    Retourne (ok, message)
    """
    # Convertir bytes en image OpenCV
    np_arr = np.frombuffer(donnees_image, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if img is None:
        return False, "Image invalide ou corrompue"

    # Charger le détecteur de visages
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    detecteur = cv2.CascadeClassifier(cascade_path)
    gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    visages = detecteur.detectMultiScale(gris, scaleFactor=1.1, minNeighbors=5)

    if len(visages) == 0:
        return False, "Aucun visage détecté dans la photo"
    if len(visages) > 1:
        return False, "Plusieurs visages détectés — une seule personne par photo"

    # Vérifier la netteté (variance du Laplacien)
    nettete = cv2.Laplacian(gris, cv2.CV_64F).var()
    if nettete < 50:
        return False, "Photo trop floue — veuillez reprendre la photo"

    return True, "Photo valide"


def sauvegarder_photo(donnees_image, personne_id):
    """Chiffrer et sauvegarder la photo sur disque. Retourne le chemin."""
    donnees_chiffrees = chiffrer_fichier(donnees_image)
    nom_fichier = f"{uuid.uuid4()}.enc"
    dossier = os.path.join(current_app.root_path, 'static', 'uploads', 'photos')
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, nom_fichier)
    with open(chemin, 'wb') as f:
        f.write(donnees_chiffrees)
    return f"uploads/photos/{nom_fichier}"


# ============================================================
# CAS 1 — Upload photo (fichier)
# Une seule photo active à la fois — l'ancienne va en historique
# ============================================================
@photos_bp.route('/api/<string:personne_id>/uploader', methods=['POST'])
@role_requis('agent')
def uploader_photo(personne_id):
    personne = Personne.query.get_or_404(personne_id)

    if 'photo' not in request.files:
        return jsonify({'succes': False, 'message': 'Aucun fichier envoyé'}), 400

    fichier = request.files['photo']
    if fichier.filename == '':
        return jsonify({'succes': False, 'message': 'Fichier vide'}), 400

    # Vérifier le format
    extension = fichier.filename.rsplit('.', 1)[-1].lower()
    if extension not in FORMATS_AUTORISES:
        return jsonify({'succes': False, 'message': 'Format invalide. JPG et PNG uniquement'}), 400

    donnees = fichier.read()

    # Vérifier la taille
    if len(donnees) > TAILLE_MAX:
        return jsonify({'succes': False, 'message': 'Fichier trop grand. Maximum 5MB'}), 400

    # Vérifier la qualité
    ok, message = verifier_qualite_photo(donnees)
    if not ok:
        return jsonify({'succes': False, 'message': message}), 400

    # Désactiver l'ancienne photo active — elle va en historique
    Photo.query.filter_by(personne_id=personne_id, est_principale=True)\
        .update({'est_principale': False})

    # Sauvegarder et chiffrer la nouvelle photo
    chemin = sauvegarder_photo(donnees, personne_id)

    # La nouvelle photo est toujours active
    photo = Photo(
        personne_id=personne_id,
        chemin_fichier=chemin,
        est_principale=True,
        cree_le=datetime.now(timezone.utc)
    )
    db.session.add(photo)

    journaliser('photo_ajoutee',
                f'Photo ajoutée pour {personne.prenom} {personne.nom}',
                personne_id=personne_id)
    db.session.commit()

    return jsonify({
        'succes': True,
        'message': 'Photo uploadée avec succès',
        'photo_id': photo.id
    }), 201


# ============================================================
# CAS 2 — Capture via caméra (reçoit base64)
# Une seule photo active à la fois — l'ancienne va en historique
# ============================================================
@photos_bp.route('/api/<string:personne_id>/capturer', methods=['POST'])
@role_requis('agent')
def capturer_photo(personne_id):
    personne = Personne.query.get_or_404(personne_id)
    data = request.get_json()

    image_base64 = data.get('image_base64', '')
    if not image_base64:
        return jsonify({'succes': False, 'message': 'Aucune image reçue'}), 400

    # Décoder le base64
    if ',' in image_base64:
        image_base64 = image_base64.split(',')[1]
    try:
        donnees = base64.b64decode(image_base64)
    except Exception:
        return jsonify({'succes': False, 'message': 'Image base64 invalide'}), 400

    if len(donnees) > TAILLE_MAX:
        return jsonify({'succes': False, 'message': 'Image trop grande. Maximum 5MB'}), 400

    # Vérifier la qualité
    ok, message = verifier_qualite_photo(donnees)
    if not ok:
        return jsonify({'succes': False, 'message': message}), 400

    # Désactiver l'ancienne photo active — elle va en historique
    Photo.query.filter_by(personne_id=personne_id, est_principale=True)\
        .update({'est_principale': False})

    # Sauvegarder et chiffrer la nouvelle photo
    chemin = sauvegarder_photo(donnees, personne_id)

    # La nouvelle photo est toujours active
    photo = Photo(
        personne_id=personne_id,
        chemin_fichier=chemin,
        est_principale=True,
        cree_le=datetime.now(timezone.utc)
    )
    db.session.add(photo)

    journaliser('photo_capturee',
                f'Photo capturée pour {personne.prenom} {personne.nom}',
                personne_id=personne_id)
    db.session.commit()

    return jsonify({
        'succes': True,
        'message': 'Photo capturée avec succès',
        'photo_id': photo.id
    }), 201


# ============================================================
# GET — Photo active d'une personne
# Utilisée par DeepFace lors du pointage
# ============================================================
@photos_bp.route('/api/<string:personne_id>/active', methods=['GET'])
@role_requis('agent')
def photo_active(personne_id):
    """Retourne uniquement la photo active — utilisée par DeepFace."""
    Personne.query.get_or_404(personne_id)

    photo = Photo.query.filter_by(
        personne_id=personne_id,
        est_principale=True
    ).first()

    if not photo:
        return jsonify({'succes': False, 'message': 'Aucune photo active'}), 404

    return jsonify({
        'succes': True,
        'photo': {
            'id': photo.id,
            'cree_le': photo.cree_le.isoformat() if photo.cree_le else None
        }
    }), 200


# ============================================================
# GET — Historique des photos d'une personne
# Toutes les photos — active + anciennes
# ============================================================
@photos_bp.route('/api/<string:personne_id>/historique', methods=['GET'])
@role_requis('agent')
def historique_photos(personne_id):
    """Retourne toutes les photos — active + historique."""
    Personne.query.get_or_404(personne_id)

    photos = Photo.query.filter_by(personne_id=personne_id)\
        .order_by(Photo.cree_le.desc()).all()

    return jsonify({
        'succes': True,
        'photos': [{
            'id': p.id,
            'est_active': p.est_principale,  # True = photo active actuelle
            'cree_le': p.cree_le.isoformat() if p.cree_le else None
        } for p in photos]
    }), 200