from flask import Flask, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_babel import Babel, gettext
from flask_migrate import Migrate
from flask_mail import Mail
from flask_bcrypt import Bcrypt
from app.config import config
from flask_bootstrap import Bootstrap5
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
babel = Babel()
mail = Mail()
bcrypt = Bcrypt()
bootstrap = Bootstrap5()
csrf = CSRFProtect()

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    bcrypt.init_app(app)
    bootstrap.init_app(app)
    csrf.init_app(app)

    def get_locale():
        try:
            if 'langue' in session:
                return session['langue']
            return request.accept_languages.best_match(['fr', 'en', 'ar']) or 'fr'
        except:
            return 'fr'

    babel.init_app(app, locale_selector=get_locale)
    app.jinja_env.globals['_'] = gettext

    login_manager.login_view = 'auth.connexion'
    login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
    login_manager.login_message_category = 'warning'

    @app.context_processor
    def inject_config():
        try:
            from app.models import Configuration
            config = Configuration.get_config()
            return {'config': config}
        except Exception:
            return {'config': None}

    from app.routes import main
    app.register_blueprint(main)

    from app.auth import auth
    app.register_blueprint(auth)

    from app.auth.decorateurs import configurer_gestionnaires_erreurs
    configurer_gestionnaires_erreurs(app)

    from app.admin import admin
    app.register_blueprint(admin)

    from app.personnes import personnes
    app.register_blueprint(personnes)

    from app.rfid import rfid_bp
    app.register_blueprint(rfid_bp)

    from app.photos import photos_bp
    app.register_blueprint(photos_bp)

    from app.sessions import sessions_bp
    app.register_blueprint(sessions_bp)

    from app.presences import presences_bp
    app.register_blueprint(presences_bp)

    from app.rapports import rapports_bp
    app.register_blueprint(rapports_bp)

    from app.journal import journal_bp
    app.register_blueprint(journal_bp)

    from app.emplois import emplois_bp
    app.register_blueprint(emplois_bp)

    return app