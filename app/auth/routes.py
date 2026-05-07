"""
routes.py — Routes d'authentification
======================================
Contient toutes les routes liées à l'authentification :
  1. /auth/inscription          — Inscription d'un nouvel utilisateur
  2. /auth/confirmation-email   — Page après inscription (vérifier sa boîte mail)
  3. /auth/verification/<token> — Vérification de l'email via le token
  4. /auth/renvoyer-email       — Renvoi de l'email de vérification si expiré
  5. /auth/connexion            — Connexion à l'interface
  6. /auth/deconnexion          — Déconnexion
  7. /auth/attente              — Page d'attente validation admin
  8. /auth/api/statut-compte    — API REST : vérification statut (pour mobile futur)

Décision architecturale :
  Lors de l'inscription, l'utilisateur ne choisit plus de rôle.
  Le champ role_souhaite est mis à None — c'est l'admin qui attribue
  le rôle (enseignant ou agent) lors de la validation via son interface.
"""

from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timezone, timedelta
import secrets

from app import db, bcrypt, login_manager
from app.models import Utilisateur, JournalSecurite
from app.auth import auth
from app.auth.forms import FormulaireInscription, FormulaireConnexion
from app.auth.email import (
    envoyer_email_verification,
    envoyer_notification_admin,
    envoyer_alerte_developpeur
)


# ============================================================
# CHARGEMENT DE L'UTILISATEUR — Flask-Login
# ============================================================
@login_manager.user_loader
def charger_utilisateur(user_id):
    """
    Fonction requise par Flask-Login.
    Elle est appelée automatiquement à chaque requête pour récupérer
    l'utilisateur connecté depuis la base de données via son ID
    stocké dans le cookie de session.

    Args:
        user_id (str) : identifiant UUID de l'utilisateur

    Returns:
        Utilisateur ou None
    """
    return Utilisateur.query.get(user_id)


# ============================================================
# FONCTION UTILITAIRE — Journalisation des événements
# ============================================================
def journaliser(type_evenement, severite, description,
                destinataire='admin', utilisateur_id=None,
                adresse_ip=None, resultat=None):
    """
    Enregistrer un événement de sécurité dans la table journal_securite.

    Cette fonction est appelée après chaque action importante :
    connexion réussie, tentative échouée, inscription, etc.

    Args:
        type_evenement (str) : ex: 'connexion_reussie', 'compte_bloque'
        severite       (str) : 'info', 'warning' ou 'critique'
        description    (str) : description lisible de l'événement
        destinataire   (str) : 'admin', 'developpeur' ou 'les_deux'
        utilisateur_id (str) : ID de l'utilisateur concerné (optionnel)
        adresse_ip     (str) : IP de la requête (auto-détectée si non fournie)
        resultat       (str) : 'succes', 'echec' ou 'bloque'
    """
    try:
        log = JournalSecurite(
            type_evenement=type_evenement,
            severite=severite,
            description=description,
            destinataire=destinataire,
            utilisateur_id=utilisateur_id,
            # request.remote_addr récupère automatiquement l'IP du client
            adresse_ip=adresse_ip or request.remote_addr,
            resultat=resultat
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Erreur journalisation : {str(e)}")


# ============================================================
# FONCTION UTILITAIRE — Génération du token email
# ============================================================
def generer_token_email():
    """
    Générer un token aléatoire et sécurisé pour la vérification email.

    secrets.token_urlsafe(32) génère une chaîne de 32 octets aléatoires
    encodée en base64 URL-safe (43 caractères environ).
    Ce token est imprévisible et unique — impossible à deviner.

    Returns:
        str : token sécurisé (ex: "K3fR7mXqL9...")
    """
    return secrets.token_urlsafe(32)


# ============================================================
# 1. INSCRIPTION
# ============================================================
@auth.route('/inscription', methods=['GET', 'POST'])
def inscription():
    """
    Page d'inscription pour les nouveaux utilisateurs.

    GET  → Afficher le formulaire d'inscription vide
    POST → Traiter le formulaire soumis

    Flux après soumission :
        1. Validation du formulaire (email unique, mot de passe complexe)
        2. Hachage du mot de passe avec bcrypt
        3. Génération d'un token de vérification email (valable 24h)
        4. Création du compte avec statut 'en_attente'
           (role_souhaite = None car c'est l'admin qui attribue le rôle)
        5. Envoi de l'email de vérification
        6. Redirection vers la page de confirmation
    """
    # Si l'utilisateur est déjà connecté, le rediriger vers le tableau de bord
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    formulaire = FormulaireInscription()

    if formulaire.validate_on_submit():
        try:
            # -----------------------------------------------
            # Étape 1 : Hacher le mot de passe
            # bcrypt génère un hash sécurisé avec sel aléatoire
            # Le mot de passe en clair n'est JAMAIS stocké
            # -----------------------------------------------
            mot_de_passe_hache = bcrypt.generate_password_hash(
                formulaire.mot_de_passe.data
            ).decode('utf-8')

            # -----------------------------------------------
            # Étape 2 : Générer le token de vérification email
            # Ce token est envoyé dans le lien email
            # Il expire après 24 heures
            # -----------------------------------------------
            token = generer_token_email()
            expiration = datetime.now(timezone.utc) + timedelta(hours=24)

            # -----------------------------------------------
            # Étape 3 : Créer le compte utilisateur
            # role_souhaite = None → l'admin choisira le rôle
            # statut_compte = 'en_attente' → email non encore vérifié
            # -----------------------------------------------
            nouvel_utilisateur = Utilisateur(
                prenom=formulaire.prenom.data.strip(),
                nom=formulaire.nom.data.strip(),
                # Normaliser l'email en minuscules pour éviter les doublons
                email=formulaire.email.data.lower().strip(),
                mot_de_passe_hache=mot_de_passe_hache,
                departement=formulaire.departement.data.strip(),
                # Pas de rôle souhaité — c'est l'admin qui décide
                role_souhaite=None,
                # Statut initial : email non encore vérifié
                statut_compte='en_attente',
                # Token pour la vérification email
                token_email=token,
                expiration_token=expiration,
                est_actif=True,
                tentatives_echouees=0,
                # Version 1 pour l'Optimistic Locking
                version=1
            )

            db.session.add(nouvel_utilisateur)
            db.session.commit()

            # -----------------------------------------------
            # Étape 4 : Envoyer l'email de vérification
            # -----------------------------------------------
            succes_email = envoyer_email_verification(nouvel_utilisateur, token)

            if succes_email:
                # Journaliser l'inscription avec succès
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
                # L'email n'a pas pu être envoyé — alerter le développeur
                envoyer_alerte_developpeur(
                    type_alerte='ERREUR_EMAIL',
                    description=f"Échec envoi email vérification à {nouvel_utilisateur.email}"
                )
                flash(
                    "Inscription réussie mais l'email de vérification n'a pas pu être envoyé. "
                    "Contactez l'administrateur.",
                    'warning'
                )

            return redirect(url_for('auth.confirmation_email_envoye'))

        except Exception as e:
            # En cas d'erreur inattendue, annuler les changements en BDD
            db.session.rollback()
            current_app.logger.error(f"Erreur inscription : {str(e)}")

            # Alerter le développeur pour investigation
            envoyer_alerte_developpeur(
                type_alerte='ERREUR_INSCRIPTION',
                description="Erreur inattendue lors de l'inscription",
                details=str(e)
            )
            flash('Une erreur est survenue. Veuillez réessayer.', 'danger')

    # GET ou formulaire invalide → afficher le formulaire
    return render_template('auth/inscription.html', formulaire=formulaire)


# ============================================================
# 2. PAGE DE CONFIRMATION — EMAIL ENVOYÉ
# ============================================================
@auth.route('/confirmation-email')
def confirmation_email_envoye():
    """
    Page affichée après l'inscription réussie.
    Informe l'utilisateur qu'il doit vérifier sa boîte mail.
    """
    return render_template('auth/confirmation_email.html')


# ============================================================
# 3. VÉRIFICATION DE L'EMAIL
# ============================================================
@auth.route('/verification/<token>')
def verifier_email(token):
    """
    Route appelée quand l'utilisateur clique sur le lien dans son email.

    Le token dans l'URL est comparé à celui stocké en BDD.
    Si valide et non expiré → statut passe à 'email_verifie'
    L'admin est notifié pour valider le compte.

    Args:
        token (str) : token de vérification extrait de l'URL
    """
    # Chercher l'utilisateur correspondant à ce token
    utilisateur = Utilisateur.query.filter_by(token_email=token).first()

    # -----------------------------------------------
    # Cas 1 : Token invalide ou déjà utilisé
    # -----------------------------------------------
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

    # -----------------------------------------------
    # Cas 2 : Token expiré (plus de 24 heures)
    # -----------------------------------------------
    expiration = utilisateur.expiration_token

    # S'assurer que la date est timezone-aware pour la comparaison
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

    # -----------------------------------------------
    # Cas 3 : Email déjà vérifié (clic sur ancien lien)
    # -----------------------------------------------
    if utilisateur.statut_compte in ['email_verifie', 'actif']:
        flash('Votre email a déjà été vérifié.', 'info')
        return redirect(url_for('auth.connexion'))

    # -----------------------------------------------
    # Cas 4 : Vérification réussie
    # Mettre à jour le statut et effacer le token
    # -----------------------------------------------
    utilisateur.statut_compte = 'email_verifie'
    # Effacer le token pour qu'il ne puisse plus être utilisé
    utilisateur.token_email = None
    utilisateur.expiration_token = None
    db.session.commit()

    # Journaliser la vérification réussie
    journaliser(
        type_evenement='verification_email_reussie',
        severite='info',
        description=f"Email vérifié : {utilisateur.email}",
        destinataire='admin',
        utilisateur_id=utilisateur.id,
        resultat='succes'
    )

    # Notifier l'admin qu'il y a un nouveau compte à valider
    envoyer_notification_admin(utilisateur)

    flash(
        "Email vérifié avec succès ! Votre demande est en attente de validation par l'administrateur.",
        'success'
    )
    return redirect(url_for('auth.attente'))


# ============================================================
# 4. RENVOI DE L'EMAIL DE VÉRIFICATION
# ============================================================
@auth.route('/renvoyer-email', methods=['GET', 'POST'])
def renvoyer_email_verification():
    """
    Permettre à l'utilisateur de demander un nouveau lien de vérification
    si le précédent a expiré (après 24 heures).

    Sécurité :
        On affiche toujours le même message qu'un email existe ou non,
        pour ne pas révéler si une adresse est enregistrée dans le système.
    """
    if request.method == 'POST':
        email = request.formulaire.get('email', '').lower().strip()

        utilisateur = Utilisateur.query.filter_by(email=email).first()

        # Générer un nouveau token seulement si le compte existe
        # et est encore en statut 'en_attente' (email non vérifié)
        if utilisateur and utilisateur.statut_compte == 'en_attente':
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

        # Message identique dans tous les cas (sécurité)
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
    Page de connexion à l'interface du système.

    GET  → Afficher le formulaire de connexion
    POST → Vérifier les identifiants

    Sécurité :
        - Vérification bcrypt du mot de passe (jamais en clair)
        - Message générique en cas d'erreur (ne révèle pas si l'email existe)
        - Compteur de tentatives échouées
        - Blocage automatique après MAX_ATTEMPTS tentatives
        - Vérification du statut du compte avant autorisation
    """
    # Récupérer la config une seule fois pour tous les render_template
    from app.models import Configuration
    config = Configuration.get_config()
    # Si déjà connecté, rediriger vers le tableau de bord
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    formulaire = FormulaireConnexion()

    if formulaire.validate_on_submit():
        email = formulaire.email.data.lower().strip()
        mot_de_passe = formulaire.mot_de_passe.data

        # Chercher l'utilisateur par email
        utilisateur = Utilisateur.query.filter_by(email=email).first()

        # -----------------------------------------------
        # Cas 1 : Email inexistant
        # Message générique pour ne pas révéler si l'email existe
        # -----------------------------------------------
        if not utilisateur:
            journaliser(
                type_evenement='connexion_echouee',
                severite='warning',
                description=f"Tentative connexion email inexistant : {email}",
                destinataire='admin',
                resultat='echec'
            )
            flash('Email ou mot de passe incorrect.', 'danger')
            from app.models import Configuration
            config = Configuration.get_config()
            return render_template('auth/connexion.html', formulaire=formulaire, config=config)

        # Récupérer le nombre max de tentatives depuis la configuration
        max_tentatives = int(current_app.config.get('MAX_ATTEMPTS', 5))

        # -----------------------------------------------
        # Cas 2 : Compte déjà bloqué
        # -----------------------------------------------
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
                "Votre compte a été bloqué après plusieurs tentatives échouées. "
                "Contactez l'administrateur.",
                'danger'
            )
            return render_template('auth/connexion.html', formulaire=formulaire, config=config)

        # -----------------------------------------------
        # Cas 3 : Mot de passe incorrect
        # bcrypt.check_password_hash compare sans jamais décoder le hash
        # -----------------------------------------------
        if not bcrypt.check_password_hash(utilisateur.mot_de_passe_hache, mot_de_passe):
            # Incrémenter le compteur de tentatives échouées
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

            # Si le max est atteint, bloquer le compte automatiquement
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

                # Alerter le développeur immédiatement
                envoyer_alerte_developpeur(
                    type_alerte='COMPTE_BLOQUE',
                    description=f"Compte bloqué après {max_tentatives} tentatives échouées",
                    details=f"Email : {email}\nIP : {request.remote_addr}"
                )

                flash(
                    "Compte bloqué après trop de tentatives échouées. "
                    "Contactez l'administrateur.",
                    'danger'
                )
            else:
                # Informer l'utilisateur du nombre de tentatives restantes
                flash(
                    f'Email ou mot de passe incorrect. '
                    f'{tentatives_restantes} tentative(s) restante(s).',
                    'danger'
                )

            return render_template('auth/connexion.html', formulaire=formulaire, config=config)

        # -----------------------------------------------
        # Mot de passe correct — vérifier le statut du compte
        # -----------------------------------------------

        # Compte désactivé manuellement par l'admin
        if not utilisateur.est_actif:
            flash("Votre compte est désactivé. Contactez l'administrateur.", 'danger')
            return render_template('auth/connexion.html', formulaire=formulaire, config=config)

        # Email non encore vérifié
        if utilisateur.statut_compte == 'en_attente':
            flash("Veuillez d'abord confirmer votre adresse email.", 'warning')
            return render_template('auth/connexion.html', formulaire=formulaire, config=config)

        # Email vérifié mais compte pas encore validé par l'admin
        if utilisateur.statut_compte == 'email_verifie':
            flash("Votre compte est en attente de validation par l'administrateur.", 'info')
            return redirect(url_for('auth.attente'))

        # Compte rejeté par l'admin
        if utilisateur.statut_compte == 'rejete':
            flash(
                f"Votre demande de compte a été refusée. "
                f"Raison : {utilisateur.raison_rejet or 'Non précisée'}",
                'danger'
            )
            return render_template('auth/connexion.html', formulaire=formulaire, config=config)

        # Compte désactivé
        if utilisateur.statut_compte == 'desactive':
            flash("Votre compte a été désactivé. Contactez l'administrateur.", 'danger')
            return render_template('auth/connexion.html', formulaire=formulaire, config=config)
        # -----------------------------------------------
        # Connexion réussie !
        # Réinitialiser les tentatives et enregistrer la connexion
        # -----------------------------------------------
        utilisateur.tentatives_echouees = 0
        utilisateur.derniere_connexion = datetime.now(timezone.utc)
        db.session.commit()

        # login_user() crée la session Flask et le cookie de connexion
        login_user(utilisateur, remember=False)
        session.permanent = True
        session['derniere_activite'] = datetime.now(timezone.utc).isoformat()

        journaliser(
            type_evenement='connexion_reussie',
            severite='info',
            description=f"Connexion réussie : {email} (rôle: {utilisateur.role})",
            destinataire='admin',
            utilisateur_id=utilisateur.id,
            resultat='succes'
        )

        # Rediriger vers la page demandée (si l'utilisateur a été redirigé
        # vers la connexion depuis une page protégée) ou le tableau de bord
        page_suivante = request.args.get('next')
        if page_suivante:
            return redirect(page_suivante)

        return redirect(url_for('main.index'))

    # GET ou formulaire invalide → afficher le formulaire
    return render_template('auth/connexion.html', formulaire=formulaire, config=config)

# ============================================================
# 6. DÉCONNEXION
# ============================================================
@auth.route('/deconnexion')
@login_required  # L'utilisateur doit être connecté pour se déconnecter
def deconnexion():
    """
    Déconnecter l'utilisateur de manière sécurisée.
    Flask-Login supprime la session et le cookie de connexion.
    """
    # Journaliser avant de déconnecter (pour avoir accès à current_user)
    journaliser(
        type_evenement='deconnexion',
        severite='info',
        description=f"Déconnexion : {current_user.email}",
        destinataire='admin',
        utilisateur_id=current_user.id,
        resultat='succes'
    )

    # logout_user() supprime la session Flask
    logout_user()

    flash('Vous avez été déconnecté avec succès.', 'info')
    return redirect(url_for('auth.connexion'))


# ============================================================
# 7. PAGE D'ATTENTE
# ============================================================
@auth.route('/attente')
def attente():
    """
    Page affichée après la vérification de l'email.
    L'utilisateur est informé que sa demande est en cours de traitement
    et qu'il recevra un email quand l'admin aura validé son compte.
    """
    return render_template('auth/attente.html')


# ============================================================
# 8. API REST — Vérification du statut d'un compte
# Pour l'application mobile future
# ============================================================
@auth.route('/api/statut-compte', methods=['POST'])
def api_statut_compte():
    """
    Endpoint API REST pour vérifier le statut d'un compte utilisateur.

    Utilisé par :
        - L'application mobile future (Flutter / React Native)
        - Les tests Postman en développement

    Requête attendue (JSON) :
        { "email": "utilisateur@universite.ma" }

    Réponse en cas de succès (200) :
        { "succes": true, "statut": "actif", "role": "enseignant" }

    Réponse en cas d'erreur :
        { "succes": false, "message": "..." }
    """
    donnees = request.get_json()

    # Vérifier que le body JSON contient bien un email
    if not donnees or 'email' not in donnees:
        return jsonify({
            'succes': False,
            'message': 'Email requis.'
        }), 400

    utilisateur = Utilisateur.query.filter_by(
        email=donnees['email'].lower().strip()
    ).first()

    # Compte introuvable
    if not utilisateur:
        return jsonify({
            'succes': False,
            'message': 'Compte introuvable.'
        }), 404

    # Retourner le statut et le rôle
    return jsonify({
        'succes': True,
        'statut': utilisateur.statut_compte,
        'role': utilisateur.role
    }), 200

@auth.route('/langue/<string:lang>', methods=['POST'])
@login_required
def changer_langue(lang):
    from flask import session
    if lang in ['fr', 'ar', 'en']:
        session['langue'] = lang
    return jsonify({'succes': True})