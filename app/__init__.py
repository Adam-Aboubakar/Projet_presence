from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_babel import Babel
from flask_migrate import Migrate
from flask_mail import Mail
from flask_bcrypt import Bcrypt
from app.config import config

# --- Initialisation des extensions ---
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
babel = Babel()
mail = Mail()
bcrypt = Bcrypt()

def create_app(config_name='default'):
    app = Flask(__name__)

    # --- Charger la configuration ---
    app.config.from_object(config[config_name])

    # --- Connecter les extensions à l'app ---
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    babel.init_app(app)
    mail.init_app(app)
    bcrypt.init_app(app)

    # --- Configuration de Flask-Login ---
    login_manager.login_view = 'auth.connexion'  # ← Mis à jour en français
    login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
    login_manager.login_message_category = 'warning'

    # --- Enregistrer les blueprints ---
    from app.routes import main
    app.register_blueprint(main)

    # --- Enregistrer le blueprint auth ---
    from app.auth import auth
    app.register_blueprint(auth)

    from app.auth.decorateurs import configurer_gestionnaires_erreurs
    configurer_gestionnaires_erreurs(app)

    # --- Enregistrer le blueprint admin ---
    from app.admin import admin
    app.register_blueprint(admin)

    # --- Enregistrer le blueprint personnes ---
    from app.personnes import personnes
    app.register_blueprint(personnes)

    return app