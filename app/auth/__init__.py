from flask import Blueprint

# Créer le blueprint d'authentification
# Toutes les routes d'auth seront préfixées par /auth
auth = Blueprint('auth', __name__, url_prefix='/auth')

# Importer les routes après pour éviter les imports circulaires
from app.auth import routes