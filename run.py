from app import create_app, db
from app import models  # Importer les modèles pour que Flask-Migrate les détecte

# Créer l'instance de l'application
app = create_app('development')

if __name__ == '__main__':
    app.run(debug=True)