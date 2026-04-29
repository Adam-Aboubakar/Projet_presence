from flask import request, jsonify
from datetime import datetime
from app.rfid import rfid_bp
from app.models import db, CarteRFID, Personne, JournalSecurite
from app.utils.chiffrement import chiffrer_texte, dechiffrer_texte
from app.auth.decorateurs import role_requis
from flask_login import current_user


def journaliser(type_evenement, message, severite='INFO', personne_id=None):
    entree = JournalSecurite(
        type_evenement=type_evenement,
        description=message,
        severite=severite,
        utilisateur_id=current_user.id if current_user.is_authenticated else None,
        personne_id=personne_id,
        adresse_ip=request.remote_addr
    )
    db.session.add(entree)


# ============================================================
# CAS 1 — Associer une carte à une personne
# ============================================================
@rfid_bp.route('/api/<string:personne_id>/associer', methods=['POST'])
@role_requis('agent')
def associer_carte(personne_id):
    personne = Personne.query.get_or_404(personne_id)
    data = request.get_json()

    numero_rfid = data.get('numero_rfid', '').strip().upper()
    if not numero_rfid:
        return jsonify({'succes': False, 'message': 'Numéro RFID obligatoire'}), 400

    # Vérifier que la personne n'a pas déjà une carte active
    carte_active = CarteRFID.query.filter_by(
        personne_id=personne_id,
        statut='actif'
    ).first()
    if carte_active:
        return jsonify({
            'succes': False,
            'message': 'Cette personne a déjà une carte active. Révoquez-la d\'abord.'
        }), 400

    # Vérifier que le numéro n'est pas déjà utilisé
    # On doit déchiffrer toutes les cartes actives et comparer
    toutes_cartes = CarteRFID.query.filter_by(statut='actif').all()
    for carte in toutes_cartes:
        try:
            if dechiffrer_texte(carte.numero_rfid) == numero_rfid:
                return jsonify({
                    'succes': False,
                    'message': 'Ce numéro RFID est déjà attribué à une autre personne.'
                }), 400
        except Exception:
            continue

    # Chiffrer et sauvegarder
    nouvelle_carte = CarteRFID(
        personne_id=personne_id,
        numero_rfid=chiffrer_texte(numero_rfid),
        statut='actif',
        attribuee_le=datetime.utcnow()
    )
    db.session.add(nouvelle_carte)

    journaliser(
        type_evenement='carte_attribuee',
        message=f'Carte RFID attribuée à {personne.prenom} {personne.nom}',
        severite='INFO',
        personne_id=personne_id
    )

    db.session.commit()
    return jsonify({'succes': True, 'message': 'Carte RFID associée avec succès', 'carte_id': nouvelle_carte.id}), 201


# ============================================================
# CAS 2 — Révoquer une carte
# ============================================================
@rfid_bp.route('/api/<string:carte_id>/revoquer', methods=['POST'])
@role_requis('agent')
def revoquer_carte(carte_id):
    carte = CarteRFID.query.get_or_404(carte_id)

    if carte.statut == 'revoque':
        return jsonify({'succes': False, 'message': 'Cette carte est déjà révoquée'}), 400

    data = request.get_json()
    raison = data.get('raison', '').strip()
    if raison not in ['perdu', 'vole', 'defectueux', 'autre']:
        return jsonify({'succes': False, 'message': 'Raison invalide. Valeurs: perdu, vole, defectueux, autre'}), 400

    carte.statut = 'revoque'
    carte.revoquee_le = datetime.utcnow()
    carte.raison_revocation = raison

    personne = Personne.query.get(carte.personne_id)
    journaliser(
        type_evenement='carte_revoquee',
        message=f'Carte RFID révoquée pour {personne.prenom} {personne.nom} — raison: {raison}',
        severite='WARNING',
        personne_id=carte.personne_id
    )

    db.session.commit()
    return jsonify({'succes': True, 'message': 'Carte révoquée avec succès'}), 200


# ============================================================
# CAS 3 — Remplacer une carte
# ============================================================
@rfid_bp.route('/api/<string:personne_id>/remplacer', methods=['POST'])
@role_requis('agent')
def remplacer_carte(personne_id):
    personne = Personne.query.get_or_404(personne_id)
    data = request.get_json()

    nouveau_numero = data.get('numero_rfid', '').strip().upper()
    raison = data.get('raison', 'autre').strip()

    if not nouveau_numero:
        return jsonify({'succes': False, 'message': 'Nouveau numéro RFID obligatoire'}), 400

    # Révoquer la carte active actuelle
    carte_active = CarteRFID.query.filter_by(personne_id=personne_id, statut='actif').first()
    if carte_active:
        carte_active.statut = 'revoque'
        carte_active.revoquee_le = datetime.utcnow()
        carte_active.raison_revocation = raison

    # Vérifier que le nouveau numéro n'est pas déjà utilisé
    toutes_cartes = CarteRFID.query.filter_by(statut='actif').all()
    for carte in toutes_cartes:
        try:
            if dechiffrer_texte(carte.numero_rfid) == nouveau_numero:
                return jsonify({'succes': False, 'message': 'Ce numéro est déjà utilisé'}), 400
        except Exception:
            continue

    # Créer la nouvelle carte
    nouvelle_carte = CarteRFID(
        personne_id=personne_id,
        numero_rfid=chiffrer_texte(nouveau_numero),
        statut='actif',
        attribuee_le=datetime.utcnow()
    )
    db.session.add(nouvelle_carte)

    journaliser(
        type_evenement='carte_remplacee',
        message=f'Carte RFID remplacée pour {personne.prenom} {personne.nom}',
        severite='INFO',
        personne_id=personne_id
    )

    db.session.commit()
    return jsonify({'succes': True, 'message': 'Carte remplacée avec succès', 'carte_id': nouvelle_carte.id}), 201


# ============================================================
# CAS 4 — Vérifier une carte (Raspberry Pi — Semaine 3)
# ============================================================
@rfid_bp.route('/api/verifier', methods=['POST'])
def verifier_carte():
    data = request.get_json()
    numero_rfid = data.get('numero_rfid', '').strip().upper()

    if not numero_rfid:
        return jsonify({'autorise': False, 'message': 'Numéro RFID manquant'}), 400

    # Chercher parmi toutes les cartes actives
    cartes_actives = CarteRFID.query.filter_by(statut='actif').all()
    for carte in cartes_actives:
        try:
            if dechiffrer_texte(carte.numero_rfid) == numero_rfid:
                personne = Personne.query.get(carte.personne_id)
                if personne and personne.statut == 'actif':
                    return jsonify({
                        'autorise': True,
                        'personne_id': personne.id,
                        'nom': f'{personne.prenom} {personne.nom}'
                    }), 200
                else:
                    journaliser('carte_personne_inactive',
                                f'Tentative avec carte d\'une personne inactive', 'WARNING')
                    db.session.commit()
                    return jsonify({'autorise': False, 'message': 'Personne inactive'}), 403
        except Exception:
            continue

    # Carte inconnue
    journaliser('carte_inconnue', f'Tentative avec carte inconnue', 'CRITIQUE')
    db.session.commit()
    return jsonify({'autorise': False, 'message': 'Carte inconnue'}), 403


# ============================================================
# GET — Historique des cartes d'une personne
# ============================================================
@rfid_bp.route('/api/<string:personne_id>/liste', methods=['GET'])
@role_requis('agent')
def liste_cartes(personne_id):
    Personne.query.get_or_404(personne_id)
    cartes = CarteRFID.query.filter_by(personne_id=personne_id).order_by(CarteRFID.attribuee_le.desc()).all()

    resultat = []
    for carte in cartes:
        resultat.append({
            'id': carte.id,
            'statut': carte.statut,
            'attribuee_le': carte.attribuee_le.isoformat() if carte.attribuee_le else None,
            'revoquee_le': carte.revoquee_le.isoformat() if carte.revoquee_le else None,
            'raison_revocation': carte.raison_revocation
        })

    return jsonify({'succes': True, 'cartes': resultat}), 200