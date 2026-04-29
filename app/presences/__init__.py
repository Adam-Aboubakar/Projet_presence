from flask import Blueprint

presences_bp = Blueprint('presences', __name__, url_prefix='/presences')

from app.presences import routes