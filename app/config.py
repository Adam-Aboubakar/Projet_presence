import os
from dotenv import load_dotenv

# Charger les variables du fichier .env
load_dotenv()

class Config:
    """
    Configuration principale de l'application.
    Toutes les valeurs sensibles viennent du fichier .env
    """

    # --- Sécurité Flask ---
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev_key_change_in_production')

    # --- Base de données ---
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Chiffrement ---
    ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')

    # --- Configuration système ---
    SYSTEM_MODE = os.getenv('SYSTEM_MODE', 'ecole')
    SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', 0.85))
    MAX_ATTEMPTS = int(os.getenv('MAX_ATTEMPTS', 5))

    # --- Upload photos ---
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # --- Configuration Gmail / Flask-Mail ---
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True') == 'True'
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER')

    # --- Emails des destinataires ---
    DEVELOPER_EMAIL = os.getenv('DEVELOPER_EMAIL')
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


# Sélectionner la configuration selon l'environnement
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}