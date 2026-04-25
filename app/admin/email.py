"""
email.py — Emails du module Admin
===================================
Contient les fonctions d'envoi des emails spécifiques au module admin :
  1. envoyer_email_changement_role  — Notifier utilisateur que son rôle a changé
  2. envoyer_email_desactivation    — Notifier utilisateur que son compte est désactivé
  3. envoyer_email_reactivation     — Notifier utilisateur que son compte est réactivé
  4. envoyer_email_nouvel_admin     — Envoyer identifiants au nouvel admin créé
  5. envoyer_email_contact_admin    — Email entre admins (bouton "Contacter")

Différence avec auth/email.py :
  auth/email.py   → Emails liés à l'inscription et la connexion
  admin/email.py  → Emails liés aux actions administratives
"""

from flask import current_app, url_for
from flask_mail import Message
from app import mail


# ============================================================
# FONCTION UTILITAIRE — Envoi générique
# ============================================================
def envoyer_email(destinataire, sujet, corps_html, corps_texte=None):
    """
    Fonction de base pour envoyer un email.
    Identique à celle dans auth/email.py — centralisée ici
    pour éviter les imports croisés entre modules.

    Args:
        destinataire (str) : adresse email du destinataire
        sujet        (str) : sujet de l'email
        corps_html   (str) : contenu HTML
        corps_texte  (str) : contenu texte brut (optionnel)

    Returns:
        bool : True si envoyé, False sinon
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
# 1. EMAIL DE CHANGEMENT DE RÔLE
# Envoyé à l'utilisateur quand l'admin change son rôle
# ============================================================
def envoyer_email_changement_role(utilisateur, ancien_role, nouveau_role):
    """
    Notifier l'utilisateur que son rôle a été modifié par l'admin.

    Flux :
        Admin change le rôle → Cet email est envoyé → Utilisateur
        déconnecté automatiquement → Se reconnecte avec nouveau rôle

    Args:
        utilisateur  : objet Utilisateur dont le rôle a changé
        ancien_role  : rôle avant modification (ex: 'enseignant')
        nouveau_role : rôle après modification (ex: 'agent')
    """
    lien_connexion = url_for('auth.connexion', _external=True)

    # Dictionnaire pour afficher les rôles en français
    roles_affiches = {
        'enseignant': 'Enseignant / Manager',
        'agent': 'Agent de scolarité / RH',
        'admin': 'Administrateur'
    }

    ancien_role_affiche = roles_affiches.get(ancien_role, ancien_role)
    nouveau_role_affiche = roles_affiches.get(nouveau_role, nouveau_role)

    sujet = "Votre rôle a été modifié — Système de Présence"

    corps_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #e67e22;">🔄 Modification de votre rôle</h2>

        <p>Bonjour <strong>{utilisateur.prenom} {utilisateur.nom}</strong>,</p>

        <p>Votre rôle sur le Système de Gestion de Présence a été modifié
        par un administrateur.</p>

        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="background-color: #f8f9fa;">
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Ancien rôle</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6; color: #e74c3c;">{ancien_role_affiche}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Nouveau rôle</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6; color: #27ae60;">{nouveau_role_affiche}</td>
            </tr>
        </table>

        <p style="color: #7f8c8d;">
            Vous avez été déconnecté automatiquement. Veuillez vous reconnecter
            pour accéder à vos nouvelles fonctionnalités.
        </p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{lien_connexion}"
               style="background-color: #3498db; color: white; padding: 12px 30px;
                      text-decoration: none; border-radius: 5px; font-size: 16px;">
                Se reconnecter
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
# 2. EMAIL DE DÉSACTIVATION
# Envoyé à l'utilisateur quand l'admin désactive son compte
# ============================================================
def envoyer_email_desactivation(utilisateur):
    """
    Notifier l'utilisateur que son compte a été désactivé.

    Flux :
        Admin désactive → Cet email est envoyé → Utilisateur
        déconnecté automatiquement → Ne peut plus se connecter

    Args:
        utilisateur : objet Utilisateur dont le compte est désactivé
    """
    sujet = "Votre compte a été désactivé — Système de Présence"

    corps_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #e74c3c;">⛔ Compte désactivé</h2>

        <p>Bonjour <strong>{utilisateur.prenom} {utilisateur.nom}</strong>,</p>

        <p>Votre compte sur le Système de Gestion de Présence a été
        <strong>désactivé</strong> par un administrateur.</p>

        <p style="color: #7f8c8d;">
            Vous ne pouvez plus vous connecter au système.
            Si vous pensez qu'il s'agit d'une erreur, contactez
            directement l'administrateur de votre établissement.
        </p>

        <hr style="border: none; border-top: 1px solid #ecf0f1; margin: 20px 0;">
        <p style="color: #95a5a6; font-size: 12px; text-align: center;">
            Système de Gestion de Présence — Email automatique, ne pas répondre.
        </p>
    </div>
    """

    return envoyer_email(utilisateur.email, sujet, corps_html)


# ============================================================
# 3. EMAIL DE RÉACTIVATION
# Envoyé à l'utilisateur quand l'admin réactive son compte
# ============================================================
def envoyer_email_reactivation(utilisateur):
    """
    Notifier l'utilisateur que son compte a été réactivé.

    Flux :
        Admin réactive → Cet email est envoyé → Utilisateur
        peut se reconnecter normalement

    Args:
        utilisateur : objet Utilisateur dont le compte est réactivé
    """
    lien_connexion = url_for('auth.connexion', _external=True)

    sujet = "Votre compte a été réactivé — Système de Présence"

    corps_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #27ae60;">✅ Compte réactivé</h2>

        <p>Bonjour <strong>{utilisateur.prenom} {utilisateur.nom}</strong>,</p>

        <p>Votre compte sur le Système de Gestion de Présence a été
        <strong>réactivé</strong> par un administrateur.</p>

        <p>Vous pouvez maintenant vous reconnecter normalement.</p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{lien_connexion}"
               style="background-color: #27ae60; color: white; padding: 12px 30px;
                      text-decoration: none; border-radius: 5px; font-size: 16px;">
                Se connecter
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
# 4. EMAIL NOUVEL ADMIN
# Envoyé au nouvel admin avec ses identifiants de connexion
# ============================================================
def envoyer_email_nouvel_admin(nouvel_admin, mot_de_passe_temporaire):
    """
    Envoyer les identifiants de connexion au nouvel admin créé.

    Flux :
        Développeur crée admin → Cet email est envoyé au nouvel admin
        → Admin se connecte avec mot de passe temporaire
        → Admin change son mot de passe immédiatement

    Args:
        nouvel_admin             : objet Utilisateur admin nouvellement créé
        mot_de_passe_temporaire  : mot de passe généré automatiquement
    """
    lien_connexion = url_for('auth.connexion', _external=True)

    sujet = "Votre compte administrateur — Système de Présence"

    corps_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #1a5276;">👤 Compte Administrateur Créé</h2>

        <p>Bonjour <strong>{nouvel_admin.prenom} {nouvel_admin.nom}</strong>,</p>

        <p>Un compte administrateur a été créé pour vous sur le
        <strong>Système de Gestion de Présence</strong>.</p>

        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="background-color: #f8f9fa;">
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Email</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{nouvel_admin.email}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Mot de passe temporaire</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6; font-family: monospace; font-size: 16px;">
                    {mot_de_passe_temporaire}
                </td>
            </tr>
            <tr style="background-color: #f8f9fa;">
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>Rôle</strong></td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">Administrateur</td>
            </tr>
        </table>

        <div style="background-color: #fdf2f2; border-left: 4px solid #e74c3c;
                    padding: 15px; margin: 20px 0;">
            <strong>⚠️ Important :</strong> Changez votre mot de passe immédiatement
            après votre première connexion.
        </div>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{lien_connexion}"
               style="background-color: #1a5276; color: white; padding: 12px 30px;
                      text-decoration: none; border-radius: 5px; font-size: 16px;">
                Se connecter
            </a>
        </div>

        <hr style="border: none; border-top: 1px solid #ecf0f1; margin: 20px 0;">
        <p style="color: #95a5a6; font-size: 12px; text-align: center;">
            Système de Gestion de Présence — Email automatique, ne pas répondre.
        </p>
    </div>
    """

    return envoyer_email(nouvel_admin.email, sujet, corps_html)


# ============================================================
# 5. EMAIL DE CONTACT ENTRE ADMINS
# Envoyé quand un admin clique "Contacter" sur un autre admin
# ============================================================
def envoyer_email_contact_admin(admin_expediteur, admin_destinataire, message):
    """
    Permettre à un admin de contacter un autre admin par email.

    Ce bouton est disponible dans la section "Administrateurs du système"
    du tableau de bord. Il permet aux admins de se consulter avant
    d'effectuer des actions importantes.

    Args:
        admin_expediteur   : objet Utilisateur admin qui envoie le message
        admin_destinataire : objet Utilisateur admin qui reçoit le message
        message            : contenu du message saisi par l'admin
    """
    sujet = f"Message de {admin_expediteur.prenom} {admin_expediteur.nom} — Système de Présence"

    corps_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #2c3e50;">📨 Message d'un administrateur</h2>

        <p>Bonjour <strong>{admin_destinataire.prenom} {admin_destinataire.nom}</strong>,</p>

        <p>Vous avez reçu un message de votre collègue administrateur
        <strong>{admin_expediteur.prenom} {admin_expediteur.nom}</strong> :</p>

        <div style="background-color: #f8f9fa; border-left: 4px solid #3498db;
                    padding: 15px; margin: 20px 0; border-radius: 4px;">
            {message}
        </div>

        <p style="color: #7f8c8d; font-size: 14px;">
            Pour répondre, contactez directement :
            <a href="mailto:{admin_expediteur.email}">{admin_expediteur.email}</a>
        </p>

        <hr style="border: none; border-top: 1px solid #ecf0f1; margin: 20px 0;">
        <p style="color: #95a5a6; font-size: 12px; text-align: center;">
            Système de Gestion de Présence — Message envoyé via l'interface admin.
        </p>
    </div>
    """

    return envoyer_email(admin_destinataire.email, sujet, corps_html)