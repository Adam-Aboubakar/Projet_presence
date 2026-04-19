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
    # Clé secrète pour signer les cookies et les sessions
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev_key_change_in_production')

    # --- Base de données ---
    # URL de connexion à PostgreSQL
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    # Désactiver le suivi des modifications pour économiser de la mémoire
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Chiffrement ---
    # Clé utilisée pour chiffrer les photos et données biométriques (AES-256)
    ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')

    # --- Configuration système ---
    # Mode du système : 'ecole' ou 'entreprise'
    SYSTEM_MODE = os.getenv('SYSTEM_MODE', 'ecole')
    # Seuil minimum de similarité faciale pour valider une présence (0 à 1)
    SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', 0.85))
    # Nombre maximum de tentatives échouées avant blocage
    MAX_ATTEMPTS = int(os.getenv('MAX_ATTEMPTS', 5))

    # --- Upload photos ---
    # Dossier de stockage des photos
    UPLOAD_FOLDER = 'static/uploads'
    # Taille maximale des fichiers uploadés : 16 MB
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024


class DevelopmentConfig(Config):
    """
    Configuration pour le développement.
    Le mode DEBUG affiche les erreurs en détail.
    ATTENTION : Ne jamais activer en production !
    """
    DEBUG = True


class ProductionConfig(Config):
    """
    Configuration pour la production.
    Le mode DEBUG est désactivé pour la sécurité.
    """
    DEBUG = False


# Sélectionner la configuration selon l'environnement
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}