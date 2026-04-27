"""
forms.py — Formulaires de gestion des personnes
=================================================
Contient les formulaires :
  1. FormulairePersonneEcole      — Ajouter/modifier un étudiant
  2. FormulairePersonneEntreprise — Ajouter/modifier un employé
  3. FormulaireImport             — Import en masse Excel/CSV
  4. FormulaireFinContrat         — Mettre fin au contrat d'un employé

Note importante :
    Le formulaire affiché dépend du mode configuré dans Configuration.
    Mode 'ecole'      → FormulairePersonneEcole
    Mode 'entreprise' → FormulairePersonneEntreprise
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, SelectField, BooleanField,
    SubmitField, TimeField, DateField, IntegerField
)
from wtforms.validators import (
    DataRequired, Email, Length, Optional,
    ValidationError, NumberRange
)
from datetime import date, datetime, timezone
from app.models import Personne


# ============================================================
# FORMULAIRE ÉTUDIANT — MODE ÉCOLE
# ============================================================
class FormulairePersonneEcole(FlaskForm):
    """
    Formulaire pour ajouter ou modifier un étudiant.
    Utilisé uniquement en mode école.

    Rempli par : Agent de scolarité
    """

    # -------------------------------------------------------
    # Informations personnelles
    # -------------------------------------------------------
    prenom = StringField(
        'Prénom',
        validators=[
            DataRequired(message='Le prénom est obligatoire.'),
            Length(min=2, max=100)
        ]
    )

    nom = StringField(
        'Nom',
        validators=[
            DataRequired(message='Le nom est obligatoire.'),
            Length(min=2, max=100)
        ]
    )

    email = StringField(
        'Email (optionnel)',
        validators=[
            Optional(),
            Email(message="L'adresse email n'est pas valide.")
        ]
    )

    # -------------------------------------------------------
    # Identifiant académique
    # CNE = Code National Étudiant — unique par étudiant
    # -------------------------------------------------------
    identifiant = StringField(
        'CNE / Code étudiant',
        validators=[
            DataRequired(message='Le CNE est obligatoire.'),
            Length(max=100)
        ]
    )

    # -------------------------------------------------------
    # Informations académiques
    # -------------------------------------------------------
    departement = StringField(
        'Filière',
        validators=[
            DataRequired(message='La filière est obligatoire.'),
            Length(max=100)
        ]
    )

    niveau_ou_poste = StringField(
        'Niveau',
        validators=[
            DataRequired(message='Le niveau est obligatoire.'),
            Length(max=100)
        ]
    )

    groupe_ou_site = StringField(
        'Groupe',
        validators=[
            DataRequired(message='Le groupe est obligatoire.'),
            Length(max=100)
        ]
    )

    soumettre = SubmitField('Enregistrer')

    def __init__(self, personne_id=None, *args, **kwargs):
        """
        personne_id : ID de la personne en cours de modification
                      (None si c'est un ajout)
        """
        super().__init__(*args, **kwargs)
        self.personne_id = personne_id

    def validate_identifiant(self, identifiant):
        """
        Vérifier que le CNE est unique.
        Si on modifie une personne existante, on exclut son propre ID.
        """
        query = Personne.query.filter_by(identifiant=identifiant.data)
        if self.personne_id:
            query = query.filter(Personne.id != self.personne_id)
        if query.first():
            raise ValidationError('Ce CNE est déjà utilisé.')

    def validate_email(self, email):
        """Vérifier que l'email est unique si fourni"""
        if not email.data:
            return
        query = Personne.query.filter_by(email=email.data)
        if self.personne_id:
            query = query.filter(Personne.id != self.personne_id)
        if query.first():
            raise ValidationError('Cette adresse email est déjà utilisée.')


# ============================================================
# FORMULAIRE EMPLOYÉ — MODE ENTREPRISE
# ============================================================
class FormulairePersonneEntreprise(FlaskForm):
    """
    Formulaire pour ajouter ou modifier un employé.
    Utilisé uniquement en mode entreprise.

    Rempli par : Agent RH

    Inclut les informations contractuelles et les horaires
    qui permettent la génération automatique des sessions.
    """

    # -------------------------------------------------------
    # Informations personnelles
    # -------------------------------------------------------
    prenom = StringField(
        'Prénom',
        validators=[
            DataRequired(message='Le prénom est obligatoire.'),
            Length(min=2, max=100)
        ]
    )

    nom = StringField(
        'Nom',
        validators=[
            DataRequired(message='Le nom est obligatoire.'),
            Length(min=2, max=100)
        ]
    )

    email = StringField(
        'Email professionnel (optionnel)',
        validators=[
            Optional(),
            Email(message="L'adresse email n'est pas valide.")
        ]
    )

    # -------------------------------------------------------
    # Identifiant professionnel
    # -------------------------------------------------------
    identifiant = StringField(
        'Matricule / Badge',
        validators=[
            DataRequired(message='Le matricule est obligatoire.'),
            Length(max=100)
        ]
    )

    # -------------------------------------------------------
    # Informations professionnelles
    # -------------------------------------------------------
    departement = StringField(
        'Département',
        validators=[
            DataRequired(message='Le département est obligatoire.'),
            Length(max=100)
        ]
    )

    niveau_ou_poste = StringField(
        'Poste',
        validators=[
            DataRequired(message='Le poste est obligatoire.'),
            Length(max=100)
        ]
    )

    groupe_ou_site = StringField(
        'Site / Bureau',
        validators=[
            Optional(),
            Length(max=100)
        ]
    )

    # -------------------------------------------------------
    # CONTRAT DE TRAVAIL
    # -------------------------------------------------------
    type_contrat = SelectField(
        'Type de contrat',
        choices=[
            ('', '-- Choisir --'),
            ('cdi', 'CDI — Contrat à Durée Indéterminée'),
            ('cdd', 'CDD — Contrat à Durée Déterminée'),
            ('stage', 'Stage')
        ],
        validators=[DataRequired(message='Le type de contrat est obligatoire.')]
    )

    date_debut_contrat = DateField(
        'Date de début du contrat',
        validators=[DataRequired(message='La date de début est obligatoire.')]
    )

    date_fin_contrat = DateField(
        'Date de fin du contrat (laisser vide si CDI)',
        validators=[Optional()]
    )

    # -------------------------------------------------------
    # HORAIRES DE TRAVAIL
    # -------------------------------------------------------
    heure_arrivee = TimeField(
        'Heure d\'arrivée',
        validators=[DataRequired(message='L\'heure d\'arrivée est obligatoire.')]
    )

    heure_depart = TimeField(
        'Heure de départ',
        validators=[DataRequired(message='L\'heure de départ est obligatoire.')]
    )

    pause_minutes = IntegerField(
        'Durée de la pause (minutes)',
        validators=[
            DataRequired(message='La durée de pause est obligatoire.'),
            NumberRange(min=0, max=240, message='La pause doit être entre 0 et 240 minutes.')
        ],
        default=60
    )

    tolerance_retard_minutes = IntegerField(
        'Tolérance retard (minutes)',
        validators=[
            DataRequired(message='La tolérance est obligatoire.'),
            # Tolérance doit être > 0
            NumberRange(min=1, max=60, message='La tolérance doit être entre 1 et 60 minutes.')
        ],
        default=10
    )

    # -------------------------------------------------------
    # JOURS TRAVAILLÉS
    # Au moins 1 jour doit être coché
    # -------------------------------------------------------
    travaille_lundi = BooleanField('Lundi', default=True)
    travaille_mardi = BooleanField('Mardi', default=True)
    travaille_mercredi = BooleanField('Mercredi', default=True)
    travaille_jeudi = BooleanField('Jeudi', default=True)
    travaille_vendredi = BooleanField('Vendredi', default=True)
    travaille_samedi = BooleanField('Samedi', default=False)
    travaille_dimanche = BooleanField('Dimanche', default=False)

    soumettre = SubmitField('Enregistrer')

    def __init__(self, personne_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.personne_id = personne_id

    def validate_identifiant(self, identifiant):
        """Vérifier que le matricule est unique"""
        query = Personne.query.filter_by(identifiant=identifiant.data)
        if self.personne_id:
            query = query.filter(Personne.id != self.personne_id)
        if query.first():
            raise ValidationError('Ce matricule est déjà utilisé.')

    def validate_email(self, email):
        """Vérifier que l'email est unique si fourni"""
        if not email.data:
            return
        query = Personne.query.filter_by(email=email.data)
        if self.personne_id:
            query = query.filter(Personne.id != self.personne_id)
        if query.first():
            raise ValidationError('Cette adresse email est déjà utilisée.')

    def validate_date_debut_contrat(self, date_debut):
        """
        Vérifier que la date de début n'est pas dans le passé.
        Sécurité : le système n'accepte pas les dates passées.
        Exception : si on modifie un employé existant dont le contrat
        a déjà commencé, on autorise la date passée.
        """
        if not self.personne_id and date_debut.data:
            if date_debut.data < date.today():
                raise ValidationError(
                    'La date de début ne peut pas être dans le passé.'
                )

    def validate_date_fin_contrat(self, date_fin):
        """
        Vérifier que la date de fin est après la date de début.
        Obligatoire seulement pour CDD et Stage.
        """
        if not date_fin.data:
            # Si CDI → pas de date de fin requise
            if self.type_contrat.data in ['cdd', 'stage']:
                raise ValidationError(
                    'La date de fin est obligatoire pour un CDD ou Stage.'
                )
            return

        if self.date_debut_contrat.data:
            if date_fin.data <= self.date_debut_contrat.data:
                raise ValidationError(
                    'La date de fin doit être après la date de début.'
                )

    def validate_heure_depart(self, heure_depart):
        """
        Vérifier que l'heure de départ est après l'heure d'arrivée.
        Sécurité : le système n'accepte pas des horaires incohérents.
        """
        if self.heure_arrivee.data and heure_depart.data:
            if heure_depart.data <= self.heure_arrivee.data:
                raise ValidationError(
                    "L'heure de départ doit être après l'heure d'arrivée."
                )

    def validate_travaille_lundi(self, field):
        """
        Vérifier qu'au moins 1 jour est coché.
        Cette validation est sur le premier champ mais vérifie tous les jours.
        """
        jours = [
            self.travaille_lundi.data,
            self.travaille_mardi.data,
            self.travaille_mercredi.data,
            self.travaille_jeudi.data,
            self.travaille_vendredi.data,
            self.travaille_samedi.data,
            self.travaille_dimanche.data
        ]
        if not any(jours):
            raise ValidationError(
                'Veuillez cocher au moins un jour de travail.'
            )


# ============================================================
# FORMULAIRE IMPORT EN MASSE
# ============================================================
class FormulaireImport(FlaskForm):
    """
    Formulaire pour importer une liste de personnes
    depuis un fichier Excel (.xlsx) ou CSV (.csv).

    Le fichier doit respecter un template téléchargeable
    depuis l'interface.
    """

    fichier = FileField(
        'Fichier Excel ou CSV',
        validators=[
            DataRequired(message='Veuillez sélectionner un fichier.'),
            # Accepter uniquement les fichiers Excel et CSV
            FileAllowed(['xlsx', 'csv'], 'Seuls les fichiers Excel (.xlsx) et CSV (.csv) sont acceptés.')
        ]
    )

    soumettre = SubmitField('Importer')


# ============================================================
# FORMULAIRE FIN DE CONTRAT — MODE ENTREPRISE
# ============================================================
class FormulaireFinContrat(FlaskForm):
    """
    Formulaire pour mettre fin au contrat d'un employé.
    Utilisé quand un employé quitte l'entreprise avant
    la date de fin prévue (ou pour un CDI).

    La date de fin effective sera enregistrée et le système
    arrêtera de générer des sessions à partir de cette date.
    """

    date_fin_effective = DateField(
        'Date de fin effective',
        validators=[DataRequired(message='La date de fin est obligatoire.')]
    )

    soumettre = SubmitField('Confirmer la fin de contrat')

    def validate_date_fin_effective(self, date_fin):
        """
        La date de fin ne peut pas être dans le futur lointain.
        Elle peut être aujourd'hui ou dans le passé récent
        (si l'agent a oublié de la saisir le bon jour).
        """
        if date_fin.data and date_fin.data > date.today():
            raise ValidationError(
                'La date de fin effective ne peut pas être dans le futur.'
            )