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
from flask_login import current_user
from datetime import datetime, timezone, date
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
)


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

def journaliser(type_evenement, severite, description,
                destinataire='admin', utilisateur_id=None,
                resultat=None):
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
    if utilisateur_cible.id == current_user.id:
        return False, "Vous ne pouvez pas effectuer cette action sur votre propre compte."
    if utilisateur_cible.role == 'admin':
        return False, "Action non autorisée. Les administrateurs sont indépendants."
    return True, None


def get_statistiques():
    """
    Statistiques pour le tableau de bord admin.
    Adaptées aux 2 modes (école / entreprise).
    """
    from app.models import Personne, Session, Presence, Configuration
    from sqlalchemy import func

    config      = Configuration.get_config()
    aujourd_hui = date.today()

    # ── Commun aux 2 modes ──────────────────────────────────
    admins_actifs          = Utilisateur.nombre_admins()
    comptes_attente        = Utilisateur.query.filter_by(statut_compte='email_verifie').count()
    utilisateurs_actifs    = Utilisateur.query.filter(
        Utilisateur.statut_compte == 'actif',
        Utilisateur.role.in_(['enseignant', 'agent'])
    ).count()
    utilisateurs_desactives = Utilisateur.query.filter_by(statut_compte='desactive').count()
    notifications_non_lues  = Notification.compter_non_lues(current_user.id)
    autres_admins           = Utilisateur.query.filter(
        Utilisateur.role == 'admin',
        Utilisateur.statut_compte == 'actif',
        Utilisateur.id != current_user.id
    ).all()

    # ── Mode École ──────────────────────────────────────────
    # Remplace tout le bloc Mode École dans get_statistiques()

    if config.mode == 'ecole':
        nb_personnes         = Personne.query.filter_by(est_actif=True).count()
        sessions_aujourd_hui = Session.query.filter(
            func.date(Session.heure_debut) == aujourd_hui
        ).count()
        sessions_en_cours    = Session.query.filter(
            func.date(Session.heure_debut) == aujourd_hui,
            Session.statut == 'en_cours'
        ).count()

        debut_mois = date(aujourd_hui.year, aujourd_hui.month, 1)
        total_p    = Presence.query.filter(
            func.date(Presence.horodatage) >= debut_mois
        ).count()
        ok_p       = Presence.query.filter(
            func.date(Presence.horodatage) >= debut_mois,
            Presence.statut.in_(['present', 'retard'])
        ).count()
        taux_presence      = round((ok_p / total_p * 100) if total_p > 0 else 0)
        absences_critiques = Presence.query.filter(
            func.date(Presence.horodatage) == aujourd_hui,
            Presence.statut == 'absent'
        ).count()

        return {
            'nombre_admins':           admins_actifs,
            'limite_admins':           3,
            'comptes_attente':         comptes_attente,
            'utilisateurs_actifs':     utilisateurs_actifs,
            'utilisateurs_desactives': utilisateurs_desactives,
            'nombre_personnes':        nb_personnes,
            'notifications_non_lues':  notifications_non_lues,
            'autres_admins':           autres_admins,
            'nb_etudiants_actifs':     nb_personnes,
            'sessions_aujourd_hui':    sessions_aujourd_hui,
            'sessions_en_cours':       sessions_en_cours,
            'taux_presence_global':    taux_presence,
            'absences_critiques':      absences_critiques,
            'admins_actifs':           admins_actifs,
        }

    # Remplace tout le bloc Mode Entreprise dans get_statistiques()

    else:
        nb_personnes          = Personne.query.filter_by(est_actif=True).count()
        pointages_aujourd_hui = Presence.query.filter(
            func.date(Presence.horodatage) == aujourd_hui
        ).count()

        debut_mois    = date(aujourd_hui.year, aujourd_hui.month, 1)
        heures_result = db.session.query(
            func.sum(Presence.heures_travaillees)
        ).filter(
            func.date(Presence.horodatage) >= debut_mois,
            Presence.heures_travaillees.isnot(None)
        ).scalar()
        heures_mois = round(heures_result or 0, 1)

        retards = Presence.query.filter(
            func.date(Presence.horodatage) == aujourd_hui,
            Presence.statut == 'retard'
        ).count()

        return {
            'nombre_admins':            admins_actifs,
            'limite_admins':            3,
            'comptes_attente':          comptes_attente,
            'utilisateurs_actifs':      utilisateurs_actifs,
            'utilisateurs_desactives':  utilisateurs_desactives,
            'nombre_personnes':         nb_personnes,
            'notifications_non_lues':   notifications_non_lues,
            'autres_admins':            autres_admins,
            'nb_employes_actifs':       nb_personnes,
            'pointages_aujourd_hui':    pointages_aujourd_hui,
            'heures_travaillees_mois':  heures_mois,
            'retards_aujourd_hui':      retards,
            'admins_actifs':            admins_actifs,
        }

def _presence_par_groupe():
    """Taux de présence groupé par groupe_ou_site (max 6 lignes)."""
    from app.models import Personne, Presence
    try:
        groupes = (
            db.session.query(Personne.groupe_ou_site)
            .filter(Personne.est_actif == True, Personne.groupe_ou_site.isnot(None))
            .distinct().all()
        )
        result = []
        for (groupe,) in groupes:
            total = Presence.query.join(Personne, Presence.personne_id == Personne.id).filter(
                Personne.groupe_ou_site == groupe
            ).count()
            ok = Presence.query.join(Personne, Presence.personne_id == Personne.id).filter(
                Personne.groupe_ou_site == groupe,
                Presence.statut.in_(['present', 'retard'])
            ).count()
            taux = round((ok / total * 100) if total > 0 else 0)
            result.append({'label': groupe, 'taux': taux})
        return result[:6]
    except Exception:
        return []


# ============================================================
# 1. TABLEAU DE BORD
# ============================================================
@admin.route('/tableau-de-bord')
@role_requis('admin')
def tableau_de_bord():
    from app.models import Configuration, JournalSecurite

    config = Configuration.get_config()
    stats  = get_statistiques()
 

    stats_par_groupe = _presence_par_groupe()

    notifications_recentes = Notification.query.filter_by(
        destinataire_id=current_user.id,
        est_lue=False
    ).order_by(Notification.cree_le.desc()).limit(5).all()

    return render_template(
        'admin/tableau_de_bord.html',
        config=config,
        stats=stats,
        stats_par_groupe=stats_par_groupe,
        notifications_recentes=notifications_recentes,
    )


# ============================================================
# 2. COMPTES EN ATTENTE
# ============================================================
@admin.route('/comptes-attente')
@role_requis('admin')
def comptes_attente():
    comptes = Utilisateur.query.filter_by(
        statut_compte='email_verifie'
    ).order_by(Utilisateur.cree_le.asc()).all()

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
    utilisateur = Utilisateur.query.get_or_404(utilisateur_id)

    if utilisateur.statut_compte != 'email_verifie':
        flash("Ce compte n'est plus en attente de validation.", 'warning')
        return redirect(url_for('admin.comptes_attente'))

    role_choisi = request.form.get('role')

    if not role_choisi or role_choisi not in ['enseignant', 'agent']:
        flash("Veuillez sélectionner un rôle avant de valider.", 'danger')
        return redirect(url_for('admin.comptes_attente'))

    try:
        utilisateur.statut_compte = 'actif'
        utilisateur.est_actif     = True
        utilisateur.role          = role_choisi
        utilisateur.valide_par    = current_user.id
        utilisateur.valide_le     = datetime.now(timezone.utc)
        utilisateur.version      += 1
        db.session.commit()

        envoyer_email_validation(utilisateur)

        roles_affiches = {'enseignant': 'Enseignant', 'agent': 'Agent de scolarité'}
        Notification.notifier_admins(
            expediteur=current_user,
            type_notification='validation',
            titre=f"{current_user.prenom} a validé {utilisateur.nom_complet()}",
            contenu=f"Rôle attribué : {roles_affiches.get(role_choisi, role_choisi)}"
        )

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
    utilisateur = Utilisateur.query.get_or_404(utilisateur_id)

    if utilisateur.statut_compte != 'email_verifie':
        flash("Ce compte n'est plus en attente de validation.", 'warning')
        return redirect(url_for('admin.comptes_attente'))

    raison = request.form.get('raison', '').strip()

    if not raison:
        flash("Veuillez indiquer une raison de rejet.", 'danger')
        return redirect(url_for('admin.comptes_attente'))

    try:
        utilisateur.statut_compte = 'rejete'
        utilisateur.est_actif     = False
        utilisateur.raison_rejet  = raison
        utilisateur.valide_par    = current_user.id
        utilisateur.valide_le     = datetime.now(timezone.utc)
        utilisateur.version      += 1
        db.session.commit()

        envoyer_email_rejet(utilisateur, raison)

        Notification.notifier_admins(
            expediteur=current_user,
            type_notification='rejet',
            titre=f"{current_user.prenom} a rejeté la demande de {utilisateur.nom_complet()}",
            contenu=f"Raison : {raison}"
        )

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
@admin.route('/utilisateurs')
@role_requis('admin')
def liste_utilisateurs():
    role_filtre = request.args.get('role', '')
    statut_filtre = request.args.get('statut', '')
    recherche = request.args.get('recherche', '').strip()

    query = Utilisateur.query.filter(
        Utilisateur.role.in_(['enseignant', 'agent'])
    )

    if role_filtre:
        query = query.filter_by(role=role_filtre)

    if statut_filtre == 'actif':
        query = query.filter_by(est_actif=True, statut_compte='actif')
    elif statut_filtre == 'desactive':
        query = query.filter(
            db.or_(
                Utilisateur.est_actif == False,
                Utilisateur.statut_compte == 'desactive'
            )
        )

    if recherche:
        query = query.filter(
            db.or_(
                Utilisateur.prenom.ilike(f'%{recherche}%'),
                Utilisateur.nom.ilike(f'%{recherche}%'),
                Utilisateur.email.ilike(f'%{recherche}%')
            )
        )

    utilisateurs = query.order_by(Utilisateur.cree_le.desc()).all()

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
    utilisateur = Utilisateur.query.get_or_404(utilisateur_id)

    autorise, message_erreur = verifier_action_sur_admin(utilisateur)
    if not autorise:
        flash(message_erreur, 'danger')
        return redirect(url_for('admin.liste_utilisateurs'))

    if not utilisateur.est_actif or utilisateur.statut_compte == 'desactive':
        flash("Ce compte est déjà désactivé.", 'warning')
        return redirect(url_for('admin.liste_utilisateurs'))

    try:
        utilisateur.est_actif     = False
        utilisateur.statut_compte = 'desactive'
        utilisateur.version      += 1
        db.session.commit()

        envoyer_email_desactivation(utilisateur)

        Notification.notifier_admins(
            expediteur=current_user,
            type_notification='desactivation',
            titre=f"{current_user.prenom} a désactivé le compte de {utilisateur.nom_complet()}",
            contenu=f"Rôle : {utilisateur.role}"
        )

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
    utilisateur = Utilisateur.query.get_or_404(utilisateur_id)

    autorise, message_erreur = verifier_action_sur_admin(utilisateur)
    if not autorise:
        flash(message_erreur, 'danger')
        return redirect(url_for('admin.liste_utilisateurs'))

    if utilisateur.est_actif and utilisateur.statut_compte == 'actif':
        flash("Ce compte est déjà actif.", 'warning')
        return redirect(url_for('admin.liste_utilisateurs'))

    try:
        utilisateur.est_actif     = True
        utilisateur.statut_compte = 'actif'
        utilisateur.version      += 1
        db.session.commit()

        envoyer_email_reactivation(utilisateur)

        Notification.notifier_admins(
            expediteur=current_user,
            type_notification='reactivation',
            titre=f"{current_user.prenom} a réactivé le compte de {utilisateur.nom_complet()}",
            contenu=f"Rôle : {utilisateur.role}"
        )

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
    utilisateur = Utilisateur.query.get_or_404(utilisateur_id)

    autorise, message_erreur = verifier_action_sur_admin(utilisateur)
    if not autorise:
        flash(message_erreur, 'danger')
        return redirect(url_for('admin.liste_utilisateurs'))

    nouveau_role = request.form.get('nouveau_role')

    if not nouveau_role or nouveau_role not in ['enseignant', 'agent']:
        flash("Rôle invalide.", 'danger')
        return redirect(url_for('admin.liste_utilisateurs'))

    if nouveau_role == utilisateur.role:
        flash("L'utilisateur a déjà ce rôle.", 'warning')
        return redirect(url_for('admin.liste_utilisateurs'))

    try:
        ancien_role      = utilisateur.role
        utilisateur.role = nouveau_role
        utilisateur.version += 1
        db.session.commit()

        envoyer_email_changement_role(utilisateur, ancien_role, nouveau_role)

        roles_affiches = {'enseignant': 'Enseignant', 'agent': 'Agent de scolarité'}
        Notification.notifier_admins(
            expediteur=current_user,
            type_notification='changement_role',
            titre=f"{current_user.prenom} a modifié le rôle de {utilisateur.nom_complet()}",
            contenu=f"{roles_affiches.get(ancien_role)} → {roles_affiches.get(nouveau_role)}"
        )

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
    token_recu    = request.headers.get('X-Admin-Secret', '')
    token_attendu = current_app.config.get('ADMIN_SECRET_TOKEN', '')

    if not token_attendu or token_recu != token_attendu:
        journaliser(
            type_evenement='tentative_creation_admin_non_autorisee',
            severite='critique',
            description=f"Tentative création admin sans token valide depuis {request.remote_addr}",
            destinataire='developpeur',
            resultat='bloque'
        )
        return jsonify({'succes': False, 'message': 'Accès non autorisé.'}), 403

    if not Utilisateur.peut_ajouter_admin():
        return jsonify({
            'succes': False,
            'message': f"Limite de 3 admins atteinte. Actuellement : {Utilisateur.nombre_admins()}/3"
        }), 400

    donnees = request.get_json()

    for champ in ['prenom', 'nom', 'email', 'departement']:
        if not donnees or not donnees.get(champ):
            return jsonify({'succes': False, 'message': f"Champ requis manquant : {champ}"}), 400

    if Utilisateur.query.filter_by(email=donnees['email'].lower()).first():
        return jsonify({'succes': False, 'message': "Cette adresse email est déjà utilisée."}), 400

    try:
        mot_de_passe_temp  = f"Admin@{secrets.token_hex(4).upper()}"
        mot_de_passe_hache = bcrypt.generate_password_hash(mot_de_passe_temp).decode('utf-8')

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

        envoyer_email_nouvel_admin(nouvel_admin, mot_de_passe_temp)

        Notification.notifier_admins(
            expediteur=nouvel_admin,
            type_notification='nouvel_admin',
            titre="Un nouvel administrateur a rejoint le système",
            contenu=f"{nouvel_admin.nom_complet()} ({nouvel_admin.email})"
        )

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
        return jsonify({'succes': False, 'message': "Une erreur est survenue."}), 500


# ============================================================
# 10. LISTE DES NOTIFICATIONS
# ============================================================
@admin.route('/notifications')
@role_requis('admin')
def liste_notifications():
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
    notification = Notification.query.get_or_404(notif_id)

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
    admin_destinataire = Utilisateur.query.get_or_404(admin_id)

    if admin_destinataire.role != 'admin':
        flash("Cet utilisateur n'est pas un administrateur.", 'danger')
        return redirect(url_for('admin.tableau_de_bord'))

    if admin_destinataire.id == current_user.id:
        flash("Vous ne pouvez pas vous envoyer un email à vous-même.", 'warning')
        return redirect(url_for('admin.tableau_de_bord'))

    message = request.form.get('message', '').strip()

    if not message:
        flash("Le message ne peut pas être vide.", 'danger')
        return redirect(url_for('admin.tableau_de_bord'))

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
    stats = get_statistiques()
    return jsonify({
        'succes': True,
        'statistiques': {
            'admins':                  f"{stats['nombre_admins']}/{stats['limite_admins']}",
            'comptes_attente':         stats['comptes_attente'],
            'utilisateurs_actifs':     stats['utilisateurs_actifs'],
            'utilisateurs_desactives': stats['utilisateurs_desactives'],
            'nombre_personnes':        stats['nombre_personnes'],
            'notifications_non_lues':  stats['notifications_non_lues']
        }
    }), 200


# ============================================================
# API REST — 15. COMPTES EN ATTENTE
# ============================================================
@admin.route('/api/comptes-attente')
@api_role_requis('admin')
def api_comptes_attente():
    comptes = Utilisateur.query.filter_by(
        statut_compte='email_verifie'
    ).order_by(Utilisateur.cree_le.asc()).all()

    return jsonify({
        'succes': True,
        'total':  len(comptes),
        'comptes': [
            {
                'id':          u.id,
                'nom_complet': u.nom_complet(),
                'email':       u.email,
                'departement': u.departement,
                'cree_le':     u.cree_le.isoformat() if u.cree_le else None
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
    utilisateur = Utilisateur.query.get_or_404(utilisateur_id)

    if utilisateur.statut_compte != 'email_verifie':
        return jsonify({'succes': False, 'message': "Ce compte n'est plus en attente."}), 400

    donnees    = request.get_json()
    role_choisi = donnees.get('role') if donnees else None

    if not role_choisi or role_choisi not in ['enseignant', 'agent']:
        return jsonify({'succes': False, 'message': "Rôle invalide. Choisissez 'enseignant' ou 'agent'."}), 400

    try:
        utilisateur.statut_compte = 'actif'
        utilisateur.est_actif     = True
        utilisateur.role          = role_choisi
        utilisateur.valide_par    = current_user.id
        utilisateur.valide_le     = datetime.now(timezone.utc)
        utilisateur.version      += 1
        db.session.commit()

        envoyer_email_validation(utilisateur)

        Notification.notifier_admins(
            expediteur=current_user,
            type_notification='validation',
            titre=f"{current_user.prenom} a validé {utilisateur.nom_complet()}",
            contenu=f"Rôle : {role_choisi}"
        )

        return jsonify({'succes': True, 'message': f"Compte validé avec le rôle {role_choisi}."}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'succes': False, 'message': "Erreur lors de la validation."}), 500


# ============================================================
# API REST — 17. LISTE DES UTILISATEURS
# ============================================================
@admin.route('/api/utilisateurs')
@api_role_requis('admin')
def api_utilisateurs():
    utilisateurs = Utilisateur.query.filter(
        Utilisateur.role.in_(['enseignant', 'agent'])
    ).order_by(Utilisateur.cree_le.desc()).all()

    return jsonify({
        'succes': True,
        'total':  len(utilisateurs),
        'utilisateurs': [
            {
                'id':                u.id,
                'nom_complet':       u.nom_complet(),
                'email':             u.email,
                'role':              u.role,
                'departement':       u.departement,
                'statut_compte':     u.statut_compte,
                'est_actif':         u.est_actif,
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
    notifications = Notification.query.filter_by(
        destinataire_id=current_user.id
    ).order_by(Notification.cree_le.desc()).limit(20).all()

    return jsonify({
        'succes':    True,
        'non_lues':  Notification.compter_non_lues(current_user.id),
        'notifications': [
            {
                'id':                n.id,
                'type':              n.type_notification,
                'titre':             n.titre,
                'contenu':           n.contenu,
                'est_lue':           n.est_lue,
                'cree_le':           n.cree_le.isoformat() if n.cree_le else None
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
    notification = Notification.query.get_or_404(notif_id)

    if notification.destinataire_id != current_user.id:
        return jsonify({'succes': False, 'message': 'Non autorisé.'}), 403

    notification.marquer_lue()
    db.session.commit()

    return jsonify({
        'succes':   True,
        'non_lues': Notification.compter_non_lues(current_user.id)
    }), 200


# ============================================================
# 20. CONFIGURATION SYSTÈME
# ============================================================
@admin.route('/configuration', methods=['GET', 'POST'])
@role_requis('admin')
def configuration():
    from app.models import Configuration
    config = Configuration.get_config()

    if request.method == 'POST':
        try:
            config.nom_etablissement      = request.form.get('nom_etablissement', '').strip()
            config.adresse                = request.form.get('adresse', '').strip()
            config.ville                  = request.form.get('ville', '').strip()
            config.telephone              = request.form.get('telephone', '').strip()
            config.site_web               = request.form.get('site_web', '').strip()
            config.domaine_email_autorise = request.form.get('domaine_email_autorise', '').strip()
            config.seuil_similarite       = float(request.form.get('seuil_similarite', 0.9))
            config.max_tentatives         = int(request.form.get('max_tentatives', 5))
            config.tolerance_retard_defaut = int(request.form.get('tolerance_retard_defaut', 15))
            config.duree_retention_jours  = int(request.form.get('duree_retention_jours', 365))
            config.langue_defaut          = request.form.get('langue_defaut', 'fr')

            if 'logo' in request.files:
                fichier = request.files['logo']
                if fichier.filename != '':
                    import os
                    from werkzeug.utils import secure_filename
                    nom_fichier = secure_filename(fichier.filename)
                    chemin = os.path.join('app', 'static', 'uploads', 'logos', nom_fichier)
                    os.makedirs(os.path.dirname(chemin), exist_ok=True)
                    fichier.save(chemin)
                    config.logo_path = f'uploads/logos/{nom_fichier}'

            db.session.commit()

            journaliser(
                type_evenement='configuration_modifiee',
                severite='info',
                description=f"{current_user.email} a modifié la configuration",
                resultat='succes'
            )

            flash('Configuration sauvegardée avec succès !', 'success')

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Erreur configuration : {str(e)}")
            flash('Erreur lors de la sauvegarde.', 'danger')

        return redirect(url_for('admin.configuration'))

    return render_template(
        'admin/configuration.html',
        config=config,
        stats=get_statistiques()
    )

# ============================================================
# SEUILS D'ABSENCES
# ============================================================
@admin.route('/seuils-absences')
@role_requis('admin')
def seuils_absences():
    from app.models import SeuilAbsence
    seuils = SeuilAbsence.query.order_by(SeuilAbsence.niveau).all()
    return render_template('admin/seuils_absences.html', seuils=seuils)


@admin.route('/seuils-absences/ajouter', methods=['POST'])
@role_requis('admin')
def ajouter_seuil():
    from app.models import SeuilAbsence
    try:
        seuil = SeuilAbsence(
            niveau=int(request.form.get('niveau')),
            nb_absences=int(request.form.get('nb_absences')),
            action=request.form.get('action'),
            sujet_email=request.form.get('sujet_email'),
            message_email=request.form.get('message_email'),
            est_actif=True
        )
        db.session.add(seuil)
        db.session.commit()
        flash('Seuil ajouté avec succès.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erreur : {str(e)}', 'danger')
    return redirect(url_for('admin.seuils_absences'))


@admin.route('/seuils-absences/<string:seuil_id>/modifier', methods=['POST'])
@role_requis('admin')
def modifier_seuil(seuil_id):
    from app.models import SeuilAbsence
    seuil = SeuilAbsence.query.get_or_404(seuil_id)
    try:
        seuil.niveau = int(request.form.get('niveau'))
        seuil.nb_absences = int(request.form.get('nb_absences'))
        seuil.action = request.form.get('action')
        seuil.sujet_email = request.form.get('sujet_email')
        seuil.message_email = request.form.get('message_email')
        seuil.est_actif = request.form.get('est_actif') == 'on'
        db.session.commit()
        flash('Seuil modifié avec succès.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erreur : {str(e)}', 'danger')
    return redirect(url_for('admin.seuils_absences'))


@admin.route('/seuils-absences/<string:seuil_id>/supprimer', methods=['POST'])
@role_requis('admin')
def supprimer_seuil(seuil_id):
    from app.models import SeuilAbsence
    seuil = SeuilAbsence.query.get_or_404(seuil_id)
    try:
        db.session.delete(seuil)
        db.session.commit()
        flash('Seuil supprimé.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erreur : {str(e)}', 'danger')
    return redirect(url_for('admin.seuils_absences'))

@admin.route('/emplois-du-temps')
@role_requis('admin')
def emplois_du_temps():
    from app.models import EmploiDuTemps, Utilisateur

    emplois = db.session.query(EmploiDuTemps).order_by(
        EmploiDuTemps.jour_semaine,
        EmploiDuTemps.heure_debut
    ).all()

    emplois_data = []
    jours = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

    for emploi in emplois:
        enseignant = Utilisateur.query.get(emploi.enseignant_id) if emploi.enseignant_id else None
        emplois_data.append({
            'id': emploi.id,
            'nom_cours': emploi.nom_cours,
            'enseignant': f'{enseignant.prenom} {enseignant.nom}' if enseignant else 'N/A',
            'groupe': emploi.groupe or 'N/A',
            'departement': emploi.departement or 'N/A',
            'niveau': emploi.niveau or 'N/A',
            'salle': emploi.salle or 'N/A',
            'jour': jours[emploi.jour_semaine] if emploi.jour_semaine < 7 else 'N/A',
            'heure_debut': emploi.heure_debut.strftime('%H:%M') if emploi.heure_debut else 'N/A',
            'heure_fin': emploi.heure_fin.strftime('%H:%M') if emploi.heure_fin else 'N/A',
            'duree': f'{int((emploi.heure_fin.hour * 60 + emploi.heure_fin.minute - emploi.heure_debut.hour * 60 - emploi.heure_debut.minute))} min' if emploi.heure_debut and emploi.heure_fin else 'N/A',
            'est_actif': emploi.est_actif,
            'date_debut': emploi.date_debut_validite.strftime('%d/%m/%Y') if emploi.date_debut_validite else 'N/A',
            'date_fin': emploi.date_fin_validite.strftime('%d/%m/%Y') if emploi.date_fin_validite else 'N/A',
        })

    return render_template('admin/emplois_du_temps.html', emplois=emplois_data)