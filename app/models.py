import uuid
from datetime import datetime, timezone, time
from flask_login import UserMixin
from app import db


# --- Fonction utilitaire ---
def generer_uuid():
    """Générer un identifiant unique universel (UUID)"""
    return str(uuid.uuid4())


# ============================================================
# TABLE : CONFIGURATION
# Paramètres globaux du système — Singleton (une seule instance)
# ============================================================
class Configuration(db.Model):
    __tablename__ = 'configuration'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # -------------------------------------------------------
    # MODE DU SYSTÈME
    # -------------------------------------------------------
    # Mode du système : 'ecole' ou 'entreprise'
    mode = db.Column(db.String(20), nullable=False, default='ecole')

    # -------------------------------------------------------
    # INFORMATIONS DE L'ÉTABLISSEMENT
    # Apparaissent dans les emails, rapports PDF et interface
    # -------------------------------------------------------
    # Nom de l'établissement
    nom_etablissement = db.Column(db.String(200), nullable=True)

    # Adresse physique
    adresse = db.Column(db.String(255), nullable=True)

    # Ville
    ville = db.Column(db.String(100), nullable=True)

    # Numéro de téléphone
    telephone = db.Column(db.String(20), nullable=True)

    # Site web officiel
    site_web = db.Column(db.String(100), nullable=True)

    # Chemin vers le logo (stocké dans app/static/uploads/logos/)
    logo_path = db.Column(db.String(255), nullable=True)

    # -------------------------------------------------------
    # SÉCURITÉ EMAIL
    # -------------------------------------------------------
    # Domaine email autorisé pour l'inscription
    # Ex: "universite.ma" → seules @universite.ma acceptées
    # Si None → tous les emails acceptés
    domaine_email_autorise = db.Column(db.String(100), nullable=True)

    # -------------------------------------------------------
    # PARAMÈTRES DE SÉCURITÉ BIOMÉTRIQUE
    # -------------------------------------------------------
    # Seuil minimum de similarité faciale (ex: 0.90 = 90%)
    seuil_similarite = db.Column(db.Float, nullable=False, default=0.90)

    # Nombre maximum de tentatives échouées avant blocage
    max_tentatives = db.Column(db.Integer, nullable=False, default=5)

    # Durée de conservation des données biométriques en jours (RGPD)
    duree_retention_jours = db.Column(db.Integer, nullable=False, default=365)

    # -------------------------------------------------------
    # PARAMÈTRES DE PRÉSENCE
    # -------------------------------------------------------
    # Tolérance retard par défaut en minutes
    # Peut être modifiée par l'enseignant lors de la création de session
    tolerance_retard_defaut = db.Column(db.Integer, nullable=False, default=10)

    # -------------------------------------------------------
    # PARAMÈTRES GÉNÉRAUX
    # -------------------------------------------------------
    # Langue par défaut : 'fr', 'en', 'ar'
    langue_defaut = db.Column(db.String(5), nullable=False, default='fr')

    # Email du développeur — alertes techniques et sécurité critique
    email_developpeur = db.Column(db.String(150), nullable=True)

    # Email de l'admin — alertes métier
    email_admin = db.Column(db.String(150), nullable=True)

    def __repr__(self):
        return f'<Configuration mode={self.mode} etablissement={self.nom_etablissement}>'

    @staticmethod
    def get_config():
        """
        Récupérer la configuration du système (Singleton).
        Retourne la première et unique instance de configuration.
        """
        return Configuration.query.first()


# ============================================================
# TABLE : UTILISATEURS
# Personnes qui ont accès à l'interface web du système
# Rôles : 'admin', 'enseignant', 'agent'
# Maximum 3 admins par système
# ============================================================
class Utilisateur(UserMixin, db.Model):
    __tablename__ = 'utilisateurs'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # Version pour l'Optimistic Locking
    # Empêche 2 admins de modifier le même enregistrement simultanément
    version = db.Column(db.Integer, default=1, nullable=False)

    # Informations personnelles
    prenom = db.Column(db.String(100), nullable=False)
    nom = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)

    # Mot de passe haché avec bcrypt — JAMAIS stocké en clair
    mot_de_passe_hache = db.Column(db.String(255), nullable=False)

    # Département ou filière
    departement = db.Column(db.String(100), nullable=True)

    # -------------------------------------------------------
    # GESTION DES RÔLES
    # -------------------------------------------------------
    # Rôle attribué par l'admin après validation
    # Valeurs : 'admin', 'enseignant', 'agent'
    # NULL tant que le compte n'est pas validé
    role = db.Column(db.String(50), nullable=True, default=None)

    # Toujours NULL — l'admin attribue directement le rôle
    # lors de la validation du compte via son interface
    role_souhaite = db.Column(db.String(50), nullable=True)

    # -------------------------------------------------------
    # GESTION DES STATUTS DU COMPTE
    # -------------------------------------------------------
    # 'en_attente'    → inscrit, email non encore vérifié
    # 'email_verifie' → email confirmé, attend validation admin
    # 'actif'         → rôle attribué, accès complet
    # 'desactive'     → bloqué par l'admin
    # 'rejete'        → demande refusée par l'admin
    statut_compte = db.Column(db.String(20), nullable=False, default='en_attente')

    # Raison du rejet par l'admin
    raison_rejet = db.Column(db.String(255), nullable=True)

    # -------------------------------------------------------
    # VÉRIFICATION DE L'EMAIL
    # -------------------------------------------------------
    token_email = db.Column(db.String(255), nullable=True)
    expiration_token = db.Column(db.DateTime, nullable=True)

    # -------------------------------------------------------
    # VALIDATION PAR L'ADMIN
    # -------------------------------------------------------
    valide_par = db.Column(db.String(36), db.ForeignKey('utilisateurs.id'), nullable=True)
    valide_le = db.Column(db.DateTime, nullable=True)

    # -------------------------------------------------------
    # SÉCURITÉ — TENTATIVES DE CONNEXION
    # -------------------------------------------------------
    tentatives_echouees = db.Column(db.Integer, default=0)
    est_actif = db.Column(db.Boolean, default=True)

    # -------------------------------------------------------
    # MÉTADONNÉES
    # -------------------------------------------------------
    derniere_connexion = db.Column(db.DateTime, nullable=True)
    cree_le = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # -------------------------------------------------------
    # OPTIMISTIC LOCKING
    # -------------------------------------------------------
    __mapper_args__ = {
        'version_id_col': version,
        'version_id_generator': False
    }

    # -------------------------------------------------------
    # RELATIONS
    # -------------------------------------------------------
    sessions_creees = db.relationship('Session', backref='createur', lazy=True,
                                      foreign_keys='Session.cree_par')
    personnes_creees = db.relationship('Personne', backref='cree_par_utilisateur', lazy=True,
                                       foreign_keys='Personne.cree_par')
    cartes_attribuees = db.relationship('CarteRFID', backref='attribuee_par_utilisateur', lazy=True,
                                        foreign_keys='CarteRFID.attribuee_par')

    def __repr__(self):
        return f'<Utilisateur {self.email} role={self.role} statut={self.statut_compte}>'

    def nom_complet(self):
        return f'{self.prenom} {self.nom}'

    def est_admin(self):
        return self.role == 'admin'

    def est_enseignant(self):
        return self.role == 'enseignant'

    def est_agent(self):
        return self.role == 'agent'

    def compte_actif(self):
        return self.statut_compte == 'actif' and self.est_actif

    @staticmethod
    def peut_ajouter_admin():
        """Vérifie si on peut encore ajouter un admin — maximum 3"""
        return Utilisateur.query.filter_by(role='admin').count() < 3

    @staticmethod
    def nombre_admins():
        """Retourne le nombre d'admins actuels"""
        return Utilisateur.query.filter_by(role='admin').count()


# ============================================================
# TABLE : PERSONNES
# Étudiants (mode école) ou Employés (mode entreprise)
# Ces personnes N'ONT PAS accès à l'interface web
# ============================================================
class Personne(db.Model):
    __tablename__ = 'personnes'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # Informations personnelles
    prenom = db.Column(db.String(100), nullable=False)
    nom = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=True)

    # Identifiant selon le contexte :
    # Mode école      → CNE ou Code étudiant
    # Mode entreprise → Matricule ou Badge employé
    identifiant = db.Column(db.String(100), unique=True, nullable=False)

    # Département / Filière
    departement = db.Column(db.String(100), nullable=True)

    # Niveau / Poste
    niveau_ou_poste = db.Column(db.String(100), nullable=True)

    # Groupe / Site
    groupe_ou_site = db.Column(db.String(100), nullable=True)

    # Statut
    est_actif = db.Column(db.Boolean, default=True)

    # Agent ou RH qui a créé ce profil
    cree_par = db.Column(db.String(36), db.ForeignKey('utilisateurs.id'), nullable=True)

    # Date de création
    cree_le = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # -------------------------------------------------------
    # CONTRAT DE TRAVAIL (MODE ENTREPRISE UNIQUEMENT)
    # Ces champs sont NULL en mode école
    # -------------------------------------------------------
    # Type de contrat : 'cdi', 'cdd', 'stage'
    type_contrat = db.Column(db.String(20), nullable=True)

    # Date de début du contrat
    # Ne peut pas être dans le passé lors de l'enregistrement
    date_debut_contrat = db.Column(db.Date, nullable=True)

    # Date de fin du contrat (NULL si CDI)
    # Doit être > date_debut_contrat
    date_fin_contrat = db.Column(db.Date, nullable=True)

    # -------------------------------------------------------
    # HORAIRES DE TRAVAIL (MODE ENTREPRISE UNIQUEMENT)
    # -------------------------------------------------------
    # Heure d'arrivée contractuelle (ex: 08:30)
    heure_arrivee = db.Column(db.Time, nullable=True)

    # Heure de départ contractuelle (ex: 17:30)
    # Doit être > heure_arrivee
    heure_depart = db.Column(db.Time, nullable=True)

    # Durée de pause forfaitaire en minutes (ex: 60 = 1 heure)
    # Déduite automatiquement du calcul des heures travaillées
    pause_minutes = db.Column(db.Integer, nullable=True, default=60)

    # Tolérance retard en minutes pour cet employé
    # Peut différer de la tolérance par défaut du système
    tolerance_retard_minutes = db.Column(db.Integer, nullable=True, default=10)

    # -------------------------------------------------------
    # JOURS TRAVAILLÉS (MODE ENTREPRISE UNIQUEMENT)
    # Cochés lors de l'enregistrement de l'employé
    # Le système génère automatiquement les sessions selon ces jours
    # -------------------------------------------------------
    travaille_lundi = db.Column(db.Boolean, default=True)
    travaille_mardi = db.Column(db.Boolean, default=True)
    travaille_mercredi = db.Column(db.Boolean, default=True)
    travaille_jeudi = db.Column(db.Boolean, default=True)
    travaille_vendredi = db.Column(db.Boolean, default=True)
    travaille_samedi = db.Column(db.Boolean, default=False)
    travaille_dimanche = db.Column(db.Boolean, default=False)

    # -------------------------------------------------------
    # RELATIONS
    # -------------------------------------------------------
    cartes_rfid = db.relationship('CarteRFID', backref='personne', lazy=True,
                                  foreign_keys='CarteRFID.personne_id')
    photos = db.relationship('Photo', backref='personne', lazy=True,
                             cascade='all, delete-orphan')
    presences = db.relationship('Presence', backref='personne', lazy=True)

    def __repr__(self):
        return f'<Personne {self.prenom} {self.nom} id={self.identifiant}>'

    def nom_complet(self):
        return f'{self.prenom} {self.nom}'

    def carte_active(self):
        """Retourne la carte RFID active de la personne"""
        return CarteRFID.query.filter_by(
            personne_id=self.id,
            statut='actif'
        ).first()

    def photo_principale(self):
        """Retourne la photo principale de la personne"""
        return Photo.query.filter_by(
            personne_id=self.id,
            est_principale=True
        ).first()

    def contrat_actif(self):
        """
        Vérifie si le contrat de l'employé est encore actif.
        Utilisé en mode entreprise pour savoir si générer des sessions.
        """
        from datetime import date
        aujourd_hui = date.today()

        if not self.date_debut_contrat:
            return False

        # Contrat pas encore commencé
        if aujourd_hui < self.date_debut_contrat:
            return False

        # CDI ou contrat sans date de fin → toujours actif
        if not self.date_fin_contrat:
            return True

        # CDD → vérifier la date de fin
        return aujourd_hui <= self.date_fin_contrat

    def heures_contractuelles_jour(self):
        """
        Calcule les heures contractuelles par jour en mode entreprise.
        Formule : heure_depart - heure_arrivee - pause_minutes
        """
        if not self.heure_arrivee or not self.heure_depart:
            return 0

        from datetime import datetime as dt
        debut = dt.combine(dt.today(), self.heure_arrivee)
        fin = dt.combine(dt.today(), self.heure_depart)
        duree_minutes = (fin - debut).seconds / 60
        return (duree_minutes - (self.pause_minutes or 0)) / 60


# ============================================================
# TABLE : PHOTOS
# Photos faciales des personnes — chiffrées AES-256
# ============================================================
class Photo(db.Model):
    __tablename__ = 'photos'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # Référence vers la personne
    personne_id = db.Column(db.String(36), db.ForeignKey('personnes.id'), nullable=False)

    # Chemin du fichier chiffré (AES-256)
    chemin_fichier = db.Column(db.String(255), nullable=False)

    # Photo principale utilisée par DeepFace
    est_principale = db.Column(db.Boolean, default=False)

    # Score de qualité (0 à 1) — minimum 0.7 requis
    score_qualite = db.Column(db.Float, nullable=True)

    # Confirme que la photo est chiffrée
    est_chiffree = db.Column(db.Boolean, default=True)

    # Date d'ajout
    cree_le = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Photo personne={self.personne_id} principale={self.est_principale}>'


# ============================================================
# TABLE : CARTES RFID
# ============================================================
class CarteRFID(db.Model):
    __tablename__ = 'cartes_rfid'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # Numéro chiffré AES-256
    numero_rfid = db.Column(db.String(255), unique=True, nullable=False)

    # Propriétaire
    personne_id = db.Column(db.String(36), db.ForeignKey('personnes.id'), nullable=False)

    # Statut : 'actif', 'revoque', 'perdu', 'expire'
    statut = db.Column(db.String(20), nullable=False, default='actif')

    # Agent qui a attribué la carte
    attribuee_par = db.Column(db.String(36), db.ForeignKey('utilisateurs.id'), nullable=True)

    # Dates
    attribuee_le = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    revoquee_le = db.Column(db.DateTime, nullable=True)
    raison_revocation = db.Column(db.String(255), nullable=True)

    # Relations
    presences = db.relationship('Presence', backref='carte_rfid', lazy=True)

    def __repr__(self):
        return f'<CarteRFID statut={self.statut} personne={self.personne_id}>'

    def est_valide(self):
        return self.statut == 'actif'

    def revoquer(self, raison):
        self.statut = 'revoque'
        self.revoquee_le = datetime.now(timezone.utc)
        self.raison_revocation = raison


# ============================================================
# TABLE : SESSIONS
# Cours (mode école) ou Journées de travail (mode entreprise)
# ============================================================
class Session(db.Model):
    __tablename__ = 'sessions'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # Nom :
    # Mode école      → "Cybersécurité G1"
    # Mode entreprise → "Journée 27/04/2026 — Ahmed Benali"
    nom = db.Column(db.String(200), nullable=False)

    # Créateur : enseignant (école) ou système automatique (entreprise)
    cree_par = db.Column(db.String(36), db.ForeignKey('utilisateurs.id'), nullable=True)

    # Lieu :
    # Mode école      → "Salle B12"
    # Mode entreprise → "Bureau principal"
    lieu = db.Column(db.String(200), nullable=True)

    # -------------------------------------------------------
    # DATES ET HEURES
    # Validations :
    #   - heure_debut ne peut pas être dans le passé
    #   - heure_fin > heure_debut obligatoire
    # -------------------------------------------------------
    heure_debut = db.Column(db.DateTime, nullable=False)
    heure_fin = db.Column(db.DateTime, nullable=False)

    # -------------------------------------------------------
    # TOLÉRANCE RETARD
    # Définie par l'enseignant lors de la création
    # Valeur par défaut = tolerance_retard_defaut de Configuration
    # L'enseignant peut modifier : 5, 10, 15, 20 min selon sa politique
    # -------------------------------------------------------
    tolerance_retard_minutes = db.Column(db.Integer, nullable=False, default=10)

    # -------------------------------------------------------
    # TYPE DE SESSION
    # -------------------------------------------------------
    # 'cours'    → mode école, créée manuellement par enseignant
    # 'journee'  → mode entreprise, créée automatiquement par le système
    type_session = db.Column(db.String(20), nullable=False, default='cours')

    # En mode entreprise : référence vers la personne concernée
    # En mode école : NULL (session concerne un groupe entier)
    personne_id = db.Column(db.String(36), db.ForeignKey('personnes.id'), nullable=True)

    # Date de création de la session
    cree_le = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relations
    presences = db.relationship('Presence', backref='session', lazy=True,
                                cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Session {self.nom} type={self.type_session}>'

    def est_active(self):
        """Vérifie si la session est en cours"""
        maintenant = datetime.now(timezone.utc)
        return self.heure_debut <= maintenant <= self.heure_fin

    def est_terminee(self):
        """Vérifie si la session est terminée"""
        return datetime.now(timezone.utc) > self.heure_fin

    def nombre_presences(self):
        """Retourne le nombre de présences validées"""
        return Presence.query.filter_by(
            session_id=self.id,
            statut='present'
        ).count()

    def heure_limite_pointage(self):
        """
        Retourne l'heure limite après laquelle le pointage
        est considéré comme un retard.
        """
        from datetime import timedelta
        return self.heure_debut + timedelta(minutes=self.tolerance_retard_minutes)


# ============================================================
# TABLE : PRESENCES
# Enregistrement de chaque présence
# ============================================================
class Presence(db.Model):
    __tablename__ = 'presences'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # Références
    personne_id = db.Column(db.String(36), db.ForeignKey('personnes.id'), nullable=False)
    session_id = db.Column(db.String(36), db.ForeignKey('sessions.id'), nullable=False)
    carte_rfid_id = db.Column(db.String(36), db.ForeignKey('cartes_rfid.id'), nullable=True)

    # -------------------------------------------------------
    # POINTAGE
    # -------------------------------------------------------
    # Horodatage du pointage entrée (RFID + visage)
    horodatage = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Score DeepFace (0 à 1) — stocké pour audit
    score_similarite = db.Column(db.Float, nullable=True)

    # -------------------------------------------------------
    # STATUT DE PRÉSENCE
    # -------------------------------------------------------
    # 'present' → pointage validé dans les délais
    # 'retard'  → pointage après tolérance
    # 'absent'  → aucun pointage en fin de session
    # 'refuse'  → tentative rejetée (fraude, score insuffisant)
    statut = db.Column(db.String(20), nullable=False, default='present')

    # Méthode de validation :
    # 'rfid_visage' → automatique
    # 'manuel'      → modifié par enseignant/manager
    methode_validation = db.Column(db.String(50), default='rfid_visage')

    # -------------------------------------------------------
    # MODIFICATION MANUELLE PAR ENSEIGNANT / MANAGER
    # Si l'enseignant constate qu'un étudiant est parti,
    # il peut modifier le statut avec une justification
    # -------------------------------------------------------
    # Qui a modifié le statut
    modifie_par = db.Column(db.String(36), db.ForeignKey('utilisateurs.id'), nullable=True)

    # Quand la modification a été faite
    modifie_le = db.Column(db.DateTime, nullable=True)

    # Justification obligatoire si modification manuelle
    # Ex: "Étudiant sorti après 20 min — maladie probable"
    # Ex: "Employé en mission externe"
    justification_modification = db.Column(db.String(255), nullable=True)

    # -------------------------------------------------------
    # MODE ENTREPRISE — HEURES TRAVAILLÉES
    # -------------------------------------------------------
    # Heures réellement travaillées (calculées automatiquement)
    # Formule : heure_depart_contractuelle - heure_arrivee_reelle - pause
    heures_travaillees = db.Column(db.Float, nullable=True)

    # Heures supplémentaires (positif = sup, négatif = déficit)
    heures_supplementaires = db.Column(db.Float, nullable=True, default=0)

    # Justification d'absence (remplie par le manager)
    # 'conge_maladie', 'conge_annuel', 'mission', 'ferie', 'injustifie'
    justification_absence = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f'<Presence personne={self.personne_id} statut={self.statut}>'

    def est_doublon(self):
        """Vérifie si cette personne a déjà une présence dans cette session"""
        return Presence.query.filter(
            Presence.personne_id == self.personne_id,
            Presence.session_id == self.session_id,
            Presence.statut.in_(['present', 'retard']),
            Presence.id != self.id
        ).count() > 0


# ============================================================
# TABLE : JOURS FÉRIÉS
# Gérés par le manager en mode entreprise
# ============================================================
class JourFerie(db.Model):
    __tablename__ = 'jours_feries'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # Date du jour férié
    date = db.Column(db.Date, nullable=False, unique=True)

    # Nom du jour férié
    # Ex: "Fête du Travail", "Fête du Trône"
    nom = db.Column(db.String(100), nullable=False)

    # Type :
    # 'national'   → jours fériés marocains prédéfinis
    #                (Fête du Trône, Fête du Travail, etc.)
    # 'ponctuel'   → fermeture exceptionnelle ajoutée par manager/admin
    #                (panne électrique, réunion exceptionnelle, etc.)
    # 'academique' → vacances scolaires — mode école uniquement
    #                (vacances de printemps, été, etc.)
    type_ferie = db.Column(db.String(20), nullable=False, default='ponctuel')

    # Manager qui a ajouté ce jour (NULL si national)
    cree_par = db.Column(db.String(36), db.ForeignKey('utilisateurs.id'), nullable=True)

    # Date de création
    cree_le = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<JourFerie {self.date} — {self.nom}>'


# ============================================================
# TABLE : JOURNAL DE SÉCURITÉ
# ============================================================
class JournalSecurite(db.Model):
    __tablename__ = 'journal_securite'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # Horodatage
    horodatage = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Type d'événement
    type_evenement = db.Column(db.String(100), nullable=False)

    # Niveau de gravité : 'info', 'warning', 'critique'
    severite = db.Column(db.String(20), nullable=False, default='info')

    # Description détaillée
    description = db.Column(db.Text, nullable=True)

    # Adresse IP
    adresse_ip = db.Column(db.String(50), nullable=True)

    # Résultat : 'succes', 'echec', 'bloque'
    resultat = db.Column(db.String(20), nullable=True)

    # Destinataire : 'admin', 'developpeur', 'les_deux'
    destinataire = db.Column(db.String(20), nullable=False, default='admin')

    # Références optionnelles
    utilisateur_id = db.Column(db.String(36), db.ForeignKey('utilisateurs.id'), nullable=True)
    personne_id = db.Column(db.String(36), db.ForeignKey('personnes.id'), nullable=True)
    carte_rfid_id = db.Column(db.String(36), db.ForeignKey('cartes_rfid.id'), nullable=True)

    def __repr__(self):
        return f'<JournalSecurite {self.type_evenement} severite={self.severite}>'


# ============================================================
# TABLE : NOTIFICATIONS
# Notifications internes entre administrateurs
# ============================================================
class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # Admin destinataire
    destinataire_id = db.Column(db.String(36), db.ForeignKey('utilisateurs.id'), nullable=False)

    # Admin expéditeur (None pour alertes système)
    expediteur_id = db.Column(db.String(36), db.ForeignKey('utilisateurs.id'), nullable=True)

    # Type :
    # 'validation', 'rejet', 'changement_role', 'desactivation',
    # 'reactivation', 'nouvel_admin', 'message'
    type_notification = db.Column(db.String(50), nullable=False)

    # Titre court affiché dans la cloche
    titre = db.Column(db.String(200), nullable=False)

    # Contenu détaillé
    contenu = db.Column(db.Text, nullable=True)

    # Statut de lecture
    est_lue = db.Column(db.Boolean, default=False, nullable=False)
    lue_le = db.Column(db.DateTime, nullable=True)

    # Date de création
    cree_le = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relations
    destinataire = db.relationship(
        'Utilisateur',
        foreign_keys=[destinataire_id],
        backref='notifications_recues'
    )
    expediteur = db.relationship(
        'Utilisateur',
        foreign_keys=[expediteur_id],
        backref='notifications_envoyees'
    )

    

    def __repr__(self):
        return f'<Notification {self.type_notification} lue={self.est_lue}>'

    def marquer_lue(self):
        """Marquer la notification comme lue"""
        self.est_lue = True
        self.lue_le = datetime.now(timezone.utc)

    @staticmethod
    def notifier_admins(expediteur, type_notification, titre, contenu=None):
        """
        Créer une notification pour tous les autres admins actifs.
        Appelée automatiquement après chaque action importante.
        """
        autres_admins = Utilisateur.query.filter(
            Utilisateur.role == 'admin',
            Utilisateur.statut_compte == 'actif',
            Utilisateur.est_actif == True,
            Utilisateur.id != expediteur.id
        ).all()

        for admin in autres_admins:
            notif = Notification(
                destinataire_id=admin.id,
                expediteur_id=expediteur.id,
                type_notification=type_notification,
                titre=titre,
                contenu=contenu,
                est_lue=False
            )
            db.session.add(notif)

        db.session.commit()

    @staticmethod
    def compter_non_lues(admin_id):
        """Retourne le nombre de notifications non lues"""
        return Notification.query.filter_by(
            destinataire_id=admin_id,
            est_lue=False
        ).count()
    
    # ============================================================
# TABLE : EMPLOIS DU TEMPS
# Emploi du temps hebdomadaire des enseignants (mode école)
# Permet la génération automatique des sessions chaque semaine
# ============================================================
class EmploiDuTemps(db.Model):
    __tablename__ = 'emplois_du_temps'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # -------------------------------------------------------
    # ENSEIGNANT PROPRIÉTAIRE
    # -------------------------------------------------------
    enseignant_id = db.Column(
        db.String(36),
        db.ForeignKey('utilisateurs.id'),
        nullable=False
    )

    # -------------------------------------------------------
    # JOUR DE LA SEMAINE
    # 0 = Lundi, 1 = Mardi, 2 = Mercredi,
    # 3 = Jeudi, 4 = Vendredi, 5 = Samedi, 6 = Dimanche
    # -------------------------------------------------------
    jour_semaine = db.Column(db.Integer, nullable=False)

    # -------------------------------------------------------
    # INFORMATIONS DU COURS
    # -------------------------------------------------------
    # Nom du cours (ex: "Cybersécurité", "Réseaux")
    nom_cours = db.Column(db.String(200), nullable=False)

    # Groupe ciblé (ex: G1, G2, G3)
    groupe = db.Column(db.String(50), nullable=True)

    # Salle de cours (ex: B12, A05)
    salle = db.Column(db.String(100), nullable=True)

    # -------------------------------------------------------
    # HORAIRES
    # heure_fin doit être > heure_debut (validé dans le formulaire)
    # -------------------------------------------------------
    heure_debut = db.Column(db.Time, nullable=False)
    heure_fin = db.Column(db.Time, nullable=False)

    # -------------------------------------------------------
    # TOLÉRANCE RETARD
    # Définie une fois dans l'emploi du temps
    # Appliquée automatiquement à chaque session générée
    # Valeur par défaut = tolerance_retard_defaut de Configuration
    # -------------------------------------------------------
    tolerance_retard_minutes = db.Column(
        db.Integer,
        nullable=False,
        default=10
    )

    # -------------------------------------------------------
    # STATUT
    # est_actif = False → cours suspendu temporairement
    # (ex: enseignant en congé, cours annulé pour ce semestre)
    # Les sessions ne sont plus générées pour ce créneau
    # -------------------------------------------------------
    est_actif = db.Column(db.Boolean, default=True, nullable=False)

    # -------------------------------------------------------
    # PÉRIODE DE VALIDITÉ
    # Permet de définir un emploi du temps par semestre
    # Ex: S1 → 01/09/2025 au 31/01/2026
    #     S2 → 01/02/2026 au 30/06/2026
    # Si None → valable indéfiniment
    # -------------------------------------------------------
    date_debut_validite = db.Column(db.Date, nullable=True)
    date_fin_validite = db.Column(db.Date, nullable=True)

    # Date de création
    cree_le = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    # -------------------------------------------------------
    # RELATION
    # -------------------------------------------------------
    enseignant = db.relationship(
        'Utilisateur',
        foreign_keys=[enseignant_id],
        backref='emplois_du_temps'
    )

    def __repr__(self):
        jours = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi',
                 'Vendredi', 'Samedi', 'Dimanche']
        jour = jours[self.jour_semaine] if 0 <= self.jour_semaine <= 6 else '?'
        return f'<EmploiDuTemps {jour} {self.heure_debut}→{self.heure_fin} {self.nom_cours}>'

    def est_valide_aujourd_hui(self):
        """
        Vérifie si cet emploi du temps est valide aujourd'hui.
        Utilisé par le scheduler avant de générer les sessions.
        """
        from datetime import date
        aujourd_hui = date.today()

        if not self.est_actif:
            return False

        if self.date_debut_validite and aujourd_hui < self.date_debut_validite:
            return False

        if self.date_fin_validite and aujourd_hui > self.date_fin_validite:
            return False

        return True

    def prochain_cours(self):
        """
        Retourne la prochaine date de ce cours.
        Utilisé par le scheduler pour générer la session de la semaine.
        """
        from datetime import date, timedelta
        aujourd_hui = date.today()
        jours_restants = (self.jour_semaine - aujourd_hui.weekday()) % 7
        if jours_restants == 0:
            jours_restants = 7
        return aujourd_hui + timedelta(days=jours_restants)