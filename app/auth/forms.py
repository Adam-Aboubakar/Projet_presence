"""
forms.py — Formulaires d'authentification
==========================================
Contient les formulaires :
  1. FormulaireInscription  — Inscription d'un nouvel utilisateur
  2. FormulaireConnexion    — Connexion à l'interface
"""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import (
    DataRequired, Email, Length,
    EqualTo, ValidationError
)
from app.models import Utilisateur


# ============================================================
# FORMULAIRE D'INSCRIPTION
# ============================================================
class FormulaireInscription(FlaskForm):
    """
    Formulaire d'inscription pour les nouveaux utilisateurs.
    Accessible uniquement aux enseignants et agents.
    L'admin ne s'inscrit jamais via ce formulaire.
    """

    prenom = StringField(
        'Prénom',
        validators=[
            DataRequired(message='Le prénom est obligatoire.'),
            Length(min=2, max=100, message='Le prénom doit contenir entre 2 et 100 caractères.')
        ]
    )

    nom = StringField(
        'Nom',
        validators=[
            DataRequired(message='Le nom est obligatoire.'),
            Length(min=2, max=100, message='Le nom doit contenir entre 2 et 100 caractères.')
        ]
    )

    email = StringField(
        'Email institutionnel',
        validators=[
            DataRequired(message="L'email est obligatoire."),
            Email(message="L'adresse email n'est pas valide.")
        ]
    )

    departement = StringField(
        'Département / Filière',
        validators=[
            DataRequired(message='Le département est obligatoire.'),
            Length(max=100)
        ]
    )

    # Rôle souhaité — uniquement enseignant ou agent
    # L'admin ne peut pas s'inscrire via cette page
    role_souhaite = SelectField(
        'Rôle souhaité',
        choices=[
            ('', '-- Choisir un rôle --'),
            ('enseignant', 'Enseignant / Manager'),
            ('agent', 'Agent de scolarité / RH')
        ],
        validators=[
            DataRequired(message='Veuillez choisir un rôle.')
        ]
    )

    mot_de_passe = PasswordField(
        'Mot de passe',
        validators=[
            DataRequired(message='Le mot de passe est obligatoire.'),
            Length(min=8, message='Le mot de passe doit contenir au moins 8 caractères.')
        ]
    )

    confirmation_mot_de_passe = PasswordField(
        'Confirmer le mot de passe',
        validators=[
            DataRequired(message='La confirmation est obligatoire.'),
            EqualTo('mot_de_passe', message='Les mots de passe ne correspondent pas.')
        ]
    )

    soumettre = SubmitField("S'inscrire")

    def validate_email(self, email):
        """Vérifier que l'email n'est pas déjà utilisé"""
        utilisateur = Utilisateur.query.filter_by(email=email.data).first()
        if utilisateur:
            raise ValidationError('Cette adresse email est déjà utilisée.')

    def validate_mot_de_passe(self, mot_de_passe):
        """
        Vérifier la complexité du mot de passe :
        - Au moins 8 caractères
        - Au moins une majuscule
        - Au moins un chiffre
        - Au moins un caractère spécial
        """
        mdp = mot_de_passe.data
        if not any(c.isupper() for c in mdp):
            raise ValidationError('Le mot de passe doit contenir au moins une majuscule.')
        if not any(c.isdigit() for c in mdp):
            raise ValidationError('Le mot de passe doit contenir au moins un chiffre.')
        if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in mdp):
            raise ValidationError('Le mot de passe doit contenir au moins un caractère spécial.')

    def validate_role_souhaite(self, role_souhaite):
        """Vérifier que le rôle choisi est valide"""
        roles_autorises = ['enseignant', 'agent']
        if role_souhaite.data not in roles_autorises:
            raise ValidationError('Rôle invalide. Choisissez Enseignant ou Agent.')


# ============================================================
# FORMULAIRE DE CONNEXION
# ============================================================
class FormulaireConnexion(FlaskForm):
    """
    Formulaire de connexion pour tous les utilisateurs.
    """

    email = StringField(
        'Email',
        validators=[
            DataRequired(message="L'email est obligatoire."),
            Email(message="L'adresse email n'est pas valide.")
        ]
    )

    mot_de_passe = PasswordField(
        'Mot de passe',
        validators=[
            DataRequired(message='Le mot de passe est obligatoire.')
        ]
    )

    soumettre = SubmitField('Se connecter')