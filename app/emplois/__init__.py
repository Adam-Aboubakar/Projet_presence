from flask import Blueprint

emplois_bp = Blueprint('emplois', __name__, url_prefix='/emplois')

from app.emplois import routes