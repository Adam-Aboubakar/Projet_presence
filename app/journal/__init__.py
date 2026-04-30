from flask import Blueprint

journal_bp = Blueprint('journal', __name__, url_prefix='/journal')

from app.journal import routes