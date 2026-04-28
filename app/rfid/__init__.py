from flask import Blueprint

rfid_bp = Blueprint('rfid', __name__, url_prefix='/rfid')

from app.rfid import routes