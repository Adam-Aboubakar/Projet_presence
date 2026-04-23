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
from app.models import Configuration, Utilisateur
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
    existing = Configuration.query.first()
    if existing:
        print("⚠️  Configuration déjà existante — ignorée.")
        return

    config = Configuration(
        mode='ecole',
        seuil_similarite=0.90,
        max_tentatives=5,
        duree_retention_jours=365,
        langue_defaut='fr',
        email_developpeur='adam@dev.com',
        email_admin=''
    )

    db.session.add(config)
    db.session.commit()
    print("✅ Configuration par défaut créée.")


def seed_admin():
    """
    Créer le compte Admin initial.
    Maximum 3 admins par système.
    """
    existing = Utilisateur.query.filter_by(role='admin').first()
    if existing:
        print("⚠️  Compte Admin déjà existant — ignoré.")
        return

    if not Utilisateur.peut_ajouter_admin():
        print("❌ Limite de 3 admins atteinte.")
        return

    mot_de_passe_temp = 'Admin@1234'
    mot_de_passe_hache = bcrypt.generate_password_hash(mot_de_passe_temp).decode('utf-8')

    admin = Utilisateur(
        prenom='Admin',
        nom='Systeme',
        email='admin@universite.ma',
        mot_de_passe_hache=mot_de_passe_hache,
        departement='Administration',
        role='admin',
        role_souhaite=None,
        statut_compte='actif',
        est_actif=True,
        version=1,
        valide_par=None,
        valide_le=datetime.now(timezone.utc),
        tentatives_echouees=0,
        cree_le=datetime.now(timezone.utc)
    )

    db.session.add(admin)
    db.session.commit()

    config = Configuration.query.first()
    if config:
        config.email_admin = admin.email
        db.session.commit()

    print("✅ Compte Admin créé avec succès.")
    print("─" * 45)
    print(f"   Email        : {admin.email}")
    print(f"   Mot de passe : {mot_de_passe_temp}")
    print(f"   Admins       : {Utilisateur.nombre_admins()}/3")
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