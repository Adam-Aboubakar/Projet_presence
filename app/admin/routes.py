"""
routes.py — Routes du module Administration
=============================================
Contient toutes les routes réservées aux administrateurs :

Routes web :
  1.  GET  /admin/tableau-de-bord         — Statistiques + notifications
  2.  GET  /admin/comptes-attente         — Liste comptes en attente
  3.  POST /admin/valider/<id>            — Valider + attribuer rôle
  4.  POST /admin/rejeter/<id>            — Rejeter avec raison
  5.  GET  /admin/utilisateurs            — Liste enseignants et agents
  6.  POST /admin/desactiver/<id>         — Désactiver un compte
  7.  POST /admin/reactiver/<id>          — Réactiver un compte
  8.  POST /admin/changer-role/<id>       — Changer rôle + notifier
  9.  POST /admin/creer-admin             — Créer admin (développeur)
  10. GET  /admin/notifications           — Liste toutes les notifications
  11. POST /admin/notifications/lire/<id> — Marquer notification lue
  12. POST /admin/notifications/lire-tout — Marquer toutes lues
  13. POST /admin/contacter/<id>          — Contacter un autre admin

Routes API REST :
  14. GET  /api/admin/statistiques            — Stats tableau de bord JSON
  15. GET  /api/admin/comptes-attente         — Comptes en attente JSON
  16. POST /api/admin/valider/<id>            — Validation JSON
  17. GET  /api/admin/utilisateurs            — Liste utilisateurs JSON
  18. GET  /api/admin/notifications           — Notifications JSON
  19. POST /api/admin/notifications/lire/<id> — Marquer lue JSON

Sécurité :
  - Toutes les routes web sont protégées par @role_requis('admin')
  - Toutes les routes API sont protégées par @api_role_requis('admin')
  - Un admin ne peut pas agir sur lui-même
  - Un admin ne peut pas agir sur un autre admin
  - L'Optimistic Locking empêche les conflits entre admins simultanés
"""

from flask import request, jsonify, redirect, url_for, flash, render_template, current_app
from flask_login import current_user, logout_user
from datetime import datetime, timezone
import secrets

from app import db, bcrypt
from app.models import Utilisateur, Notification, JournalSecurite
from app.admin import admin
from app.auth.decorateurs import role_requis, api_role_requis
from app.admin.email import (
    envoyer_email_changement_role,
    envoyer_email_desactivation,
    envoyer_email_reactivation,
    envoyer_email_nouvel_admin,
    envoyer_email_contact_admin
)
from app.auth.email import (
    envoyer_email_validation,
    envoyer_email_rejet,
    envoyer_alerte_developpeur
)


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

def journaliser(type_evenement, severite, description,
                destinataire='admin', utilisateur_id=None,
                resultat=None):
    """
    Enregistrer un événement dans le journal de sécurité.

    Args:
        type_evenement (str) : ex: 'compte_valide', 'compte_rejete'
        severite       (str) : 'info', 'warning' ou 'critique'
        description    (str) : description lisible de l'événement
        destinataire   (str) : 'admin', 'developpeur' ou 'les_deux'
        utilisateur_id (str) : ID de l'utilisateur concerné (optionnel)
        resultat       (str) : 'succes', 'echec' ou 'bloque'
    """
    try:
        log = JournalSecurite(
            type_evenement=type_evenement,
            severite=severite,
            description=description,
            destinataire=destinataire,
            utilisateur_id=utilisateur_id,
            adresse_ip=request.remote_addr,
            resultat=resultat
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Erreur journalisation : {str(e)}")


def verifier_action_sur_admin(utilisateur_cible):
    """
    Vérifier qu'un admin ne tente pas d'agir sur un autre admin
    ou sur lui-même.

    Returns:
        tuple (bool, str) : (action_autorisee, message_erreur)
    """
    # Vérification 1 : pas d'action sur soi-même
    if utilisateur_cible.id == current_user.id:
        return False, "Vous ne pouvez pas effectuer cette action sur votre propre compte. Contactez le développeur."

    # Vérification 2 : pas d'action sur un autre admin
    if utilisateur_cible.role == 'admin':
        return False, "Action non autorisée. Les administrateurs sont indépendants."

    return True, None


def get_statistiques():
    """
    Récupérer les statistiques pour le tableau de bord admin.

    Returns:
        dict : dictionnaire contenant toutes les statistiques
    """
    from app.models import Personne, Session, Presence

    return {
        # Nombre d'admins actifs / limite
        'nombre_admins': Utilisateur.nombre_admins(),
        'limite_admins': 3,

        # Comptes en attente de validation
        'comptes_attente': Utilisateur.query.filter_by(
            statut_compte='email_verifie'
        ).count(),

        # Utilisateurs actifs (enseignants + agents)
        'utilisateurs_actifs': Utilisateur.query.filter(
            Utilisateur.statut_compte == 'actif',
            Utilisateur.role.in_(['enseignant', 'agent'])
        ).count(),

        # Utilisateurs désactivés
        'utilisateurs_desactives': Utilisateur.query.filter_by(
            statut_compte='desactive'
        ).count(),

        # Personnes dans le système (étudiants/employés)
        'nombre_personnes': Personne.query.filter_by(est_actif=True).count(),

        # Notifications non lues pour l'admin connecté
        'notifications_non_lues': Notification.compter_non_lues(current_user.id),

        # Liste des autres admins pour la section contact
        'autres_admins': Utilisateur.query.filter(
            Utilisateur.role == 'admin',
            Utilisateur.statut_compte == 'actif',
            Utilisateur.id != current_user.id
        ).all()
    }


# ============================================================
# 1. TABLEAU DE BORD
# ============================================================
@admin.route('/tableau-de-bord')
@role_requis('admin')
def tableau_de_bord():
    """
    Page principale de l'admin.
    Affiche les statistiques globales et les notifications récentes.
    """
    stats = get_statistiques()

    # Récupérer les 5 dernières notifications non lues
    notifications_recentes = Notification.query.filter_by(
        destinataire_id=current_user.id,
        est_lue=False
    ).order_by(Notification.cree_le.desc()).limit(5).all()

    return render_template(
        'admin/tableau_de_bord.html',
        stats=stats,
        notifications_recentes=notifications_recentes
    )


# ============================================================
# 2. COMPTES EN ATTENTE
# ============================================================
@admin.route('/comptes-attente')
@role_requis('admin')
def comptes_attente():
    """
    Liste des comptes avec statut = 'email_verifie'.
    Ces comptes ont vérifié leur email et attendent la validation de l'admin.
    L'admin choisit le rôle via boutons radio et valide ou rejette.
    """
    comptes = Utilisateur.query.filter_by(
        statut_compte='email_verifie'
    ).order_by(Utilisateur.cree_le.asc()).all()

    # Trier du plus ancien au plus récent (FIFO — premier arrivé, premier servi)
    return render_template(
        'admin/comptes_attente.html',
        comptes=comptes,
        stats=get_statistiques()
    )


# ============================================================
# 3. VALIDER UN COMPTE
# ============================================================
@admin.route('/valider/<string:utilisateur_id>', methods=['POST'])
@role_requis('admin')
def valider_compte(utilisateur_id):
    """
    Valider un compte en attente et lui attribuer un rôle.

    L'admin choisit le rôle via boutons radio dans le formulaire :
        ○ enseignant — Enseignant / Manager
        ○ agent      — Agent de scolarité / RH

    Sécurité :
        - Vérification Optimistic Locking (version)
        - Le compte doit être en statut 'email_verifie'
        - Le rôle doit être 'enseignant' ou 'agent'
    """
    utilisateur = Utilisateur.query.get_or_404(utilisateur_id)

    # Vérifier que le compte est bien en attente de validation
    if utilisateur.statut_compte != 'email_verifie':
        flash("Ce compte n'est plus en attente de validation.", 'warning')
        return redirect(url_for('admin.comptes_attente'))

    # Récupérer le rôle choisi par l'admin
    role_choisi = request.form.get('role')

    # Vérifier qu'un rôle a bien été sélectionné
    if not role_choisi or role_choisi not in ['enseignant', 'agent']:
        flash("Veuillez sélectionner un rôle avant de valider.", 'danger')
        return redirect(url_for('admin.comptes_attente'))

    try:
        # Mettre à jour le compte
        utilisateur.statut_compte = 'actif'
        utilisateur.role = role_choisi
        utilisateur.valide_par = current_user.id
        utilisateur.valide_le = datetime.now(timezone.utc)
        # L'Optimistic Locking incrémente automatiquement la version
        utilisateur.version += 1
        db.session.commit()

        # Envoyer email à l'utilisateur
        envoyer_email_validation(utilisateur)

        # Notifier les autres admins
        roles_affiches = {'enseignant': 'Enseignant', 'agent': 'Agent de scolarité'}
        Notification.notifier_admins(
            expediteur=current_user,
            type_notification='validation',
            titre=f"{current_user.prenom} a validé {utilisateur.nom_complet()}",
            contenu=f"Rôle attribué : {roles_affiches.get(role_choisi, role_choisi)}"
        )

        # Journaliser
        journaliser(
            type_evenement='compte_valide',
            severite='info',
            description=f"{current_user.email} a validé {utilisateur.email} comme {role_choisi}",
            utilisateur_id=utilisateur.id,
            resultat='succes'
        )

        flash(f"Compte de {utilisateur.nom_complet()} validé avec succès !", 'success')

    except Exception as e:
        db.session.rollback()

        # Vérifier si c'est un conflit Optimistic Locking
        if 'StaleDataError' in str(type(e)) or 'version' in str(e).lower():
            flash("Ce compte a déjà été traité par un autre administrateur.", 'warning')
        else:
            current_app.logger.error(f"Erreur validation compte : {str(e)}")
            flash("Une erreur est survenue. Veuillez réessayer.", 'danger')

    return redirect(url_for('admin.comptes_attente'))


# ============================================================
# 4. REJETER UN COMPTE
# ============================================================
@admin.route('/rejeter/<string:utilisateur_id>', methods=['POST'])
@role_requis('admin')
def rejeter_compte(utilisateur_id):
    """
    Rejeter un compte en attente avec une raison obligatoire.

    L'admin doit saisir une raison de rejet.
    L'utilisateur reçoit un email avec la raison.
    """
    utilisateur = Utilisateur.query.get_or_404(utilisateur_id)

    # Vérifier que le compte est bien en attente
    if utilisateur.statut_compte != 'email_verifie':
        flash("Ce compte n'est plus en attente de validation.", 'warning')
        return redirect(url_for('admin.comptes_attente'))

    # Récupérer la raison du rejet
    raison = request.form.get('raison', '').strip()

    # La raison est obligatoire
    if not raison:
        flash("Veuillez indiquer une raison de rejet.", 'danger')
        return redirect(url_for('admin.comptes_attente'))

    try:
        # Mettre à jour le compte
        utilisateur.statut_compte = 'rejete'
        utilisateur.raison_rejet = raison
        utilisateur.valide_par = current_user.id
        utilisateur.valide_le = datetime.now(timezone.utc)
        utilisateur.version += 1
        db.session.commit()

        # Envoyer email à l'utilisateur avec la raison
        envoyer_email_rejet(utilisateur, raison)

        # Notifier les autres admins
        Notification.notifier_admins(
            expediteur=current_user,
            type_notification='rejet',
            titre=f"{current_user.prenom} a rejeté la demande de {utilisateur.nom_complet()}",
            contenu=f"Raison : {raison}"
        )

        # Journaliser
        journaliser(
            type_evenement='compte_rejete',
            severite='warning',
            description=f"{current_user.email} a rejeté {utilisateur.email}. Raison : {raison}",
            utilisateur_id=utilisateur.id,
            resultat='succes'
        )

        flash(f"Demande de {utilisateur.nom_complet()} rejetée.", 'info')

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur rejet compte : {str(e)}")
        flash("Une erreur est survenue. Veuillez réessayer.", 'danger')

    return redirect(url_for('admin.comptes_attente'))


# ============================================================
# 5. LISTE DES UTILISATEURS
# ============================================================
@admin.route('/utilisateurs')
@role_requis('admin')
def liste_utilisateurs():
    """
    Liste de tous les enseignants et agents du système.
    L'admin peut voir leurs informations, changer leur rôle,
    désactiver ou réactiver leur compte.

    Note : les autres admins ne sont PAS affichés ici.
    """
    # Récupérer uniquement enseignants et agents (pas les admins)
    utilisateurs = Utilisateur.query.filter(
        Utilisateur.role.in_(['enseignant', 'agent']),
    ).order_by(Utilisateur.cree_le.desc()).all()

    return render_template(
        'admin/utilisateurs.html',
        utilisateurs=utilisateurs,
        stats=get_statistiques()
    )


# ============================================================
# 6. DÉSACTIVER UN COMPTE
# ============================================================
@admin.route('/desactiver/<string:utilisateur_id>', methods=['POST'])
@role_requis('admin')
def desactiver_compte(utilisateur_id):
    """
    Désactiver le compte d'un enseignant ou agent.

    Sécurité :
        - Un admin ne peut pas désactiver son propre compte
        - Un admin ne peut pas désactiver un autre admin
        - L'utilisateur est déconnecté automatiquement
        - Un email de notification lui est envoyé
    """
    utilisateur = Utilisateur.query.get_or_404(utilisateur_id)

    # Vérifier les restrictions de sécurité
    autorise, message_erreur = verifier_action_sur_admin(utilisateur)
    if not autorise:
        flash(message_erreur, 'danger')
        return redirect(url_for('admin.liste_utilisateurs'))

    # Vérifier que le compte n'est pas déjà désactivé
    if not utilisateur.est_actif or utilisateur.statut_compte == 'desactive':
        flash("Ce compte est déjà désactivé.", 'warning')
        return redirect(url_for('admin.liste_utilisateurs'))

    try:
        # Désactiver le compte
        utilisateur.est_actif = False
        utilisateur.statut_compte = 'desactive'
        utilisateur.version += 1
        db.session.commit()

        # Envoyer email à l'utilisateur
        envoyer_email_desactivation(utilisateur)

        # Notifier les autres admins
        Notification.notifier_admins(
            expediteur=current_user,
            type_notification='desactivation',
            titre=f"{current_user.prenom} a désactivé le compte de {utilisateur.nom_complet()}",
            contenu=f"Rôle : {utilisateur.role} — Email : {utilisateur.email}"
        )

        # Journaliser
        journaliser(
            type_evenement='compte_desactive',
            severite='warning',
            description=f"{current_user.email} a désactivé {utilisateur.email}",
            utilisateur_id=utilisateur.id,
            resultat='succes'
        )

        flash(f"Compte de {utilisateur.nom_complet()} désactivé.", 'info')

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur désactivation : {str(e)}")
        flash("Une erreur est survenue.", 'danger')

    return redirect(url_for('admin.liste_utilisateurs'))


# ============================================================
# 7. RÉACTIVER UN COMPTE
# ============================================================
@admin.route('/reactiver/<string:utilisateur_id>', methods=['POST'])
@role_requis('admin')
def reactiver_compte(utilisateur_id):
    """
    Réactiver le compte d'un enseignant ou agent désactivé.

    L'utilisateur reçoit un email et peut se reconnecter.
    """
    utilisateur = Utilisateur.query.get_or_404(utilisateur_id)

    # Vérifier les restrictions de sécurité
    autorise, message_erreur = verifier_action_sur_admin(utilisateur)
    if not autorise:
        flash(message_erreur, 'danger')
        return redirect(url_for('admin.liste_utilisateurs'))

    # Vérifier que le compte est bien désactivé
    if utilisateur.est_actif and utilisateur.statut_compte == 'actif':
        flash("Ce compte est déjà actif.", 'warning')
        return redirect(url_for('admin.liste_utilisateurs'))

    try:
        # Réactiver le compte
        utilisateur.est_actif = True
        utilisateur.statut_compte = 'actif'
        utilisateur.version += 1
        db.session.commit()

        # Envoyer email à l'utilisateur
        envoyer_email_reactivation(utilisateur)

        # Notifier les autres admins
        Notification.notifier_admins(
            expediteur=current_user,
            type_notification='reactivation',
            titre=f"{current_user.prenom} a réactivé le compte de {utilisateur.nom_complet()}",
            contenu=f"Rôle : {utilisateur.role} — Email : {utilisateur.email}"
        )

        # Journaliser
        journaliser(
            type_evenement='compte_reactive',
            severite='info',
            description=f"{current_user.email} a réactivé {utilisateur.email}",
            utilisateur_id=utilisateur.id,
            resultat='succes'
        )

        flash(f"Compte de {utilisateur.nom_complet()} réactivé.", 'success')

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur réactivation : {str(e)}")
        flash("Une erreur est survenue.", 'danger')

    return redirect(url_for('admin.liste_utilisateurs'))


# ============================================================
# 8. CHANGER LE RÔLE D'UN UTILISATEUR
# ============================================================
@admin.route('/changer-role/<string:utilisateur_id>', methods=['POST'])
@role_requis('admin')
def changer_role(utilisateur_id):
    """
    Changer le rôle d'un enseignant ou agent.

    Après changement :
        - L'utilisateur est déconnecté automatiquement
        - Il reçoit un email l'informant du changement
        - À sa reconnexion il voit ses nouvelles fonctionnalités

    Sécurité :
        - Pas d'action sur soi-même
        - Pas d'action sur un autre admin
        - Le nouveau rôle doit être différent de l'ancien
    """
    utilisateur = Utilisateur.query.get_or_404(utilisateur_id)

    # Vérifier les restrictions de sécurité
    autorise, message_erreur = verifier_action_sur_admin(utilisateur)
    if not autorise:
        flash(message_erreur, 'danger')
        return redirect(url_for('admin.liste_utilisateurs'))

    # Récupérer le nouveau rôle
    nouveau_role = request.form.get('nouveau_role')

    # Vérifier que le rôle est valide
    if not nouveau_role or nouveau_role not in ['enseignant', 'agent']:
        flash("Rôle invalide.", 'danger')
        return redirect(url_for('admin.liste_utilisateurs'))

    # Vérifier que le rôle est différent de l'actuel
    if nouveau_role == utilisateur.role:
        flash("L'utilisateur a déjà ce rôle.", 'warning')
        return redirect(url_for('admin.liste_utilisateurs'))

    try:
        ancien_role = utilisateur.role

        # Mettre à jour le rôle
        utilisateur.role = nouveau_role
        utilisateur.version += 1
        db.session.commit()

        # Envoyer email à l'utilisateur
        envoyer_email_changement_role(utilisateur, ancien_role, nouveau_role)

        # Notifier les autres admins
        roles_affiches = {'enseignant': 'Enseignant', 'agent': 'Agent de scolarité'}
        Notification.notifier_admins(
            expediteur=current_user,
            type_notification='changement_role',
            titre=f"{current_user.prenom} a modifié le rôle de {utilisateur.nom_complet()}",
            contenu=f"{roles_affiches.get(ancien_role)} → {roles_affiches.get(nouveau_role)}"
        )

        # Journaliser
        journaliser(
            type_evenement='changement_role',
            severite='info',
            description=f"{current_user.email} a changé le rôle de {utilisateur.email} : {ancien_role} → {nouveau_role}",
            utilisateur_id=utilisateur.id,
            resultat='succes'
        )

        flash(
            f"Rôle de {utilisateur.nom_complet()} modifié. "
            f"Il sera déconnecté à sa prochaine requête.",
            'success'
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur changement rôle : {str(e)}")
        flash("Une erreur est survenue.", 'danger')

    return redirect(url_for('admin.liste_utilisateurs'))


# ============================================================
# 9. CRÉER UN ADMIN (DÉVELOPPEUR UNIQUEMENT)
# ============================================================
@admin.route('/creer-admin', methods=['POST'])
def creer_admin():
    """
    Créer un nouveau compte administrateur.

    Accès : développeur uniquement via token secret dans le header.
    Ce n'est PAS une route admin normale — elle est accessible
    sans être connecté mais nécessite le token secret.

    Header requis :
        X-Admin-Secret: [valeur de ADMIN_SECRET_TOKEN dans .env]

    Body JSON :
        { prenom, nom, email, departement }

    Sécurité :
        - Token secret vérifié avant tout
        - Limite de 3 admins vérifiée
        - Accessible uniquement par le développeur
    """
    # Vérifier le token secret
    token_recu = request.headers.get('X-Admin-Secret', '')
    token_attendu = current_app.config.get('ADMIN_SECRET_TOKEN', '')

    if not token_attendu or token_recu != token_attendu:
        journaliser(
            type_evenement='tentative_creation_admin_non_autorisee',
            severite='critique',
            description=f"Tentative création admin sans token valide depuis {request.remote_addr}",
            destinataire='developpeur',
            resultat='bloque'
        )
        return jsonify({
            'succes': False,
            'message': 'Accès non autorisé.'
        }), 403

    # Vérifier la limite de 3 admins
    if not Utilisateur.peut_ajouter_admin():
        return jsonify({
            'succes': False,
            'message': f"Limite de 3 admins atteinte. Actuellement : {Utilisateur.nombre_admins()}/3"
        }), 400

    donnees = request.get_json()

    # Vérifier les données requises
    champs_requis = ['prenom', 'nom', 'email', 'departement']
    for champ in champs_requis:
        if not donnees or not donnees.get(champ):
            return jsonify({
                'succes': False,
                'message': f"Champ requis manquant : {champ}"
            }), 400

    # Vérifier que l'email n'existe pas déjà
    if Utilisateur.query.filter_by(email=donnees['email'].lower()).first():
        return jsonify({
            'succes': False,
            'message': "Cette adresse email est déjà utilisée."
        }), 400

    try:
        # Générer un mot de passe temporaire sécurisé
        # Format : Lettre majuscule + minuscules + chiffres + caractère spécial
        mot_de_passe_temp = f"Admin@{secrets.token_hex(4).upper()}"
        mot_de_passe_hache = bcrypt.generate_password_hash(
            mot_de_passe_temp
        ).decode('utf-8')

        # Créer le compte admin
        nouvel_admin = Utilisateur(
            prenom=donnees['prenom'].strip(),
            nom=donnees['nom'].strip(),
            email=donnees['email'].lower().strip(),
            mot_de_passe_hache=mot_de_passe_hache,
            departement=donnees['departement'].strip(),
            role='admin',
            statut_compte='actif',
            est_actif=True,
            version=1,
            tentatives_echouees=0
        )

        db.session.add(nouvel_admin)
        db.session.commit()

        # Envoyer les identifiants par email au nouvel admin
        envoyer_email_nouvel_admin(nouvel_admin, mot_de_passe_temp)

        # Notifier les autres admins existants
        Notification.notifier_admins(
            expediteur=nouvel_admin,
            type_notification='nouvel_admin',
            titre="Un nouvel administrateur a rejoint le système",
            contenu=f"{nouvel_admin.nom_complet()} ({nouvel_admin.email})"
        )

        # Journaliser
        journaliser(
            type_evenement='nouvel_admin_cree',
            severite='info',
            description=f"Nouvel admin créé par le développeur : {nouvel_admin.email}",
            destinataire='les_deux',
            utilisateur_id=nouvel_admin.id,
            resultat='succes'
        )

        return jsonify({
            'succes': True,
            'message': f"Admin créé avec succès. Identifiants envoyés à {nouvel_admin.email}",
            'admins': f"{Utilisateur.nombre_admins()}/3"
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur création admin : {str(e)}")
        return jsonify({
            'succes': False,
            'message': "Une erreur est survenue."
        }), 500


# ============================================================
# 10. LISTE DES NOTIFICATIONS
# ============================================================
@admin.route('/notifications')
@role_requis('admin')
def liste_notifications():
    """
    Page listant toutes les notifications de l'admin connecté.
    Triées de la plus récente à la plus ancienne.
    """
    notifications = Notification.query.filter_by(
        destinataire_id=current_user.id
    ).order_by(Notification.cree_le.desc()).all()

    return render_template(
        'admin/notifications.html',
        notifications=notifications,
        stats=get_statistiques()
    )


# ============================================================
# 11. MARQUER UNE NOTIFICATION COMME LUE
# ============================================================
@admin.route('/notifications/lire/<string:notif_id>', methods=['POST'])
@role_requis('admin')
def marquer_notification_lue(notif_id):
    """
    Marquer une notification spécifique comme lue.
    """
    notification = Notification.query.get_or_404(notif_id)

    # Vérifier que la notification appartient bien à l'admin connecté
    if notification.destinataire_id != current_user.id:
        return jsonify({'succes': False, 'message': 'Non autorisé.'}), 403

    notification.marquer_lue()
    db.session.commit()

    return jsonify({
        'succes': True,
        'non_lues': Notification.compter_non_lues(current_user.id)
    }), 200


# ============================================================
# 12. MARQUER TOUTES LES NOTIFICATIONS COMME LUES
# ============================================================
@admin.route('/notifications/lire-tout', methods=['POST'])
@role_requis('admin')
def marquer_tout_lu():
    """
    Marquer toutes les notifications non lues comme lues.
    """
    Notification.query.filter_by(
        destinataire_id=current_user.id,
        est_lue=False
    ).update({
        'est_lue': True,
        'lue_le': datetime.now(timezone.utc)
    })
    db.session.commit()

    flash("Toutes les notifications ont été marquées comme lues.", 'info')
    return redirect(url_for('admin.liste_notifications'))


# ============================================================
# 13. CONTACTER UN AUTRE ADMIN
# ============================================================
@admin.route('/contacter/<string:admin_id>', methods=['POST'])
@role_requis('admin')
def contacter_admin(admin_id):
    """
    Envoyer un email à un autre administrateur.

    Utilisé pour se consulter avant une action sensible
    (changement de rôle, désactivation, etc.)
    """
    admin_destinataire = Utilisateur.query.get_or_404(admin_id)

    # Vérifier que c'est bien un admin
    if admin_destinataire.role != 'admin':
        flash("Cet utilisateur n'est pas un administrateur.", 'danger')
        return redirect(url_for('admin.tableau_de_bord'))

    # Vérifier qu'on ne s'envoie pas un email à soi-même
    if admin_destinataire.id == current_user.id:
        flash("Vous ne pouvez pas vous envoyer un email à vous-même.", 'warning')
        return redirect(url_for('admin.tableau_de_bord'))

    message = request.form.get('message', '').strip()

    if not message:
        flash("Le message ne peut pas être vide.", 'danger')
        return redirect(url_for('admin.tableau_de_bord'))

    # Envoyer l'email
    succes = envoyer_email_contact_admin(current_user, admin_destinataire, message)

    if succes:
        flash(f"Message envoyé à {admin_destinataire.nom_complet()}.", 'success')
    else:
        flash("Erreur lors de l'envoi du message.", 'danger')

    return redirect(url_for('admin.tableau_de_bord'))


# ============================================================
# API REST — 14. STATISTIQUES
# ============================================================
@admin.route('/api/statistiques')
@api_role_requis('admin')
def api_statistiques():
    """
    API REST — Statistiques du tableau de bord.
    Utilisée par l'application mobile future.
    """
    stats = get_statistiques()

    return jsonify({
        'succes': True,
        'statistiques': {
            'admins': f"{stats['nombre_admins']}/{stats['limite_admins']}",
            'comptes_attente': stats['comptes_attente'],
            'utilisateurs_actifs': stats['utilisateurs_actifs'],
            'utilisateurs_desactives': stats['utilisateurs_desactives'],
            'nombre_personnes': stats['nombre_personnes'],
            'notifications_non_lues': stats['notifications_non_lues']
        }
    }), 200


# ============================================================
# API REST — 15. COMPTES EN ATTENTE
# ============================================================
@admin.route('/api/comptes-attente')
@api_role_requis('admin')
def api_comptes_attente():
    """
    API REST — Liste des comptes en attente de validation.
    """
    comptes = Utilisateur.query.filter_by(
        statut_compte='email_verifie'
    ).order_by(Utilisateur.cree_le.asc()).all()

    return jsonify({
        'succes': True,
        'total': len(comptes),
        'comptes': [
            {
                'id': u.id,
                'nom_complet': u.nom_complet(),
                'email': u.email,
                'departement': u.departement,
                'cree_le': u.cree_le.isoformat() if u.cree_le else None
            }
            for u in comptes
        ]
    }), 200


# ============================================================
# API REST — 16. VALIDER UN COMPTE
# ============================================================
@admin.route('/api/valider/<string:utilisateur_id>', methods=['POST'])
@api_role_requis('admin')
def api_valider_compte(utilisateur_id):
    """
    API REST — Valider un compte et attribuer un rôle.

    Body JSON :
        { "role": "enseignant" ou "agent" }
    """
    utilisateur = Utilisateur.query.get_or_404(utilisateur_id)

    if utilisateur.statut_compte != 'email_verifie':
        return jsonify({
            'succes': False,
            'message': "Ce compte n'est plus en attente."
        }), 400

    donnees = request.get_json()
    role_choisi = donnees.get('role') if donnees else None

    if not role_choisi or role_choisi not in ['enseignant', 'agent']:
        return jsonify({
            'succes': False,
            'message': "Rôle invalide. Choisissez 'enseignant' ou 'agent'."
        }), 400

    try:
        utilisateur.statut_compte = 'actif'
        utilisateur.role = role_choisi
        utilisateur.valide_par = current_user.id
        utilisateur.valide_le = datetime.now(timezone.utc)
        utilisateur.version += 1
        db.session.commit()

        envoyer_email_validation(utilisateur)

        Notification.notifier_admins(
            expediteur=current_user,
            type_notification='validation',
            titre=f"{current_user.prenom} a validé {utilisateur.nom_complet()}",
            contenu=f"Rôle : {role_choisi}"
        )

        return jsonify({
            'succes': True,
            'message': f"Compte validé avec le rôle {role_choisi}."
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'succes': False,
            'message': "Erreur lors de la validation."
        }), 500


# ============================================================
# API REST — 17. LISTE DES UTILISATEURS
# ============================================================
@admin.route('/api/utilisateurs')
@api_role_requis('admin')
def api_utilisateurs():
    """
    API REST — Liste des enseignants et agents.
    """
    utilisateurs = Utilisateur.query.filter(
        Utilisateur.role.in_(['enseignant', 'agent'])
    ).order_by(Utilisateur.cree_le.desc()).all()

    return jsonify({
        'succes': True,
        'total': len(utilisateurs),
        'utilisateurs': [
            {
                'id': u.id,
                'nom_complet': u.nom_complet(),
                'email': u.email,
                'role': u.role,
                'departement': u.departement,
                'statut_compte': u.statut_compte,
                'est_actif': u.est_actif,
                'derniere_connexion': u.derniere_connexion.isoformat() if u.derniere_connexion else None
            }
            for u in utilisateurs
        ]
    }), 200


# ============================================================
# API REST — 18. NOTIFICATIONS
# ============================================================
@admin.route('/api/notifications')
@api_role_requis('admin')
def api_notifications():
    """
    API REST — Notifications de l'admin connecté.
    """
    notifications = Notification.query.filter_by(
        destinataire_id=current_user.id
    ).order_by(Notification.cree_le.desc()).limit(20).all()

    return jsonify({
        'succes': True,
        'non_lues': Notification.compter_non_lues(current_user.id),
        'notifications': [
            {
                'id': n.id,
                'type': n.type_notification,
                'titre': n.titre,
                'contenu': n.contenu,
                'est_lue': n.est_lue,
                'cree_le': n.cree_le.isoformat() if n.cree_le else None
            }
            for n in notifications
        ]
    }), 200


# ============================================================
# API REST — 19. MARQUER NOTIFICATION LUE
# ============================================================
@admin.route('/api/notifications/lire/<string:notif_id>', methods=['POST'])
@api_role_requis('admin')
def api_marquer_notification_lue(notif_id):
    """
    API REST — Marquer une notification comme lue.
    """
    notification = Notification.query.get_or_404(notif_id)

    if notification.destinataire_id != current_user.id:
        return jsonify({'succes': False, 'message': 'Non autorisé.'}), 403

    notification.marquer_lue()
    db.session.commit()

    return jsonify({
        'succes': True,
        'non_lues': Notification.compter_non_lues(current_user.id)
    }), 200