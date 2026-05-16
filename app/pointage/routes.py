from flask import render_template, request, jsonify
from app.pointage import pointage_bp
from app import csrf
from app.models import db, Session, Personne, CarteRFID, Presence
from app.utils.chiffrement import dechiffrer_texte
from datetime import datetime, timezone
import threading

# RFID en attente (partagé entre terminal et page)
rfid_en_attente = {'numero': None, 'timestamp': 0}

@pointage_bp.route('/')
def index():
    return render_template('pointage/index.html')

@pointage_bp.route('/api/rfid', methods=['POST'])
@csrf.exempt
def recevoir_rfid():
    """Reçoit le RFID depuis RC522 ou terminal de test."""
    import time
    data = request.get_json()
    numero = data.get('numero_rfid', '').strip().upper()
    if not numero:
        return jsonify({'succes': False, 'message': 'RFID manquant'}), 400
    rfid_en_attente['numero'] = numero
    rfid_en_attente['timestamp'] = time.time()
    return jsonify({'succes': True}), 200

@pointage_bp.route('/api/rfid/poll', methods=['GET'])
def poll_rfid():
    """La page HTML interroge cette route pour savoir si un RFID a été scanné."""
    import time
    numero = rfid_en_attente.get('numero')
    timestamp = rfid_en_attente.get('timestamp', 0)
    # RFID valide seulement si reçu dans les 10 dernières secondes
    if numero and (time.time() - timestamp) < 10:
        rfid_en_attente['numero'] = None
        return jsonify({'succes': True, 'numero_rfid': numero}), 200
    return jsonify({'succes': False}), 200