from flask import Blueprint, render_template

# Créer le blueprint principal
# Un blueprint = groupe de routes logiquement liées
main = Blueprint('main', __name__)


@main.route('/')
def index():
    """Page d'accueil du système"""
    return "✅ Système de Gestion de Présence — Opérationnel !"


@main.route('/health')
def health():
    """
    Route de vérification de l'état du système.
    Utilisée pour vérifier que le serveur fonctionne.
    """
    return {"status": "ok", "message": "Serveur opérationnel"}