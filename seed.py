"""
seed.py — Script d'initialisation des données de base
======================================================
Ce script crée :
  1. La configuration par défaut du système
  2. Le compte Admin initial

À exécuter UNE SEULE FOIS après la création des tables.
Commande : python seed.py

IMPORTANT : Changer le mot de passe admin après le premier démarrage !
"""

from app import create_app, db
from app.models import Configuration, User
from flask_bcrypt import Bcrypt
from datetime import datetime, timezone

# --- Créer l'application Flask ---
app = create_app('development')
bcrypt = Bcrypt(app)


def seed_configuration():
    """
    Créer la configuration par défaut du système.
    Une seule instance — Singleton.
    """
    # Vérifier si une configuration existe déjà
    existing = Configuration.query.first()
    if existing:
        print("⚠️  Configuration déjà existante — ignorée.")
        return

    config = Configuration(
        mode='ecole',                        # Mode école par défaut
        similarity_threshold=0.90,           # Seuil reconnaissance faciale 90%
        max_attempts=5,                      # Blocage après 5 tentatives échouées
        data_retention_days=365,             # Conservation données 1 an (RGPD)
        default_language='fr',               # Langue française par défaut
        developer_email='adam@dev.com',      # ← Remplace par ton email
        admin_email=''                       # Sera rempli quand l'admin est créé
    )

    db.session.add(config)
    db.session.commit()
    print("✅ Configuration par défaut créée.")


def seed_admin():
    """
    Créer le compte Admin initial.
    Ce compte est créé directement par le développeur (toi).
    Il n'existe qu'un seul admin par établissement.
    """
    # Vérifier si un admin existe déjà
    existing = User.query.filter_by(role='admin').first()
    if existing:
        print("⚠️  Compte Admin déjà existant — ignoré.")
        return

    # Mot de passe temporaire — À CHANGER IMMÉDIATEMENT après connexion !
    temp_password = 'Admin@1234'
    password_hash = bcrypt.generate_password_hash(temp_password).decode('utf-8')

    admin = User(
        first_name='Admin',
        last_name='Système',
        email='admin@universite.ma',         # ← Remplace par l'email réel de l'admin
        password_hash=password_hash,
        department='Administration',
        role='admin',                        # Rôle attribué directement par le développeur
        requested_role=None,                 # Pas de rôle souhaité — créé directement
        account_status='actif',              # Compte actif immédiatement
        is_active=True,
        validated_by=None,                   # Créé par le développeur, pas par un admin
        validated_at=datetime.utcnow(),
        failed_attempts=0,
        created_at=datetime.utcnow()
    )

    db.session.add(admin)
    db.session.commit()

    # Mettre à jour l'email admin dans la configuration
    config = Configuration.query.first()
    if config:
        config.admin_email = admin.email
        db.session.commit()

    print("✅ Compte Admin créé avec succès.")
    print("─" * 45)
    print(f"   Email    : {admin.email}")
    print(f"   Mot de passe : {temp_password}")
    print("─" * 45)
    print("⚠️  IMPORTANT : Change le mot de passe après la première connexion !")


def run_seed():
    """Exécuter toutes les fonctions de seed"""
    print("\n" + "=" * 45)
    print("   INITIALISATION DE LA BASE DE DONNÉES")
    print("=" * 45 + "\n")

    with app.app_context():
        seed_configuration()
        seed_admin()

    print("\n" + "=" * 45)
    print("   INITIALISATION TERMINÉE AVEC SUCCÈS ✅")
    print("=" * 45 + "\n")


if __name__ == '__main__':
    run_seed()
