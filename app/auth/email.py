"""
email.py — Module d'envoi des emails
=====================================
Contient les fonctions d'envoi des emails :
  1. envoyer_email_verification     — Confirmation de l'adresse email
  2. envoyer_notification_admin     — Notification à l'admin (nouveau compte)
  3. envoyer_email_validation       — Notification à l'utilisateur (compte validé)
  4. envoyer_email_rejet            — Notification à l'utilisateur (compte rejeté)
  5. envoyer_alerte_developpeur     — Alertes techniques au développeur
"""

from flask import current_app, url_for, render_template
from flask_mail import Message
from app import mail


# ============================================================
# FONCTION UTILITAIRE — Envoi générique
# ============================================================
def envoyer_email(destinataire, sujet, corps_html, corps_texte=None):
    """
    Fonction utilitaire pour envoyer un email.
    
    Args:
        destinataire : adresse email du destinataire
        sujet        : sujet de l'email
        corps_html   : contenu HTML de l'email
        corps_texte  : contenu texte brut (optionnel)
    """
    try:
        msg = Message(
            subject=sujet,
            sender=current_app.config['MAIL_DEFAULT_SENDER'],
            recipients=[destinataire]
        )
        msg.html = corps_html
        if corps_texte:
            msg.body = corps_texte
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur envoi email à {destinataire} : {str(e)}")
        return False


# ============================================================
# 1. EMAIL DE VÉRIFICATION
# Envoyé à l'utilisateur après l'inscription
# ============================================================
def envoyer_email_verification(utilisateur, token):
    """
    Envoyer l'email de vérification après l'inscription.
    L'utilisateur doit cliquer sur le lien pour confirmer son email.
    
    Args:
        utilisateur : objet Utilisateur
        token       : token de vérification unique
    """
    lien_verification = url_for(
        'auth.verifier_email',
        token=token,
        _external=True
    )

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

    corps_texte = f"""
    Bonjour {utilisateur.prenom} {utilisateur.nom},
    
    Pour confirmer votre adresse email, visitez ce lien :
    {lien_verification}
    
    Ce lien est valable pendant 24 heures.
    """

    return envoyer_email(utilisateur.email, sujet, corps_html, corps_texte)


# ============================================================
# 2. NOTIFICATION À L'ADMIN
# Envoyée à l'admin quand un nouveau compte attend validation
# ============================================================
def envoyer_notification_admin(utilisateur):
    """
    Notifier l'admin qu'un nouveau compte attend sa validation.
    
    Args:
        utilisateur : objet Utilisateur qui vient de vérifier son email
    """
    email_admin = current_app.config.get('ADMIN_EMAIL')
    if not email_admin:
        return False

    lien_admin = url_for('admin.gerer_utilisateurs', _external=True)

    role_affiche = 'Enseignant / Manager' if utilisateur.role_souhaite == 'enseignant' else 'Agent de scolarité / RH'

    sujet = f"Nouveau compte en attente de validation — {utilisateur.prenom} {utilisateur.nom}"

    corps_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #2c3e50;">Nouveau compte en attente de validation</h2>
        
        <p>Un nouveau compte a été créé et attend votre validation :</p>
        
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
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Rôle souhaité</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{role_affiche}</td>
            </tr>
        </table>
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="{lien_admin}" 
               style="background-color: #27ae60; color: white; padding: 12px 30px; 
                      text-decoration: none; border-radius: 5px; font-size: 16px;">
                Gérer les comptes en attente
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
    Notifier l'utilisateur que son compte a été validé par l'admin.
    
    Args:
        utilisateur : objet Utilisateur dont le compte vient d'être validé
    """
    lien_connexion = url_for('auth.connexion', _external=True)

    role_affiche = 'Enseignant / Manager' if utilisateur.role == 'enseignant' else 'Agent de scolarité / RH'

    sujet = "Votre compte a été validé — Système de Présence"

    corps_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #27ae60;">✅ Votre compte a été validé !</h2>
        
        <p>Bonjour <strong>{utilisateur.prenom} {utilisateur.nom}</strong>,</p>
        
        <p>Votre compte a été validé par l'administrateur. Vous pouvez maintenant 
        vous connecter au système.</p>
        
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
    Notifier l'utilisateur que son compte a été rejeté par l'admin.
    
    Args:
        utilisateur : objet Utilisateur dont le compte a été rejeté
        raison      : raison du rejet fournie par l'admin
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
    Envoyer une alerte technique au développeur.
    
    Args:
        type_alerte  : type de l'alerte (ex: 'ERREUR_SERVEUR', 'INJECTION_SQL')
        description  : description de l'alerte
        details      : détails supplémentaires (optionnel)
    """
    email_developpeur = current_app.config.get('DEVELOPER_EMAIL')
    if not email_developpeur:
        return False

    from datetime import datetime, timezone
    horodatage = datetime.now(timezone.utc).strftime('%d/%m/%Y à %H:%M:%S UTC')

    sujet = f"🚨 ALERTE {type_alerte} — Système de Présence"

    corps_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #e74c3c;">🚨 Alerte Technique — {type_alerte}</h2>
        
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="background-color: #fdf2f2;">
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Type</strong></td>
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
            {f'<tr><td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Détails</strong></td><td style="padding: 10px; border: 1px solid #dee2e6;"><pre>{details}</pre></td></tr>' if details else ''}
        </table>
        
        <hr style="border: none; border-top: 1px solid #ecf0f1; margin: 20px 0;">
        <p style="color: #95a5a6; font-size: 12px; text-align: center;">
            Système de Gestion de Présence — Alerte automatique développeur.
        </p>
    </div>
    """

    return envoyer_email(email_developpeur, sujet, corps_html)