"""
forms.py — Formulaires d'authentification
==========================================
Contient les formulaires :
  1. FormulaireInscription  — Inscription d'un nouvel utilisateur
  2. FormulaireConnexion    — Connexion à l'interface

Décision architecturale :
  Le rôle n'est PAS choisi par l'utilisateur lors de l'inscription.
  C'est l'administrateur qui attribue le rôle (enseignant ou agent)
  lors de la validation du compte, via des boutons radio dans l'interface admin.
  Cela correspond à la réalité : l'admin connaît ses utilisateurs et
  sait quel rôle leur attribuer.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
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

    Qui peut s'inscrire ?
        - Enseignants / Managers
        - Agents de scolarité / RH

    Qui NE peut PAS s'inscrire via ce formulaire ?
        - Les admins (créés uniquement par le développeur via seed.py)

    Après inscription :
        1. L'utilisateur reçoit un email de vérification
        2. Après vérification, l'admin voit la demande dans son tableau de bord
        3. L'admin choisit le rôle via boutons radio et valide (ou rejette) le compte
    """

    # -------------------------------------------------------
    # Champ : Prénom
    # -------------------------------------------------------
    prenom = StringField(
        'Prénom',
        validators=[
            # Le prénom est obligatoire
            DataRequired(message='Le prénom est obligatoire.'),
            # Entre 2 et 100 caractères
            Length(min=2, max=100, message='Le prénom doit contenir entre 2 et 100 caractères.')
        ]
    )

    # -------------------------------------------------------
    # Champ : Nom
    # -------------------------------------------------------
    nom = StringField(
        'Nom',
        validators=[
            DataRequired(message='Le nom est obligatoire.'),
            Length(min=2, max=100, message='Le nom doit contenir entre 2 et 100 caractères.')
        ]
    )

    # -------------------------------------------------------
    # Champ : Email institutionnel
    # Utilisé comme identifiant de connexion
    # -------------------------------------------------------
    email = StringField(
        'Email institutionnel',
        validators=[
            DataRequired(message="L'email est obligatoire."),
            # Vérification du format email (ex: nom@universite.ma)
            Email(message="L'adresse email n'est pas valide.")
        ]
    )

    # -------------------------------------------------------
    # Champ : Département ou Filière
    # Aide l'admin à identifier l'utilisateur et attribuer le bon rôle
    # Exemple : "Cybersécurité", "Informatique", "RH", "Finance"
    # -------------------------------------------------------
    departement = StringField(
        'Département / Filière',
        validators=[
            DataRequired(message='Le département est obligatoire.'),
            Length(max=100)
        ]
    )

    # -------------------------------------------------------
    # Champ : Mot de passe
    # La complexité est vérifiée dans validate_mot_de_passe()
    # -------------------------------------------------------
    mot_de_passe = PasswordField(
        'Mot de passe',
        validators=[
            DataRequired(message='Le mot de passe est obligatoire.'),
            # Minimum 8 caractères
            Length(min=8, message='Le mot de passe doit contenir au moins 8 caractères.')
        ]
    )

    # -------------------------------------------------------
    # Champ : Confirmation du mot de passe
    # Doit être identique au champ mot_de_passe
    # -------------------------------------------------------
    confirmation_mot_de_passe = PasswordField(
        'Confirmer le mot de passe',
        validators=[
            DataRequired(message='La confirmation est obligatoire.'),
            # EqualTo vérifie que les deux mots de passe sont identiques
            EqualTo('mot_de_passe', message='Les mots de passe ne correspondent pas.')
        ]
    )

    # Bouton de soumission du formulaire
    soumettre = SubmitField("S'inscrire")

    # -------------------------------------------------------
    # Validation personnalisée : unicité de l'email
    # Flask-WTF appelle automatiquement cette méthode
    # lors de la validation du formulaire
    # -------------------------------------------------------
    def validate_email(self, email):
        """
        Vérifier que l'adresse email n'est pas déjà utilisée.
        Si un compte existe déjà avec cet email, on lève une erreur.
        """
        utilisateur = Utilisateur.query.filter_by(email=email.data).first()
        if utilisateur:
            raise ValidationError('Cette adresse email est déjà utilisée.')

    # -------------------------------------------------------
    # Validation personnalisée : complexité du mot de passe
    # Un mot de passe fort réduit les risques de compromission
    # -------------------------------------------------------
    def validate_mot_de_passe(self, mot_de_passe):
        """
        Vérifier la complexité du mot de passe.

        Règles :
            - Au moins 8 caractères (vérifié par Length ci-dessus)
            - Au moins une lettre majuscule (ex: A, B, C...)
            - Au moins un chiffre (ex: 0, 1, 2...)
            - Au moins un caractère spécial (ex: @, #, $...)

        Pourquoi ces règles ?
            Un mot de passe complexe est beaucoup plus difficile à deviner
            par force brute ou par dictionnaire.
        """
        mdp = mot_de_passe.data

        # Vérifier la présence d'une majuscule
        if not any(c.isupper() for c in mdp):
            raise ValidationError('Le mot de passe doit contenir au moins une majuscule.')

        # Vérifier la présence d'un chiffre
        if not any(c.isdigit() for c in mdp):
            raise ValidationError('Le mot de passe doit contenir au moins un chiffre.')

        # Vérifier la présence d'un caractère spécial
        if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in mdp):
            raise ValidationError('Le mot de passe doit contenir au moins un caractère spécial.')


# ============================================================
# FORMULAIRE DE CONNEXION
# ============================================================
class FormulaireConnexion(FlaskForm):
    """
    Formulaire de connexion pour tous les utilisateurs ayant un compte actif.

    Sécurité :
        - Le mot de passe est vérifié via bcrypt (jamais comparé en clair)
        - Après 5 tentatives échouées, le compte est automatiquement bloqué
        - Un message générique est affiché en cas d'erreur pour ne pas
          révéler si l'email existe ou non dans le système
    """

    # -------------------------------------------------------
    # Champ : Email — identifiant unique de connexion
    # -------------------------------------------------------
    email = StringField(
        'Email',
        validators=[
            DataRequired(message="L'email est obligatoire."),
            Email(message="L'adresse email n'est pas valide.")
        ]
    )

    # -------------------------------------------------------
    # Champ : Mot de passe
    # -------------------------------------------------------
    mot_de_passe = PasswordField(
        'Mot de passe',
        validators=[
            DataRequired(message='Le mot de passe est obligatoire.')
        ]
    )

    # Bouton de soumission du formulaire
    soumettre = SubmitField('Se connecter')