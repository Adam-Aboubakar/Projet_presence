"""
admin/__init__.py — Blueprint Administration
=============================================
Ce blueprint gère toutes les fonctionnalités
réservées aux administrateurs du système.

Préfixe URL : /admin
Accès : uniquement les utilisateurs avec role = 'admin'
"""

from flask import Blueprint

# Créer le blueprint admin avec le préfixe /admin
# Toutes les routes de ce module commenceront par /admin
admin = Blueprint('admin', __name__, url_prefix='/admin')

# Importer les routes après pour éviter les imports circulaires
from app.admin import routes