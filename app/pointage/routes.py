from flask import render_template, request, jsonify
from app.pointage import pointage_bp
from app import csrf
import threading
import time

# ── RFID en attente (partagé entre terminal et page) ──────────
rfid_lock = threading.Lock()
rfid_en_attente = {'numero': None, 'timestamp': 0}


# ============================================================
# Page principale de pointage
# ============================================================
@pointage_bp.route('/')
def index():
    return render_template('pointage/index.html')


# ============================================================
# Reçoit le RFID depuis RC522 ou terminal de test
# ============================================================
@pointage_bp.route('/api/rfid', methods=['POST'])
@csrf.exempt
def recevoir_rfid():
    data = request.get_json()
    numero = data.get('numero_rfid', '').strip().upper()

    if not numero:
        return jsonify({'succes': False, 'message': 'RFID manquant'}), 400

    with rfid_lock:
        rfid_en_attente['numero'] = numero
        rfid_en_attente['timestamp'] = time.time()

    return jsonify({'succes': True}), 200


# ============================================================
# La page HTML interroge cette route pour savoir si un RFID
# a été scanné (polling toutes les secondes)
# ============================================================
@pointage_bp.route('/api/rfid/poll', methods=['GET'])
def poll_rfid():
    with rfid_lock:
        numero = rfid_en_attente.get('numero')
        timestamp = rfid_en_attente.get('timestamp', 0)
        # RFID valide seulement si reçu dans les 10 dernières secondes
        if numero and (time.time() - timestamp) < 10:
            rfid_en_attente['numero'] = None
            return jsonify({'succes': True, 'numero_rfid': numero}), 200

    return jsonify({'succes': False}), 200