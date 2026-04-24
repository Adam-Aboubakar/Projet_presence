"""
routes.py — Routes d'authentification
======================================
Contient toutes les routes liées à l'authentification :
  1. /auth/inscription        — Inscription d'un nouvel utilisateur
  2. /auth/verification/<token> — Vérification de l'email
  3. /auth/connexion          — Connexion à l'interface
  4. /auth/deconnexion        — Déconnexion
  5. /auth/attente            — Page d'attente validation admin
  6. /auth/renvoyer-email     — Renvoi de l'email de vérification
"""

from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
# Nouveau — importer depuis app
from app import bcrypt
from datetime import datetime, timezone, timedelta
import secrets

from app import db
from app.models import Utilisateur, JournalSecurite
from app.auth import auth
from app.auth.forms import FormulaireInscription, FormulaireConnexion
from app.auth.email import (
    envoyer_email_verification,
    envoyer_notification_admin,
    envoyer_alerte_developpeur
)

 


# ============================================================
# FONCTION UTILITAIRE — Journalisation
# ============================================================
def journaliser(type_evenement, severite, description,
                destinataire='admin', utilisateur_id=None,
                adresse_ip=None, resultat=None):
    """Enregistrer un événement dans le journal de sécurité"""
    try:
        log = JournalSecurite(
            type_evenement=type_evenement,
            severite=severite,
            description=description,
            destinataire=destinataire,
            utilisateur_id=utilisateur_id,
            adresse_ip=adresse_ip or request.remote_addr,
            resultat=resultat
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Erreur journalisation : {str(e)}")


# ============================================================
# FONCTION UTILITAIRE — Générer token email
# ============================================================
def generer_token_email():
    """Générer un token unique et sécurisé pour la vérification email"""
    return secrets.token_urlsafe(32)


# ============================================================
# FONCTION UTILITAIRE — Charger l'utilisateur pour Flask-Login
# ============================================================
from app import login_manager

@login_manager.user_loader
def charger_utilisateur(user_id):
    """Charger l'utilisateur depuis la base de données"""
    return Utilisateur.query.get(user_id)


# ============================================================
# 1. INSCRIPTION
# ============================================================
@auth.route('/inscription', methods=['GET', 'POST'])
def inscription():
    """
    Page d'inscription pour les nouveaux utilisateurs.
    Accessible uniquement aux non-connectés.
    """
    # Rediriger si déjà connecté
    if current_user.is_authenticated:
        return redirect(url_for('main.tableau_de_bord'))

    formulaire = FormulaireInscription()

    if formulaire.validate_on_submit():
        try:
            # Hacher le mot de passe
            mot_de_passe_hache = bcrypt.generate_password_hash(
                formulaire.mot_de_passe.data
            ).decode('utf-8')

            # Générer le token de vérification email
            token = generer_token_email()
            expiration = datetime.now(timezone.utc) + timedelta(hours=24)

            # Créer le nouvel utilisateur
            nouvel_utilisateur = Utilisateur(
                prenom=formulaire.prenom.data.strip(),
                nom=formulaire.nom.data.strip(),
                email=formulaire.email.data.lower().strip(),
                mot_de_passe_hache=mot_de_passe_hache,
                departement=formulaire.departement.data.strip(),
                role_souhaite=formulaire.role_souhaite.data,
                statut_compte='en_attente',
                token_email=token,
                expiration_token=expiration,
                est_actif=True,
                tentatives_echouees=0,
                version=1
            )

            db.session.add(nouvel_utilisateur)
            db.session.commit()

            # Envoyer l'email de vérification
            succes_email = envoyer_email_verification(nouvel_utilisateur, token)

            if succes_email:
                # Journaliser l'inscription
                journaliser(
                    type_evenement='inscription',
                    severite='info',
                    description=f"Nouvelle inscription : {nouvel_utilisateur.email}",
                    destinataire='admin',
                    utilisateur_id=nouvel_utilisateur.id,
                    resultat='succes'
                )
                flash(
                    'Inscription réussie ! Vérifiez votre email pour confirmer votre adresse.',
                    'success'
                )
            else:
                # Email non envoyé — alerter le développeur
                envoyer_alerte_developpeur(
                    type_alerte='ERREUR_EMAIL',
                    description=f"Échec envoi email vérification à {nouvel_utilisateur.email}"
                )
                flash(
                    'Inscription réussie mais l\'email de vérification n\'a pas pu être envoyé. '
                    'Contactez l\'administrateur.',
                    'warning'
                )

            return redirect(url_for('auth.confirmation_email_envoye'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Erreur inscription : {str(e)}")

            # Alerter le développeur
            envoyer_alerte_developpeur(
                type_alerte='ERREUR_INSCRIPTION',
                description=f"Erreur lors de l'inscription",
                details=str(e)
            )
            flash('Une erreur est survenue. Veuillez réessayer.', 'danger')

    return render_template('auth/inscription.html', formulaire=formulaire)


# ============================================================
# 2. CONFIRMATION EMAIL ENVOYÉ
# ============================================================
@auth.route('/confirmation-email')
def confirmation_email_envoye():
    """Page informant l'utilisateur de vérifier son email"""
    return render_template('auth/confirmation_email.html')


# ============================================================
# 3. VÉRIFICATION EMAIL
# ============================================================
@auth.route('/verification/<token>')
def verifier_email(token):
    """
    Vérifier l'email de l'utilisateur via le token.
    Le token est valable 24 heures.
    """
    # Chercher l'utilisateur avec ce token
    utilisateur = Utilisateur.query.filter_by(token_email=token).first()

    # Token invalide
    if not utilisateur:
        journaliser(
            type_evenement='verification_email_invalide',
            severite='warning',
            description=f"Token de vérification invalide : {token[:20]}...",
            destinataire='developpeur',
            resultat='echec'
        )
        flash('Lien de vérification invalide ou déjà utilisé.', 'danger')
        return redirect(url_for('auth.connexion'))

    # Token expiré
    expiration = utilisateur.expiration_token
    if expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expiration:
        journaliser(
            type_evenement='verification_email_expire',
            severite='warning',
            description=f"Token expiré pour : {utilisateur.email}",
            destinataire='admin',
            utilisateur_id=utilisateur.id,
            resultat='echec'
        )
        flash('Ce lien de vérification a expiré. Demandez un nouveau lien.', 'warning')
        return redirect(url_for('auth.renvoyer_email_verification'))

    # Email déjà vérifié
    if utilisateur.statut_compte in ['email_verifie', 'actif']:
        flash('Votre email a déjà été vérifié.', 'info')
        return redirect(url_for('auth.connexion'))

    # Mettre à jour le statut
    utilisateur.statut_compte = 'email_verifie'
    utilisateur.token_email = None
    utilisateur.expiration_token = None
    db.session.commit()

    # Journaliser
    journaliser(
        type_evenement='verification_email_reussie',
        severite='info',
        description=f"Email vérifié : {utilisateur.email}",
        destinataire='admin',
        utilisateur_id=utilisateur.id,
        resultat='succes'
    )

    # Notifier l'admin
    envoyer_notification_admin(utilisateur)

    flash(
        'Email vérifié avec succès ! Votre demande est en attente de validation par l\'administrateur.',
        'success'
    )
    return redirect(url_for('auth.attente'))


# ============================================================
# 4. RENVOI EMAIL DE VÉRIFICATION
# ============================================================
@auth.route('/renvoyer-email', methods=['GET', 'POST'])
def renvoyer_email_verification():
    """
    Permettre à l'utilisateur de demander un nouveau email de vérification
    si le précédent a expiré.
    """
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()

        utilisateur = Utilisateur.query.filter_by(email=email).first()

        if utilisateur and utilisateur.statut_compte == 'en_attente':
            # Générer nouveau token
            token = generer_token_email()
            expiration = datetime.now(timezone.utc) + timedelta(hours=24)

            utilisateur.token_email = token
            utilisateur.expiration_token = expiration
            db.session.commit()

            envoyer_email_verification(utilisateur, token)

            journaliser(
                type_evenement='renvoi_email_verification',
                severite='info',
                description=f"Renvoi email vérification : {email}",
                utilisateur_id=utilisateur.id,
                resultat='succes'
            )

        # Toujours afficher le même message (sécurité — ne pas révéler si l'email existe)
        flash(
            'Si cette adresse email est enregistrée, un nouveau lien de vérification a été envoyé.',
            'info'
        )
        return redirect(url_for('auth.connexion'))

    return render_template('auth/renvoyer_email.html')


# ============================================================
# 5. CONNEXION
# ============================================================
@auth.route('/connexion', methods=['GET', 'POST'])
def connexion():
    """
    Page de connexion.
    Gère le blocage après tentatives échouées.
    """
    # Rediriger si déjà connecté
    if current_user.is_authenticated:
        return redirect(url_for('main.tableau_de_bord'))

    formulaire = FormulaireConnexion()

    if formulaire.validate_on_submit():
        email = formulaire.email.data.lower().strip()
        mot_de_passe = formulaire.mot_de_passe.data

        utilisateur = Utilisateur.query.filter_by(email=email).first()

        # Email inexistant — même message que mot de passe incorrect (sécurité)
        if not utilisateur:
            journaliser(
                type_evenement='connexion_echouee',
                severite='warning',
                description=f"Tentative connexion email inexistant : {email}",
                destinataire='admin',
                resultat='echec'
            )
            flash('Email ou mot de passe incorrect.', 'danger')
            return render_template('auth/connexion.html', formulaire=formulaire)

        # Compte bloqué après trop de tentatives
        config = current_app.config
        max_tentatives = int(config.get('MAX_ATTEMPTS', 5))

        if utilisateur.tentatives_echouees >= max_tentatives:
            journaliser(
                type_evenement='connexion_compte_bloque',
                severite='critique',
                description=f"Tentative connexion compte bloqué : {email}",
                destinataire='les_deux',
                utilisateur_id=utilisateur.id,
                resultat='bloque'
            )
            flash(
                'Votre compte a été bloqué après plusieurs tentatives échouées. '
                'Contactez l\'administrateur.',
                'danger'
            )
            return render_template('auth/connexion.html', formulaire=formulaire)

        # Vérifier le mot de passe
        if not bcrypt.check_password_hash(utilisateur.mot_de_passe_hache, mot_de_passe):
            # Incrémenter les tentatives échouées
            utilisateur.tentatives_echouees += 1
            db.session.commit()

            tentatives_restantes = max_tentatives - utilisateur.tentatives_echouees

            journaliser(
                type_evenement='connexion_echouee',
                severite='warning',
                description=f"Mot de passe incorrect pour : {email} "
                           f"({utilisateur.tentatives_echouees}/{max_tentatives} tentatives)",
                destinataire='admin',
                utilisateur_id=utilisateur.id,
                resultat='echec'
            )

            # Bloquer si max atteint
            if utilisateur.tentatives_echouees >= max_tentatives:
                utilisateur.est_actif = False
                db.session.commit()

                journaliser(
                    type_evenement='compte_bloque',
                    severite='critique',
                    description=f"Compte bloqué automatiquement : {email}",
                    destinataire='les_deux',
                    utilisateur_id=utilisateur.id,
                    resultat='bloque'
                )

                # Alerter le développeur
                envoyer_alerte_developpeur(
                    type_alerte='COMPTE_BLOQUE',
                    description=f"Compte bloqué après {max_tentatives} tentatives",
                    details=f"Email : {email}\nIP : {request.remote_addr}"
                )

                flash(
                    'Compte bloqué après trop de tentatives échouées. '
                    'Contactez l\'administrateur.',
                    'danger'
                )
            else:
                flash(
                    f'Email ou mot de passe incorrect. '
                    f'{tentatives_restantes} tentative(s) restante(s).',
                    'danger'
                )

            return render_template('auth/connexion.html', formulaire=formulaire)

        # Mot de passe correct — vérifier le statut du compte
        if not utilisateur.est_actif:
            flash(
                'Votre compte est désactivé. Contactez l\'administrateur.',
                'danger'
            )
            return render_template('auth/connexion.html', formulaire=formulaire)

        if utilisateur.statut_compte == 'en_attente':
            flash(
                'Veuillez d\'abord confirmer votre adresse email.',
                'warning'
            )
            return render_template('auth/connexion.html', formulaire=formulaire)

        if utilisateur.statut_compte == 'email_verifie':
            flash(
                'Votre compte est en attente de validation par l\'administrateur.',
                'info'
            )
            return redirect(url_for('auth.attente'))

        if utilisateur.statut_compte == 'rejete':
            flash(
                f'Votre demande de compte a été refusée. '
                f'Raison : {utilisateur.raison_rejet or "Non précisée"}',
                'danger'
            )
            return render_template('auth/connexion.html', formulaire=formulaire)

        if utilisateur.statut_compte == 'desactive':
            flash(
                'Votre compte a été désactivé. Contactez l\'administrateur.',
                'danger'
            )
            return render_template('auth/connexion.html', formulaire=formulaire)

        # Connexion réussie
        utilisateur.tentatives_echouees = 0
        utilisateur.derniere_connexion = datetime.now(timezone.utc)
        db.session.commit()

        login_user(utilisateur)

        journaliser(
            type_evenement='connexion_reussie',
            severite='info',
            description=f"Connexion réussie : {email} (rôle: {utilisateur.role})",
            destinataire='admin',
            utilisateur_id=utilisateur.id,
            resultat='succes'
        )

        # Rediriger vers la page demandée ou le tableau de bord
        page_suivante = request.args.get('next')
        if page_suivante:
            return redirect(page_suivante)

        return redirect(url_for('main.tableau_de_bord'))

    return render_template('auth/connexion.html', formulaire=formulaire)


# ============================================================
# 6. DÉCONNEXION
# ============================================================
@auth.route('/deconnexion')
@login_required
def deconnexion():
    """Déconnecter l'utilisateur et rediriger vers la page de connexion"""
    journaliser(
        type_evenement='deconnexion',
        severite='info',
        description=f"Déconnexion : {current_user.email}",
        destinataire='admin',
        utilisateur_id=current_user.id,
        resultat='succes'
    )
    logout_user()
    flash('Vous avez été déconnecté avec succès.', 'info')
    return redirect(url_for('auth.connexion'))


# ============================================================
# 7. PAGE D'ATTENTE
# ============================================================
@auth.route('/attente')
def attente():
    """
    Page affichée après vérification email.
    L'utilisateur attend la validation de l'admin.
    """
    return render_template('auth/attente.html')


# ============================================================
# 8. API REST — Vérification statut compte (pour mobile futur)
# ============================================================
@auth.route('/api/statut-compte', methods=['POST'])
def api_statut_compte():
    """
    API REST pour vérifier le statut d'un compte.
    Utilisée par l'application mobile future.
    """
    donnees = request.get_json()

    if not donnees or 'email' not in donnees:
        return jsonify({
            'succes': False,
            'message': 'Email requis.'
        }), 400

    utilisateur = Utilisateur.query.filter_by(
        email=donnees['email'].lower().strip()
    ).first()

    if not utilisateur:
        return jsonify({
            'succes': False,
            'message': 'Compte introuvable.'
        }), 404

    return jsonify({
        'succes': True,
        'statut': utilisateur.statut_compte,
        'role': utilisateur.role
    }), 200