from flask import Blueprint

photos_bp = Blueprint('photos', __name__, url_prefix='/photos')

from app.photos import routes