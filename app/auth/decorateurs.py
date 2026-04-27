"""
decorateurs.py — Décorateurs de protection des routes
=======================================================
Contient les décorateurs :
  1. role_requis         — Vérifier le rôle de l'utilisateur
  2. compte_actif_requis — Vérifier que le compte est actif
  3. api_login_requis    — Protection des routes API REST
"""

from functools import wraps
from flask import abort, jsonify, request, redirect, url_for, flash
from flask_login import current_user


# ============================================================
# 1. DÉCORATEUR — Rôle requis
# Vérifie que l'utilisateur connecté a le bon rôle
# ============================================================
def role_requis(*roles):
    """
    Décorateur pour protéger les routes selon le rôle.

    Utilisation :
        @role_requis('admin')
        @role_requis('admin', 'enseignant')
        @role_requis('agent')

    Args:
        *roles : un ou plusieurs rôles autorisés
    """
    def decorateur(f):
        @wraps(f)
        def fonction_decoree(*args, **kwargs):
            # Vérifier que l'utilisateur est connecté
            if not current_user.is_authenticated:
                flash('Veuillez vous connecter pour accéder à cette page.', 'warning')
                return redirect(url_for('auth.connexion'))

            # Vérifier que le compte est actif
            if not current_user.compte_actif():
                flash('Votre compte n\'est pas actif.', 'danger')
                return redirect(url_for('auth.connexion'))

            # Vérifier le rôle
            if current_user.role not in roles:
                abort(403)  # Accès interdit

            return f(*args, **kwargs)
        return fonction_decoree
    return decorateur


# ============================================================
# 2. DÉCORATEUR — Compte actif requis
# Vérifie que le compte est actif sans vérifier le rôle
# ============================================================
def compte_actif_requis(f):
    """
    Décorateur pour vérifier que le compte est actif.
    Utilisé pour les routes accessibles à tous les rôles.

    Utilisation :
        @compte_actif_requis
        def ma_route():
            ...
    """
    @wraps(f)
    def fonction_decoree(*args, **kwargs):
        # Vérifier que l'utilisateur est connecté
        if not current_user.is_authenticated:
            flash('Veuillez vous connecter pour accéder à cette page.', 'warning')
            return redirect(url_for('auth.connexion'))

        # Vérifier que le compte est actif
        if not current_user.compte_actif():
            flash('Votre compte n\'est pas actif. Contactez l\'administrateur.', 'danger')
            return redirect(url_for('auth.connexion'))

        # Vérifier le statut du compte
        if current_user.statut_compte != 'actif':
            if current_user.statut_compte in ['en_attente', 'email_verifie']:
                return redirect(url_for('auth.attente'))
            flash('Accès refusé.', 'danger')
            return redirect(url_for('auth.connexion'))

        return f(*args, **kwargs)
    return fonction_decoree


# ============================================================
# 3. DÉCORATEUR — Protection API REST
# Retourne du JSON au lieu de rediriger
# ============================================================
def api_login_requis(f):
    """
    Décorateur pour protéger les routes API REST.
    Retourne une réponse JSON au lieu de rediriger.

    Utilisation :
        @api_login_requis
        def ma_route_api():
            ...
    """
    @wraps(f)
    def fonction_decoree(*args, **kwargs):
        # Vérifier que l'utilisateur est connecté
        if not current_user.is_authenticated:
            return jsonify({
                'succes': False,
                'message': 'Authentification requise.',
                'code': 'NON_AUTHENTIFIE'
            }), 401

        # Vérifier que le compte est actif
        if not current_user.compte_actif():
            return jsonify({
                'succes': False,
                'message': 'Compte inactif ou bloqué.',
                'code': 'COMPTE_INACTIF'
            }), 403

        return f(*args, **kwargs)
    return fonction_decoree


# ============================================================
# 4. DÉCORATEUR — Rôle requis pour API REST
# Combine api_login_requis + vérification du rôle
# ============================================================
def api_role_requis(*roles):
    """
    Décorateur pour protéger les routes API REST selon le rôle.
    Retourne du JSON au lieu de rediriger.

    Utilisation :
        @api_role_requis('admin')
        @api_role_requis('admin', 'enseignant')
    """
    def decorateur(f):
        @wraps(f)
        def fonction_decoree(*args, **kwargs):
            # Vérifier que l'utilisateur est connecté
            if not current_user.is_authenticated:
                return jsonify({
                    'succes': False,
                    'message': 'Authentification requise.',
                    'code': 'NON_AUTHENTIFIE'
                }), 401

            # Vérifier que le compte est actif
            if not current_user.compte_actif():
                return jsonify({
                    'succes': False,
                    'message': 'Compte inactif ou bloqué.',
                    'code': 'COMPTE_INACTIF'
                }), 403

            # Vérifier le rôle
            if current_user.role not in roles:
                return jsonify({
                    'succes': False,
                    'message': 'Accès non autorisé. Permissions insuffisantes.',
                    'code': 'ACCES_REFUSE',
                    'roles_requis': list(roles),
                    'role_actuel': current_user.role
                }), 403

            return f(*args, **kwargs)
        return fonction_decoree
    return decorateur


# ============================================================
# 5. GESTIONNAIRE D'ERREURS — 403 Accès interdit
# ============================================================
def configurer_gestionnaires_erreurs(app):
    """
    Configurer les gestionnaires d'erreurs HTTP.
    À appeler dans create_app().
    """
    @app.errorhandler(403)
    def acces_interdit(e):
        """Gérer l'erreur 403 — Accès interdit"""
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({
                'succes': False,
                'message': 'Accès interdit. Vous n\'avez pas les permissions nécessaires.',
                'code': 'ACCES_INTERDIT'
            }), 403
        return redirect(url_for('admin.tableau_de_bord'))

    @app.errorhandler(404)
    def page_introuvable(e):
        """Gérer l'erreur 404 — Page introuvable"""
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({
                'succes': False,
                'message': 'Ressource introuvable.',
                'code': 'INTROUVABLE'
            }), 404
        return redirect(url_for('admin.tableau_de_bord'))

    @app.errorhandler(500)
    def erreur_serveur(e):
        """Gérer l'erreur 500 — Erreur interne du serveur"""
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({
                'succes': False,
                'message': 'Erreur interne du serveur.',
                'code': 'ERREUR_SERVEUR'
            }), 500
        return redirect(url_for('admin.tableau_de_bord'))