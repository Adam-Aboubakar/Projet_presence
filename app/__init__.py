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
    app.config['SESSION_PERMANENT'] = True

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    bcrypt.init_app(app)
    bootstrap.init_app(app)
    csrf.init_app(app)
    csrf.exempt('app.admin.routes.creer_admin')
    csrf.exempt('app.rfid.routes.associer_carte')
    csrf.exempt('app.rfid.routes.revoquer_carte')
    csrf.exempt('app.rfid.routes.remplacer_carte')
    csrf.exempt('app.rfid.routes.verifier_carte')
    csrf.exempt('app.photos.routes.uploader_photo')
    csrf.exempt('app.photos.routes.capturer_photo')
    csrf.exempt('app.journal.routes.liste_logs')
    csrf.exempt('app.presences.routes.pointer')
    csrf.exempt('app.sessions.routes.verifier_rfid')

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
            from app.models import Configuration, Notification
            from flask import session as flask_session
            from flask_login import current_user
            cfg = Configuration.get_config()
            langue = flask_session.get('langue', 'fr')

            notifications_recentes = []
            nb_notifs = 0
            if current_user.is_authenticated and current_user.role == 'admin':
                notifications_recentes = Notification.query.filter_by(
                    destinataire_id=current_user.id,
                    est_lue=False
                ).order_by(Notification.cree_le.desc()).limit(5).all()
                nb_notifs = len(notifications_recentes)

            return {
                'config': cfg,
                'langue': langue,
                'notifications_recentes': notifications_recentes,
                'nb_notifs': nb_notifs
            }
        except Exception:
            return {'config': None, 'langue': 'fr', 'notifications_recentes': [], 'nb_notifs': 0}

    @app.before_request
    def verifier_inactivite():
        from flask_login import current_user, logout_user
        from flask import flash, redirect, url_for
        from datetime import datetime, timezone, timedelta

        if request.path == '/favicon.ico':
            return

        if request.endpoint and (
            request.endpoint.startswith('static') or
            request.endpoint.startswith('auth.')
        ):
            return

        if current_user.is_authenticated:
            derniere = session.get('derniere_activite')
            if derniere:
                try:
                    derniere_dt = datetime.fromisoformat(derniere)
                    inactif_depuis = datetime.now(timezone.utc) - derniere_dt
                    if inactif_depuis > timedelta(minutes=15):
                        logout_user()
                        session.clear()
                        flash('Session expirée. Veuillez vous reconnecter.', 'warning')
                        return redirect(url_for('auth.connexion'))
                except Exception:
                    pass

            session['derniere_activite'] = datetime.now(timezone.utc).isoformat()

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

    # Démarrer le scheduler
    from app.scheduler import init_scheduler
    init_scheduler(app)

    from app.pointage import pointage_bp
    app.register_blueprint(pointage_bp)

    return app