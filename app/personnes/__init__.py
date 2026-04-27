"""
personnes/__init__.py — Blueprint Gestion des Personnes
=========================================================
Ce blueprint gère toutes les opérations sur les personnes :
    - Mode école      → Étudiants
    - Mode entreprise → Employés

Préfixe URL : /personnes
Accès : Admin et Agent de scolarité / RH
"""

from flask import Blueprint

# Créer le blueprint personnes avec le préfixe /personnes
personnes = Blueprint('personnes', __name__, url_prefix='/personnes')

# Importer les routes après pour éviter les imports circulaires
from app.personnes import routes