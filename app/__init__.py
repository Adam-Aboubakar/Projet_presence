from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_babel import Babel
from app.config import config

# --- Initialisation des extensions ---
# Ces objets seront utilisés dans toute l'application
db = SQLAlchemy()          # Gestion de la base de données
login_manager = LoginManager()  # Gestion des sessions utilisateurs
babel = Babel()            # Gestion du multi-langues

def create_app(config_name='default'):
    """
    Factory function — crée et configure l'application Flask.
    Utiliser une factory permet de créer plusieurs instances
    de l'app (développement, test, production).
    """
    app = Flask(__name__)

    # --- Charger la configuration ---
    app.config.from_object(config[config_name])

    # --- Connecter les extensions à l'app ---
    db.init_app(app)
    login_manager.init_app(app)
    babel.init_app(app)

    # --- Configuration de Flask-Login ---
    # Si l'utilisateur n'est pas connecté, rediriger vers la page de login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
    login_manager.login_message_category = 'warning'

    # --- Enregistrer les blueprints (routes) ---
    # Un blueprint = un groupe de routes logiquement liées
    from app.routes import main
    app.register_blueprint(main)

    return app