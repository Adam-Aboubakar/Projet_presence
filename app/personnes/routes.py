"""
routes.py — Routes de gestion des personnes
=============================================
Contient toutes les routes pour gérer les personnes :
    - Mode école      → Étudiants (CNE, filière, groupe, niveau)
    - Mode entreprise → Employés (matricule, contrat, horaires)

Routes web :
  1.  GET      /personnes/                    — Liste avec filtres
  2.  GET/POST /personnes/ajouter             — Ajouter une personne
  3.  GET      /personnes/<id>                — Profil complet
  4.  GET/POST /personnes/<id>/modifier       — Modifier
  5.  POST     /personnes/<id>/desactiver     — Désactiver
  6.  POST     /personnes/<id>/reactiver      — Réactiver
  7.  GET/POST /personnes/<id>/fin-contrat    — Fin de contrat (entreprise)
  8.  GET/POST /personnes/importer            — Import Excel/CSV
  9.  GET      /personnes/template            — Télécharger template Excel

Routes API REST :
  10. GET      /personnes/api/                — Liste JSON
  11. GET      /personnes/api/<id>            — Profil JSON
  12. POST     /personnes/api/ajouter         — Ajouter JSON
  13. PUT      /personnes/api/<id>/modifier   — Modifier JSON
  14. POST     /personnes/api/<id>/desactiver — Désactiver JSON
  15. GET      /personnes/api/rechercher      — Recherche JSON

Sécurité :
  - Consultation : Admin + Agent
  - Ajout/Modification/Désactivation : Agent uniquement
  - Import : Agent uniquement
"""

from flask import request, jsonify, redirect, url_for, flash, render_template, current_app, send_file
from flask_login import current_user
from datetime import datetime, timezone, date, time
import pandas as pd
import io
import os

from app import db
from app.models import Personne, Configuration, JournalSecurite, CarteRFID
from app.personnes import personnes
from app.personnes.forms import (
    FormulairePersonneEcole,
    FormulairePersonneEntreprise,
    FormulaireImport,
    FormulaireFinContrat
)
from app.auth.decorateurs import role_requis, api_role_requis


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

def journaliser(type_evenement, severite, description,
                destinataire='admin', personne_id=None, resultat=None):
    """Enregistrer un événement dans le journal de sécurité"""
    try:
        log = JournalSecurite(
            type_evenement=type_evenement,
            severite=severite,
            description=description,
            destinataire=destinataire,
            utilisateur_id=current_user.id,
            personne_id=personne_id,
            adresse_ip=request.remote_addr,
            resultat=resultat
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Erreur journalisation : {str(e)}")


def get_mode():
    """Récupérer le mode actuel du système (ecole ou entreprise)"""
    config = Configuration.get_config()
    return config.mode if config else 'ecole'


def get_formulaire(personne_id=None):
    """
    Retourner le bon formulaire selon le mode du système.
    Mode école      → FormulairePersonneEcole
    Mode entreprise → FormulairePersonneEntreprise
    """
    if get_mode() == 'entreprise':
        return FormulairePersonneEntreprise(personne_id=personne_id)
    return FormulairePersonneEcole(personne_id=personne_id)


def personne_vers_dict(personne):
    """
    Convertir un objet Personne en dictionnaire JSON.
    Utilisé par les routes API REST.
    """
    data = {
        'id': personne.id,
        'prenom': personne.prenom,
        'nom': personne.nom,
        'nom_complet': personne.nom_complet(),
        'email': personne.email,
        'identifiant': personne.identifiant,
        'departement': personne.departement,
        'niveau_ou_poste': personne.niveau_ou_poste,
        'groupe_ou_site': personne.groupe_ou_site,
        'est_actif': personne.est_actif,
        'cree_le': personne.cree_le.isoformat() if personne.cree_le else None,
        'a_carte_rfid': personne.carte_active() is not None,
        'nombre_photos': len(personne.photos)
    }

    # Ajouter les infos contrat si mode entreprise
    if get_mode() == 'entreprise':
        data.update({
            'type_contrat': personne.type_contrat,
            'date_debut_contrat': personne.date_debut_contrat.isoformat() if personne.date_debut_contrat else None,
            'date_fin_contrat': personne.date_fin_contrat.isoformat() if personne.date_fin_contrat else None,
            'heure_arrivee': personne.heure_arrivee.strftime('%H:%M') if personne.heure_arrivee else None,
            'heure_depart': personne.heure_depart.strftime('%H:%M') if personne.heure_depart else None,
            'pause_minutes': personne.pause_minutes,
            'tolerance_retard_minutes': personne.tolerance_retard_minutes,
            'contrat_actif': personne.contrat_actif(),
            'heures_jour': personne.heures_contractuelles_jour(),
            'jours_travailles': {
                'lundi': personne.travaille_lundi,
                'mardi': personne.travaille_mardi,
                'mercredi': personne.travaille_mercredi,
                'jeudi': personne.travaille_jeudi,
                'vendredi': personne.travaille_vendredi,
                'samedi': personne.travaille_samedi,
                'dimanche': personne.travaille_dimanche
            }
        })

    return data


# ============================================================
# 1. LISTE DES PERSONNES
# ============================================================
@personnes.route('/')
@role_requis('admin', 'agent')
def liste():
    """
    Liste de toutes les personnes avec filtres de recherche.

    Filtres disponibles via paramètres URL :
        ?recherche=nom     → Recherche par nom/prénom
        ?departement=IT    → Filtrer par département
        ?groupe=G1         → Filtrer par groupe/site
        ?statut=actif      → Filtrer par statut
    """
    mode = get_mode()

    recherche = request.args.get('recherche', '').strip()
    departement = request.args.get('departement', '').strip()
    groupe = request.args.get('groupe', '').strip()
    statut = request.args.get('statut', 'tous')

    query = Personne.query

    if recherche:
        query = query.filter(
            db.or_(
                Personne.prenom.ilike(f'%{recherche}%'),
                Personne.nom.ilike(f'%{recherche}%'),
                Personne.identifiant.ilike(f'%{recherche}%')
            )
        )

    if departement:
        query = query.filter(Personne.departement.ilike(f'%{departement}%'))

    if groupe:
        query = query.filter(Personne.groupe_ou_site.ilike(f'%{groupe}%'))

    if statut == 'actif':
        query = query.filter_by(est_actif=True)
    elif statut == 'inactif':
        query = query.filter_by(est_actif=False)

    liste_personnes = query.order_by(Personne.nom.asc()).all()

    return render_template(
        'personnes/liste.html',
        personnes=liste_personnes,
        mode=mode,
        recherche=recherche,
        departement=departement,
        groupe=groupe,
        statut=statut,
        total=len(liste_personnes)
    )


# ============================================================
# 2. AJOUTER UNE PERSONNE
# ============================================================
@personnes.route('/ajouter', methods=['GET', 'POST'])
@role_requis('agent')
def ajouter():
    """
    Formulaire pour ajouter une nouvelle personne.
    Mode école      → Formulaire étudiant
    Mode entreprise → Formulaire employé avec contrat et horaires
    """
    mode = get_mode()
    formulaire = get_formulaire()

    if formulaire.validate_on_submit():
        try:
            nouvelle_personne = Personne(
                prenom=formulaire.prenom.data.strip(),
                nom=formulaire.nom.data.strip(),
                email=formulaire.email.data.lower().strip() if formulaire.email.data else None,
                identifiant=formulaire.identifiant.data.strip().upper(),
                departement=formulaire.departement.data.strip(),
                niveau_ou_poste=formulaire.niveau_ou_poste.data.strip(),
                groupe_ou_site=formulaire.groupe_ou_site.data.strip() if formulaire.groupe_ou_site.data else None,
                est_actif=True,
               # cree_par=current_user.id
               cree_par=current_user.id if current_user.is_authenticated else None
            )

            if mode == 'entreprise':
                nouvelle_personne.type_contrat = formulaire.type_contrat.data
                nouvelle_personne.date_debut_contrat = formulaire.date_debut_contrat.data
                nouvelle_personne.date_fin_contrat = formulaire.date_fin_contrat.data
                nouvelle_personne.heure_arrivee = formulaire.heure_arrivee.data
                nouvelle_personne.heure_depart = formulaire.heure_depart.data
                nouvelle_personne.pause_minutes = formulaire.pause_minutes.data
                nouvelle_personne.tolerance_retard_minutes = formulaire.tolerance_retard_minutes.data
                nouvelle_personne.travaille_lundi = formulaire.travaille_lundi.data
                nouvelle_personne.travaille_mardi = formulaire.travaille_mardi.data
                nouvelle_personne.travaille_mercredi = formulaire.travaille_mercredi.data
                nouvelle_personne.travaille_jeudi = formulaire.travaille_jeudi.data
                nouvelle_personne.travaille_vendredi = formulaire.travaille_vendredi.data
                nouvelle_personne.travaille_samedi = formulaire.travaille_samedi.data
                nouvelle_personne.travaille_dimanche = formulaire.travaille_dimanche.data

            db.session.add(nouvelle_personne)
            db.session.commit()

            journaliser(
                type_evenement='personne_ajoutee',
                severite='info',
                description=f"{current_user.email} a ajouté {nouvelle_personne.nom_complet()} ({nouvelle_personne.identifiant})",
                personne_id=nouvelle_personne.id,
                resultat='succes'
            )

            flash(
                f"{'Étudiant' if mode == 'ecole' else 'Employé'} "
                f"{nouvelle_personne.nom_complet()} ajouté avec succès ! "
                f"Associez maintenant une carte RFID et ajoutez des photos.",
                'success'
            )

            return redirect(url_for('personnes.profil', personne_id=nouvelle_personne.id))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Erreur ajout personne : {str(e)}")
            flash("Une erreur est survenue. Veuillez réessayer.", 'danger')

    return render_template(
        'personnes/formulaire.html',
        formulaire=formulaire,
        mode=mode,
        action='ajouter',
        titre=f"Ajouter un {'étudiant' if mode == 'ecole' else 'employé'}"
    )


# ============================================================
# 3. PROFIL COMPLET D'UNE PERSONNE
# ============================================================
@personnes.route('/<string:personne_id>')
@role_requis('admin', 'agent')
def profil(personne_id):
    """
    Page de profil complet d'une personne.
    Affiche informations, carte RFID, photos et historique présences.
    """
    personne = Personne.query.get_or_404(personne_id)
    mode = get_mode()

    from app.models import Presence
    dernieres_presences = Presence.query.filter_by(
        personne_id=personne_id
    ).order_by(Presence.horodatage.desc()).limit(10).all()

    return render_template(
        'personnes/profil.html',
        personne=personne,
        mode=mode,
        dernieres_presences=dernieres_presences,
        carte_active=personne.carte_active(),
        photos=personne.photos
    )


# ============================================================
# 4. MODIFIER UNE PERSONNE
# ============================================================
@personnes.route('/<string:personne_id>/modifier', methods=['GET', 'POST'])
@role_requis('agent')
def modifier(personne_id):
    """Formulaire pré-rempli pour modifier une personne existante."""
    personne = Personne.query.get_or_404(personne_id)
    mode = get_mode()
    formulaire = get_formulaire(personne_id=personne_id)

    if request.method == 'GET':
        formulaire.prenom.data = personne.prenom
        formulaire.nom.data = personne.nom
        formulaire.email.data = personne.email
        formulaire.identifiant.data = personne.identifiant
        formulaire.departement.data = personne.departement
        formulaire.niveau_ou_poste.data = personne.niveau_ou_poste
        formulaire.groupe_ou_site.data = personne.groupe_ou_site

        if mode == 'entreprise':
            formulaire.type_contrat.data = personne.type_contrat
            formulaire.date_debut_contrat.data = personne.date_debut_contrat
            formulaire.date_fin_contrat.data = personne.date_fin_contrat
            formulaire.heure_arrivee.data = personne.heure_arrivee
            formulaire.heure_depart.data = personne.heure_depart
            formulaire.pause_minutes.data = personne.pause_minutes
            formulaire.tolerance_retard_minutes.data = personne.tolerance_retard_minutes
            formulaire.travaille_lundi.data = personne.travaille_lundi
            formulaire.travaille_mardi.data = personne.travaille_mardi
            formulaire.travaille_mercredi.data = personne.travaille_mercredi
            formulaire.travaille_jeudi.data = personne.travaille_jeudi
            formulaire.travaille_vendredi.data = personne.travaille_vendredi
            formulaire.travaille_samedi.data = personne.travaille_samedi
            formulaire.travaille_dimanche.data = personne.travaille_dimanche

    if formulaire.validate_on_submit():
        try:
            personne.prenom = formulaire.prenom.data.strip()
            personne.nom = formulaire.nom.data.strip()
            personne.email = formulaire.email.data.lower().strip() if formulaire.email.data else None
            personne.identifiant = formulaire.identifiant.data.strip().upper()
            personne.departement = formulaire.departement.data.strip()
            personne.niveau_ou_poste = formulaire.niveau_ou_poste.data.strip()
            personne.groupe_ou_site = formulaire.groupe_ou_site.data.strip() if formulaire.groupe_ou_site.data else None

            if mode == 'entreprise':
                personne.type_contrat = formulaire.type_contrat.data
                personne.date_debut_contrat = formulaire.date_debut_contrat.data
                personne.date_fin_contrat = formulaire.date_fin_contrat.data
                personne.heure_arrivee = formulaire.heure_arrivee.data
                personne.heure_depart = formulaire.heure_depart.data
                personne.pause_minutes = formulaire.pause_minutes.data
                personne.tolerance_retard_minutes = formulaire.tolerance_retard_minutes.data
                personne.travaille_lundi = formulaire.travaille_lundi.data
                personne.travaille_mardi = formulaire.travaille_mardi.data
                personne.travaille_mercredi = formulaire.travaille_mercredi.data
                personne.travaille_jeudi = formulaire.travaille_jeudi.data
                personne.travaille_vendredi = formulaire.travaille_vendredi.data
                personne.travaille_samedi = formulaire.travaille_samedi.data
                personne.travaille_dimanche = formulaire.travaille_dimanche.data

            db.session.commit()

            journaliser(
                type_evenement='personne_modifiee',
                severite='info',
                description=f"{current_user.email} a modifié {personne.nom_complet()}",
                personne_id=personne.id,
                resultat='succes'
            )

            flash(f"Informations de {personne.nom_complet()} mises à jour.", 'success')
            return redirect(url_for('personnes.profil', personne_id=personne.id))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Erreur modification personne : {str(e)}")
            flash("Une erreur est survenue.", 'danger')

    return render_template(
        'personnes/formulaire.html',
        formulaire=formulaire,
        mode=mode,
        action='modifier',
        personne=personne,
        titre=f"Modifier {personne.nom_complet()}"
    )


# ============================================================
# 5. DÉSACTIVER UNE PERSONNE
# ============================================================
@personnes.route('/<string:personne_id>/desactiver', methods=['POST'])
@role_requis('agent')
def desactiver(personne_id):
    """
    Désactiver une personne.
    On ne supprime JAMAIS pour garder l'historique des présences.
    La carte RFID active est révoquée automatiquement.
    """
    personne = Personne.query.get_or_404(personne_id)

    if not personne.est_actif:
        flash(f"{personne.nom_complet()} est déjà désactivé.", 'warning')
        return redirect(url_for('personnes.profil', personne_id=personne_id))

    try:
        personne.est_actif = False

        carte = personne.carte_active()
        if carte:
            carte.revoquer(raison="Désactivation automatique — personne désactivée")

        db.session.commit()

        journaliser(
            type_evenement='personne_desactivee',
            severite='warning',
            description=f"{current_user.email} a désactivé {personne.nom_complet()} ({personne.identifiant})",
            personne_id=personne.id,
            resultat='succes'
        )

        flash(
            f"{personne.nom_complet()} désactivé. "
            f"{'Sa carte RFID a été révoquée automatiquement.' if carte else ''}",
            'info'
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur désactivation : {str(e)}")
        flash("Une erreur est survenue.", 'danger')

    return redirect(url_for('personnes.liste'))


# ============================================================
# 6. RÉACTIVER UNE PERSONNE
# ============================================================
@personnes.route('/<string:personne_id>/reactiver', methods=['POST'])
@role_requis('agent')
def reactiver(personne_id):
    """
    Réactiver une personne désactivée.
    La carte RFID n'est PAS réassociée automatiquement.
    L'agent doit associer une nouvelle carte manuellement.
    """
    personne = Personne.query.get_or_404(personne_id)

    if personne.est_actif:
        flash(f"{personne.nom_complet()} est déjà actif.", 'warning')
        return redirect(url_for('personnes.profil', personne_id=personne_id))

    try:
        personne.est_actif = True
        db.session.commit()

        journaliser(
            type_evenement='personne_reactivee',
            severite='info',
            description=f"{current_user.email} a réactivé {personne.nom_complet()}",
            personne_id=personne.id,
            resultat='succes'
        )

        flash(
            f"{personne.nom_complet()} réactivé. "
            f"N'oubliez pas d'associer une nouvelle carte RFID.",
            'success'
        )

    except Exception as e:
        db.session.rollback()
        flash("Une erreur est survenue.", 'danger')

    return redirect(url_for('personnes.profil', personne_id=personne_id))


# ============================================================
# 7. FIN DE CONTRAT — MODE ENTREPRISE
# ============================================================
@personnes.route('/<string:personne_id>/fin-contrat', methods=['GET', 'POST'])
@role_requis('agent')
def fin_contrat(personne_id):
    """
    Mettre fin au contrat d'un employé (CDI qui quitte ou CDD interrompu).
    La carte RFID est révoquée automatiquement si la date est passée.
    """
    if get_mode() != 'entreprise':
        flash("Cette fonctionnalité n'est disponible qu'en mode entreprise.", 'warning')
        return redirect(url_for('personnes.liste'))

    personne = Personne.query.get_or_404(personne_id)
    formulaire = FormulaireFinContrat()

    if formulaire.validate_on_submit():
        try:
            date_fin = formulaire.date_fin_effective.data
            personne.date_fin_contrat = date_fin

            if date_fin <= date.today():
                personne.est_actif = False
                carte = personne.carte_active()
                if carte:
                    carte.revoquer(raison="Fin de contrat")

            db.session.commit()

            journaliser(
                type_evenement='fin_contrat',
                severite='info',
                description=f"{current_user.email} a mis fin au contrat de {personne.nom_complet()} — Date : {date_fin}",
                personne_id=personne.id,
                resultat='succes'
            )

            flash(f"Fin de contrat enregistrée pour {personne.nom_complet()}.", 'success')
            return redirect(url_for('personnes.profil', personne_id=personne_id))

        except Exception as e:
            db.session.rollback()
            flash("Une erreur est survenue.", 'danger')

    return render_template(
        'personnes/fin_contrat.html',
        formulaire=formulaire,
        personne=personne
    )


# ============================================================
# 8. IMPORT EN MASSE EXCEL/CSV
# ============================================================
@personnes.route('/importer', methods=['GET', 'POST'])
@role_requis('agent')
def importer():
    """
    Importer une liste de personnes depuis un fichier Excel ou CSV.
    Rapport d'import : nombre importées + liste des erreurs.
    """
    mode = get_mode()
    formulaire = FormulaireImport()

    if formulaire.validate_on_submit():
        fichier = formulaire.fichier.data
        nom_fichier = fichier.filename.lower()
        importees = 0
        erreurs = []

        try:
            if nom_fichier.endswith('.xlsx'):
                df = pd.read_excel(fichier)
            else:
                df = pd.read_csv(fichier)

            for index, ligne in df.iterrows():
                numero_ligne = index + 2

                try:
                    prenom = str(ligne.get('prenom', '')).strip()
                    nom = str(ligne.get('nom', '')).strip()
                    identifiant = str(ligne.get('identifiant', '')).strip().upper()

                    if not prenom or prenom == 'NAN':
                        erreurs.append(f"Ligne {numero_ligne} : Prénom manquant")
                        continue
                    if not nom or nom == 'NAN':
                        erreurs.append(f"Ligne {numero_ligne} : Nom manquant")
                        continue
                    if not identifiant or identifiant == 'NAN':
                        erreurs.append(f"Ligne {numero_ligne} : Identifiant manquant")
                        continue
                    if Personne.query.filter_by(identifiant=identifiant).first():
                        erreurs.append(f"Ligne {numero_ligne} : Identifiant '{identifiant}' déjà utilisé")
                        continue

                    nouvelle_personne = Personne(
                        prenom=prenom,
                        nom=nom,
                        email=str(ligne.get('email', '')).strip().lower() or None,
                        identifiant=identifiant,
                        departement=str(ligne.get('departement', '')).strip() or None,
                        niveau_ou_poste=str(ligne.get('niveau_ou_poste', '')).strip() or None,
                        groupe_ou_site=str(ligne.get('groupe_ou_site', '')).strip() or None,
                        est_actif=True,
                       # cree_par=current_user.id
                       cree_par=current_user.id if current_user.is_authenticated else None
                    )
                    db.session.add(nouvelle_personne)
                    importees += 1

                except Exception as e:
                    erreurs.append(f"Ligne {numero_ligne} : Erreur — {str(e)}")
                    continue

            db.session.commit()

            journaliser(
                type_evenement='import_personnes',
                severite='info',
                description=f"{current_user.email} a importé {importees} personnes ({len(erreurs)} erreurs)",
                resultat='succes' if importees > 0 else 'echec'
            )

            flash(
                f"Import terminé : {importees} personnes importées, {len(erreurs)} erreur(s).",
                'success' if len(erreurs) == 0 else 'warning'
            )

            return render_template(
                'personnes/rapport_import.html',
                importees=importees,
                erreurs=erreurs,
                mode=mode
            )

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Erreur import : {str(e)}")
            flash("Erreur lors de la lecture du fichier. Vérifiez le format.", 'danger')

    return render_template('personnes/import.html', formulaire=formulaire, mode=mode)


# ============================================================
# 9. TÉLÉCHARGER LE TEMPLATE EXCEL
# ============================================================
@personnes.route('/template')
@role_requis('agent')
def telecharger_template():
    """Télécharger le template Excel vide pour l'import en masse."""
    mode = get_mode()

    if mode == 'ecole':
        colonnes = ['prenom', 'nom', 'email', 'identifiant',
                    'departement', 'niveau_ou_poste', 'groupe_ou_site']
        nom_fichier = 'template_etudiants.xlsx'
    else:
        colonnes = ['prenom', 'nom', 'email', 'identifiant',
                    'departement', 'niveau_ou_poste', 'groupe_ou_site',
                    'type_contrat', 'date_debut_contrat', 'date_fin_contrat',
                    'heure_arrivee', 'heure_depart', 'pause_minutes']
        nom_fichier = 'template_employes.xlsx'

    df = pd.DataFrame(columns=colonnes)
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Données')

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=nom_fichier,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# ============================================================
# API REST — 10. LISTE DES PERSONNES
# ============================================================
@personnes.route('/api/')
@api_role_requis('admin', 'agent')
def api_liste():
    """
    API REST — Liste des personnes avec filtres et pagination.
    URL : GET /personnes/api/?recherche=nom&page=1
    """
    recherche = request.args.get('recherche', '').strip()
    departement = request.args.get('departement', '').strip()
    statut = request.args.get('statut', 'tous')
    page = int(request.args.get('page', 1))
    par_page = int(request.args.get('par_page', 20))

    query = Personne.query

    if recherche:
        query = query.filter(
            db.or_(
                Personne.prenom.ilike(f'%{recherche}%'),
                Personne.nom.ilike(f'%{recherche}%'),
                Personne.identifiant.ilike(f'%{recherche}%')
            )
        )

    if departement:
        query = query.filter(Personne.departement.ilike(f'%{departement}%'))

    if statut == 'actif':
        query = query.filter_by(est_actif=True)
    elif statut == 'inactif':
        query = query.filter_by(est_actif=False)

    total = query.count()
    liste_personnes = query.order_by(
        Personne.nom.asc()
    ).offset((page - 1) * par_page).limit(par_page).all()

    return jsonify({
        'succes': True,
        'total': total,
        'page': page,
        'par_page': par_page,
        'pages': (total + par_page - 1) // par_page,
        'personnes': [personne_vers_dict(p) for p in liste_personnes]
    }), 200


# ============================================================
# API REST — 11. PROFIL D'UNE PERSONNE
# ============================================================
@personnes.route('/api/<string:personne_id>')
@api_role_requis('admin', 'agent')
def api_profil(personne_id):
    """
    API REST — Profil complet d'une personne.
    URL : GET /personnes/api/<id>
    """
    personne = Personne.query.get_or_404(personne_id)
    return jsonify({
        'succes': True,
        'personne': personne_vers_dict(personne)
    }), 200


# ============================================================
# API REST — 12. AJOUTER UNE PERSONNE
# ============================================================
@personnes.route('/api/ajouter', methods=['POST'])
@api_role_requis('agent')
def api_ajouter():
    """
    API REST — Ajouter une personne.
    URL : POST /personnes/api/ajouter

    Body JSON (mode école) :
        { prenom, nom, email, identifiant, departement,
          niveau_ou_poste, groupe_ou_site }

    Body JSON (mode entreprise) :
        { + type_contrat, date_debut_contrat, heure_arrivee,
            heure_depart, pause_minutes, jours_travailles }
    """
    donnees = request.get_json()
    mode = get_mode()

    if not donnees:
        return jsonify({'succes': False, 'message': 'Données JSON requises.'}), 400

    champs_requis = ['prenom', 'nom', 'identifiant', 'departement']
    for champ in champs_requis:
        if not donnees.get(champ):
            return jsonify({'succes': False, 'message': f"Champ requis : {champ}"}), 400

    if Personne.query.filter_by(identifiant=donnees['identifiant'].upper()).first():
        return jsonify({'succes': False, 'message': "Identifiant déjà utilisé."}), 400

    try:
        nouvelle_personne = Personne(
            prenom=donnees['prenom'].strip(),
            nom=donnees['nom'].strip(),
            email=donnees.get('email', '').lower().strip() or None,
            identifiant=donnees['identifiant'].strip().upper(),
            departement=donnees['departement'].strip(),
            niveau_ou_poste=donnees.get('niveau_ou_poste', '').strip() or None,
            groupe_ou_site=donnees.get('groupe_ou_site', '').strip() or None,
            est_actif=True,
           # cree_par=current_user.id
           cree_par=current_user.id if current_user.is_authenticated else None
        )

        if mode == 'entreprise':
            nouvelle_personne.type_contrat = donnees.get('type_contrat')
            if donnees.get('date_debut_contrat'):
                nouvelle_personne.date_debut_contrat = datetime.strptime(
                    donnees['date_debut_contrat'], '%Y-%m-%d'
                ).date()
            if donnees.get('heure_arrivee'):
                h, m = donnees['heure_arrivee'].split(':')
                nouvelle_personne.heure_arrivee = time(int(h), int(m))
            if donnees.get('heure_depart'):
                h, m = donnees['heure_depart'].split(':')
                nouvelle_personne.heure_depart = time(int(h), int(m))
            nouvelle_personne.pause_minutes = donnees.get('pause_minutes', 60)
            nouvelle_personne.tolerance_retard_minutes = donnees.get('tolerance_retard_minutes', 10)

            jours = donnees.get('jours_travailles', {})
            nouvelle_personne.travaille_lundi = jours.get('lundi', True)
            nouvelle_personne.travaille_mardi = jours.get('mardi', True)
            nouvelle_personne.travaille_mercredi = jours.get('mercredi', True)
            nouvelle_personne.travaille_jeudi = jours.get('jeudi', True)
            nouvelle_personne.travaille_vendredi = jours.get('vendredi', True)
            nouvelle_personne.travaille_samedi = jours.get('samedi', False)
            nouvelle_personne.travaille_dimanche = jours.get('dimanche', False)

        db.session.add(nouvelle_personne)
        db.session.commit()

        return jsonify({
            'succes': True,
            'message': 'Personne ajoutée avec succès.',
            'personne': personne_vers_dict(nouvelle_personne)
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'succes': False, 'message': str(e)}), 500


# ============================================================
# API REST — 13. MODIFIER UNE PERSONNE
# ============================================================
@personnes.route('/api/<string:personne_id>/modifier', methods=['PUT'])
@api_role_requis('agent')
def api_modifier(personne_id):
    """
    API REST — Modifier une personne existante.
    URL : PUT /personnes/api/<id>/modifier
    """
    personne = Personne.query.get_or_404(personne_id)
    donnees = request.get_json()

    if not donnees:
        return jsonify({'succes': False, 'message': 'Données JSON requises.'}), 400

    try:
        if 'prenom' in donnees:
            personne.prenom = donnees['prenom'].strip()
        if 'nom' in donnees:
            personne.nom = donnees['nom'].strip()
        if 'email' in donnees:
            personne.email = donnees['email'].lower().strip() or None
        if 'departement' in donnees:
            personne.departement = donnees['departement'].strip()
        if 'niveau_ou_poste' in donnees:
            personne.niveau_ou_poste = donnees['niveau_ou_poste'].strip()
        if 'groupe_ou_site' in donnees:
            personne.groupe_ou_site = donnees['groupe_ou_site'].strip()

        db.session.commit()

        return jsonify({
            'succes': True,
            'message': 'Personne modifiée.',
            'personne': personne_vers_dict(personne)
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'succes': False, 'message': str(e)}), 500


# ============================================================
# API REST — 14. DÉSACTIVER UNE PERSONNE
# ============================================================
@personnes.route('/api/<string:personne_id>/desactiver', methods=['POST'])
@api_role_requis('agent')
def api_desactiver(personne_id):
    """
    API REST — Désactiver une personne.
    URL : POST /personnes/api/<id>/desactiver
    """
    personne = Personne.query.get_or_404(personne_id)

    if not personne.est_actif:
        return jsonify({'succes': False, 'message': 'Personne déjà désactivée.'}), 400

    try:
        personne.est_actif = False
        carte = personne.carte_active()
        if carte:
            carte.revoquer("Désactivation automatique")
        db.session.commit()

        return jsonify({
            'succes': True,
            'message': f"{personne.nom_complet()} désactivé.",
            'carte_revoquee': carte is not None
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'succes': False, 'message': str(e)}), 500


# ============================================================
# API REST — 15. RECHERCHER DES PERSONNES
# ============================================================
@personnes.route('/api/rechercher')
@api_role_requis('admin', 'agent')
def api_rechercher():
    """
    API REST — Recherche rapide pour autocomplétion.
    URL : GET /personnes/api/rechercher?q=nom
    Minimum 2 caractères requis.
    """
    q = request.args.get('q', '').strip()

    if len(q) < 2:
        return jsonify({'succes': True, 'personnes': []}), 200

    resultats = Personne.query.filter(
        db.and_(
            Personne.est_actif == True,
            db.or_(
                Personne.prenom.ilike(f'%{q}%'),
                Personne.nom.ilike(f'%{q}%'),
                Personne.identifiant.ilike(f'%{q}%')
            )
        )
    ).limit(10).all()

    return jsonify({
        'succes': True,
        'personnes': [
            {
                'id': p.id,
                'nom_complet': p.nom_complet(),
                'identifiant': p.identifiant,
                'departement': p.departement
            }
            for p in resultats
        ]
    }), 200
