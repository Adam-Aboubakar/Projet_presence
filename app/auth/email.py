"""
email.py — Module d'envoi des emails
=====================================
Contient les fonctions d'envoi des emails :
  1. envoyer_email_verification  — Confirmation de l'adresse email
  2. envoyer_notification_admin  — Notification à l'admin (nouveau compte en attente)
  3. envoyer_email_validation    — Notification à l'utilisateur (compte validé)
  4. envoyer_email_rejet         — Notification à l'utilisateur (compte rejeté)
  5. envoyer_alerte_developpeur  — Alertes techniques au développeur

Décision architecturale :
  La notification à l'admin ne mentionne plus le rôle souhaité.
  L'admin voit simplement le nom, l'email et le département de l'utilisateur.
  Il attribue lui-même le rôle via des boutons radio dans son interface.
"""

from flask import current_app
from flask_mail import Message
from app import mail


# ============================================================
# FONCTION UTILITAIRE — Envoi générique d'un email
# ============================================================
def envoyer_email(destinataire, sujet, corps_html, corps_texte=None):
    """
    Fonction de base pour envoyer un email via Flask-Mail.

    Cette fonction est utilisée par toutes les autres fonctions de ce module.
    Elle centralise la logique d'envoi pour éviter la duplication de code.

    Args:
        destinataire (str) : adresse email du destinataire
        sujet        (str) : sujet de l'email
        corps_html   (str) : contenu HTML de l'email (affiché dans les clients modernes)
        corps_texte  (str) : contenu texte brut optionnel (fallback pour clients anciens)

    Returns:
        bool : True si l'email a été envoyé avec succès, False sinon
    """
    try:
        msg = Message(
            subject=sujet,
            # L'expéditeur est défini dans .env → MAIL_DEFAULT_SENDER
            sender=current_app.config['MAIL_DEFAULT_SENDER'],
            recipients=[destinataire]
        )
        # Corps HTML principal (affiché dans Gmail, Outlook, etc.)
        msg.html = corps_html

        # Corps texte brut optionnel (fallback pour anciens clients email)
        if corps_texte:
            msg.body = corps_texte

        mail.send(msg)
        return True

    except Exception as e:
        # En cas d'erreur, on log le problème sans planter l'application
        current_app.logger.error(f"Erreur envoi email à {destinataire} : {str(e)}")
        return False


# ============================================================
# 1. EMAIL DE VÉRIFICATION
# Envoyé à l'utilisateur immédiatement après l'inscription
# ============================================================
def envoyer_email_verification(utilisateur, token):
    """
    Envoyer l'email de confirmation d'adresse email.

    Flux :
        Inscription → Cet email est envoyé → L'utilisateur clique sur le lien
        → Son statut passe de 'en_attente' à 'email_verifie'
        → L'admin est notifié

    Le lien contient un token unique valable 24 heures.
    Si l'utilisateur ne clique pas dans ce délai, il peut demander
    un nouveau lien via la route /auth/renvoyer-email.

    Args:
        utilisateur : objet Utilisateur venant de s'inscrire
        token (str) : token de vérification unique généré lors de l'inscription
    """
    # Construire le lien de vérification avec le token
    # _external=True génère une URL complète (avec http://...)
    base_url = current_app.config.get('BASE_URL', 'http://127.0.0.1:5000')
    lien_verification = f"{base_url}/auth/verification/{token}"

    sujet = "Confirmez votre adresse email — Système de Présence"

    corps_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #2c3e50;">Confirmation de votre adresse email</h2>

        <p>Bonjour <strong>{utilisateur.prenom} {utilisateur.nom}</strong>,</p>

        <p>Merci de vous être inscrit sur le <strong>Système de Gestion de Présence</strong>.</p>

        <p>Pour confirmer votre adresse email, cliquez sur le bouton ci-dessous :</p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{lien_verification}"
               style="background-color: #3498db; color: white; padding: 12px 30px;
                      text-decoration: none; border-radius: 5px; font-size: 16px;">
                Confirmer mon email
            </a>
        </div>

        <p style="color: #7f8c8d; font-size: 14px;">
            Ce lien est valable pendant <strong>24 heures</strong>.<br>
            Si vous n'avez pas créé de compte, ignorez cet email.
        </p>

        <p style="color: #7f8c8d; font-size: 12px;">
            Si le bouton ne fonctionne pas, copiez ce lien dans votre navigateur :<br>
            <a href="{lien_verification}">{lien_verification}</a>
        </p>

        <hr style="border: none; border-top: 1px solid #ecf0f1; margin: 20px 0;">
        <p style="color: #95a5a6; font-size: 12px; text-align: center;">
            Système de Gestion de Présence — Email automatique, ne pas répondre.
        </p>
    </div>
    """

    # Version texte brut (fallback)
    corps_texte = f"""
    Bonjour {utilisateur.prenom} {utilisateur.nom},

    Pour confirmer votre adresse email, visitez ce lien :
    {lien_verification}

    Ce lien est valable pendant 24 heures.
    """

    return envoyer_email(utilisateur.email, sujet, corps_html, corps_texte)


# ============================================================
# 2. NOTIFICATION À L'ADMIN
# Envoyée quand un utilisateur a vérifié son email
# et attend la validation de l'admin
# ============================================================
def envoyer_notification_admin(utilisateur):
    """
    Notifier l'admin qu'un nouveau compte est en attente de validation.

    Flux :
        Vérification email → Cet email est envoyé à l'admin
        → L'admin se connecte → Il voit la demande
        → Il choisit le rôle via boutons radio (enseignant ou agent)
        → Il valide ou rejette le compte

    Note importante :
        On n'affiche plus le "rôle souhaité" car c'est l'admin qui décide.
        Il voit le nom, l'email et le département pour identifier la personne.

    Args:
        utilisateur : objet Utilisateur dont l'email vient d'être vérifié
    """
    # Récupérer l'email de l'admin depuis la configuration
    email_admin = current_app.config.get('ADMIN_EMAIL')

    # Si aucun email admin n'est configuré, on ne peut pas envoyer
    if not email_admin:
        return False

    # Lien vers la page de gestion des utilisateurs dans l'interface admin
    base_url = current_app.config.get('BASE_URL', 'http://127.0.0.1:5000')
    lien_admin = f"{base_url}/admin/comptes-attente"

    sujet = f"Nouveau compte en attente — {utilisateur.prenom} {utilisateur.nom}"

    corps_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #2c3e50;">Nouveau compte en attente de validation</h2>

        <p>Un nouvel utilisateur s'est inscrit et attend votre validation :</p>

        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="background-color: #f8f9fa;">
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Nom complet</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{utilisateur.prenom} {utilisateur.nom}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Email</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{utilisateur.email}</td>
            </tr>
            <tr style="background-color: #f8f9fa;">
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Département</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{utilisateur.departement or 'Non renseigné'}</td>
            </tr>
        </table>

        <p style="color: #7f8c8d;">
            Connectez-vous à l'interface d'administration pour attribuer un rôle
            et valider ou rejeter cette demande.
        </p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{lien_admin}"
               style="background-color: #27ae60; color: white; padding: 12px 30px;
                      text-decoration: none; border-radius: 5px; font-size: 16px;">
                Valider et attribuer un rôle
            </a>
        </div>

        <hr style="border: none; border-top: 1px solid #ecf0f1; margin: 20px 0;">
        <p style="color: #95a5a6; font-size: 12px; text-align: center;">
            Système de Gestion de Présence — Email automatique, ne pas répondre.
        </p>
    </div>
    """

    return envoyer_email(email_admin, sujet, corps_html)


# ============================================================
# 3. EMAIL DE VALIDATION DU COMPTE
# Envoyé à l'utilisateur quand l'admin valide son compte
# ============================================================
def envoyer_email_validation(utilisateur):
    """
    Notifier l'utilisateur que son compte a été validé et son rôle attribué.

    Flux :
        Admin valide + attribue rôle → Cet email est envoyé à l'utilisateur
        → L'utilisateur peut maintenant se connecter

    Args:
        utilisateur : objet Utilisateur dont le compte vient d'être validé
                      (son rôle a déjà été attribué par l'admin)
    """
    base_url = current_app.config.get('BASE_URL', 'http://127.0.0.1:5000')
    lien_connexion = f"{base_url}/auth/connexion"

    # Afficher le rôle en français selon la valeur stockée en BDD
    roles_affiches = {
        'enseignant': 'Enseignant / Manager',
        'agent': 'Agent de scolarité / RH',
        'admin': 'Administrateur'
    }
    role_affiche = roles_affiches.get(utilisateur.role, utilisateur.role)

    sujet = "Votre compte a été validé — Système de Présence"

    corps_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #27ae60;">✅ Votre compte a été validé !</h2>

        <p>Bonjour <strong>{utilisateur.prenom} {utilisateur.nom}</strong>,</p>

        <p>Votre compte a été validé par l'administrateur.
        Vous pouvez maintenant vous connecter au système.</p>

        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="background-color: #f8f9fa;">
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Email</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{utilisateur.email}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Rôle attribué</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{role_affiche}</td>
            </tr>
        </table>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{lien_connexion}"
               style="background-color: #3498db; color: white; padding: 12px 30px;
                      text-decoration: none; border-radius: 5px; font-size: 16px;">
                Se connecter maintenant
            </a>
        </div>

        <hr style="border: none; border-top: 1px solid #ecf0f1; margin: 20px 0;">
        <p style="color: #95a5a6; font-size: 12px; text-align: center;">
            Système de Gestion de Présence — Email automatique, ne pas répondre.
        </p>
    </div>
    """

    return envoyer_email(utilisateur.email, sujet, corps_html)


# ============================================================
# 4. EMAIL DE REJET DU COMPTE
# Envoyé à l'utilisateur quand l'admin rejette son compte
# ============================================================
def envoyer_email_rejet(utilisateur, raison):
    """
    Notifier l'utilisateur que sa demande de compte a été refusée.

    Flux :
        Admin rejette + saisit une raison → Cet email est envoyé à l'utilisateur

    Args:
        utilisateur : objet Utilisateur dont la demande a été rejetée
        raison (str) : raison du rejet saisie par l'admin dans l'interface
    """
    sujet = "Votre demande de compte n'a pas été approuvée — Système de Présence"

    corps_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #e74c3c;">Demande de compte non approuvée</h2>

        <p>Bonjour <strong>{utilisateur.prenom} {utilisateur.nom}</strong>,</p>

        <p>Votre demande de compte sur le Système de Gestion de Présence
        n'a pas été approuvée par l'administrateur.</p>

        <div style="background-color: #fdf2f2; border-left: 4px solid #e74c3c;
                    padding: 15px; margin: 20px 0;">
            <strong>Raison :</strong> {raison}
        </div>

        <p>Si vous pensez qu'il s'agit d'une erreur, contactez directement
        l'administrateur de votre établissement.</p>

        <hr style="border: none; border-top: 1px solid #ecf0f1; margin: 20px 0;">
        <p style="color: #95a5a6; font-size: 12px; text-align: center;">
            Système de Gestion de Présence — Email automatique, ne pas répondre.
        </p>
    </div>
    """

    return envoyer_email(utilisateur.email, sujet, corps_html)


# ============================================================
# 5. ALERTE AU DÉVELOPPEUR
# Envoyée pour les événements techniques critiques
# ============================================================
def envoyer_alerte_developpeur(type_alerte, description, details=None):
    """
    Envoyer une alerte technique au développeur (Adam).

    Quand est-ce utilisé ?
        - Erreur serveur inattendue
        - Échec d'envoi d'email
        - Compte bloqué après trop de tentatives
        - Tentative d'injection SQL détectée
        - Clonage de carte RFID détecté
        - Toute erreur critique nécessitant une intervention technique

    Args:
        type_alerte  (str) : type court de l'alerte (ex: 'ERREUR_SERVEUR', 'COMPTE_BLOQUE')
        description  (str) : description lisible de ce qui s'est passé
        details      (str) : informations techniques supplémentaires (optionnel)
                             ex: traceback d'erreur, adresse IP, etc.
    """
    # Récupérer l'email du développeur depuis la configuration
    email_developpeur = current_app.config.get('DEVELOPER_EMAIL')

    if not email_developpeur:
        return False

    # Horodatage de l'alerte en UTC
    from datetime import datetime, timezone
    horodatage = datetime.now(timezone.utc).strftime('%d/%m/%Y à %H:%M:%S UTC')

    sujet = f"🚨 ALERTE {type_alerte} — Système de Présence"

    # Ligne de détails optionnelle dans le tableau HTML
    ligne_details = ''
    if details:
        ligne_details = f"""
        <tr>
            <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Détails techniques</strong></td>
            <td style="padding: 10px; border: 1px solid #dee2e6;"><pre style="margin:0;">{details}</pre></td>
        </tr>
        """

    corps_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #e74c3c;">🚨 Alerte Technique — {type_alerte}</h2>

        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="background-color: #fdf2f2;">
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Type d'alerte</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{type_alerte}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Horodatage</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{horodatage}</td>
            </tr>
            <tr style="background-color: #fdf2f2;">
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Description</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{description}</td>
            </tr>
            {ligne_details}
        </table>

        <hr style="border: none; border-top: 1px solid #ecf0f1; margin: 20px 0;">
        <p style="color: #95a5a6; font-size: 12px; text-align: center;">
            Système de Gestion de Présence — Alerte automatique développeur.
        </p>
    </div>
    """

    return envoyer_email(email_developpeur, sujet, corps_html)