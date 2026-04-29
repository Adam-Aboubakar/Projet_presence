from flask import Blueprint

rapports_bp = Blueprint('rapports', __name__, url_prefix='/rapports')

from app.rapports import routes