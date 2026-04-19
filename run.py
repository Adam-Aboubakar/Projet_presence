from app import create_app, db
from app import models  # Importer les modèles explicitement

# Créer l'instance de l'application
app = create_app('development')

if __name__ == '__main__':
    with app.app_context():
        # Forcer la création des tables dans presence_db
        db.drop_all()    # Supprimer les anciennes tables si elles existent
        db.create_all()  # Créer toutes les tables
        print("✅ Tables créées avec succès !")

    # Lancer le serveur Flask
    app.run(debug=True)