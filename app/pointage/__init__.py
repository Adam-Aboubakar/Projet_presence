from flask import Blueprint
pointage_bp = Blueprint('pointage', __name__, url_prefix='/pointage')
from app.pointage import routes
