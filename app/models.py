import uuid
from datetime import datetime, timezone
from flask_login import UserMixin
from app import db


# --- Fonction utilitaire ---
def generate_uuid():
    """Générer un identifiant unique universel (UUID)"""
    return str(uuid.uuid4())


# ============================================================
# TABLE : CONFIGURATION
# Paramètres globaux du système — Singleton (une seule instance)
# ============================================================
class Configuration(db.Model):
    __tablename__ = 'configuration'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Mode du système : 'ecole' ou 'entreprise'
    mode = db.Column(db.String(20), nullable=False, default='ecole')

    # Seuil minimum de similarité faciale (ex: 0.90 = 90%)
    similarity_threshold = db.Column(db.Float, nullable=False, default=0.90)

    # Nombre maximum de tentatives échouées avant blocage du compte
    max_attempts = db.Column(db.Integer, nullable=False, default=5)

    # Durée de conservation des données biométriques en jours (RGPD)
    data_retention_days = db.Column(db.Integer, nullable=False, default=365)

    # Langue par défaut : 'fr', 'en', 'ar'
    default_language = db.Column(db.String(5), nullable=False, default='fr')

    # Email du développeur — pour recevoir les alertes techniques et de sécurité critique
    developer_email = db.Column(db.String(150), nullable=True)

    # Email de l'admin — pour recevoir les alertes métier
    admin_email = db.Column(db.String(150), nullable=True)

    def __repr__(self):
        return f'<Configuration mode={self.mode}>'


# ============================================================
# TABLE : UTILISATEURS
# Personnes qui ont accès à l'interface web du système
# Rôles : 'admin', 'enseignant', 'agent'
# (manager et rh sont des alias selon le mode)
# ============================================================
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Informations personnelles
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)

    # Email institutionnel — utilisé pour la connexion
    email = db.Column(db.String(150), unique=True, nullable=False)

    # Mot de passe haché avec bcrypt — JAMAIS stocké en clair
    password_hash = db.Column(db.String(255), nullable=False)

    # Département ou filière — aide l'admin à attribuer le bon rôle
    department = db.Column(db.String(100), nullable=True)

    # -------------------------------------------------------
    # GESTION DES RÔLES
    # -------------------------------------------------------
    # Rôle attribué par l'admin après validation
    # Valeurs : 'admin', 'enseignant', 'agent'
    # NULL tant que le compte n'est pas validé
    role = db.Column(db.String(50), nullable=True, default=None)

    # Rôle souhaité par l'utilisateur lors de l'inscription
    # Valeurs possibles : 'enseignant' ou 'agent' uniquement
    # L'admin ne s'inscrit jamais via la page publique
    requested_role = db.Column(db.String(50), nullable=True)

    # -------------------------------------------------------
    # GESTION DES STATUTS DU COMPTE
    # -------------------------------------------------------
    # Statut du compte :
    # 'en_attente'     → inscrit, email non encore vérifié
    # 'email_verifie'  → email confirmé, attend validation admin
    # 'actif'          → rôle attribué, accès complet
    # 'desactive'      → bloqué par l'admin (ex: départ de l'établissement)
    # 'rejete'         → demande refusée par l'admin
    account_status = db.Column(db.String(20), nullable=False, default='en_attente')

    # Raison du rejet par l'admin (si statut = 'rejete')
    rejection_reason = db.Column(db.String(255), nullable=True)

    # -------------------------------------------------------
    # VÉRIFICATION DE L'EMAIL
    # -------------------------------------------------------
    # Token envoyé par email pour confirmer l'adresse
    email_token = db.Column(db.String(255), nullable=True)

    # Date d'expiration du token (valable 24h en général)
    email_token_expiry = db.Column(db.DateTime, nullable=True)

    # -------------------------------------------------------
    # VALIDATION PAR L'ADMIN
    # -------------------------------------------------------
    # ID de l'admin qui a validé ou rejeté la demande
    validated_by = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)

    # Date de validation ou de rejet
    validated_at = db.Column(db.DateTime, nullable=True)

    # -------------------------------------------------------
    # SÉCURITÉ — TENTATIVES DE CONNEXION
    # -------------------------------------------------------
    # Nombre de tentatives de connexion échouées consécutives
    failed_attempts = db.Column(db.Integer, default=0)

    # Indique si le compte est actif (False = bloqué après tentatives)
    is_active = db.Column(db.Boolean, default=True)

    # -------------------------------------------------------
    # MÉTADONNÉES
    # -------------------------------------------------------
    # Date et heure de la dernière connexion réussie
    last_login = db.Column(db.DateTime, nullable=True)

    # Date de création du compte
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # -------------------------------------------------------
    # RELATIONS
    # -------------------------------------------------------
    # Sessions créées par cet utilisateur (enseignant/manager)
    sessions = db.relationship('Session', backref='creator', lazy=True,
                               foreign_keys='Session.user_id')

    # Personnes créées par cet utilisateur (agent/RH)
    persons_created = db.relationship('Person', backref='created_by_user', lazy=True,
                                      foreign_keys='Person.created_by')

    # Cartes RFID attribuées par cet utilisateur (agent/RH)
    cards_assigned = db.relationship('RFIDCard', backref='assigned_by_user', lazy=True,
                                     foreign_keys='RFIDCard.assigned_by')

    def __repr__(self):
        return f'<User {self.email} role={self.role} status={self.account_status}>'

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'

    def is_admin(self):
        return self.role == 'admin'

    def is_enseignant(self):
        return self.role == 'enseignant'

    def is_agent(self):
        return self.role == 'agent'

    def is_account_active(self):
        return self.account_status == 'actif' and self.is_active


# ============================================================
# TABLE : PERSONNES
# Étudiants (mode école) ou Employés (mode entreprise)
# Ces personnes N'ONT PAS accès à l'interface web
# Elles s'authentifient uniquement via carte RFID + visage
# ============================================================
class Person(db.Model):
    __tablename__ = 'persons'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Informations personnelles
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=True)

    # Identifiant selon le contexte :
    # Mode école     → CNE ou Code étudiant
    # Mode entreprise → Matricule ou Badge employé
    identifier = db.Column(db.String(100), unique=True, nullable=False)

    # Département / Filière selon le contexte :
    # Mode école     → Filière (ex: Cybersécurité, Informatique)
    # Mode entreprise → Département (ex: IT, RH, Finance)
    department = db.Column(db.String(100), nullable=True)

    # Niveau / Poste selon le contexte :
    # Mode école     → Niveau (ex: 2ème année)
    # Mode entreprise → Poste (ex: Développeur, Manager)
    level_or_position = db.Column(db.String(100), nullable=True)

    # Groupe / Site selon le contexte :
    # Mode école     → Groupe (ex: G1, G2)
    # Mode entreprise → Site ou Bureau (ex: Casablanca, Rabat)
    group_or_site = db.Column(db.String(100), nullable=True)

    # Statut : True = actif, False = inactif (ex: étudiant exclu, employé parti)
    is_active = db.Column(db.Boolean, default=True)

    # Agent ou RH qui a créé ce profil
    created_by = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)

    # Date de création du profil
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # -------------------------------------------------------
    # RELATIONS
    # -------------------------------------------------------
    # Une personne peut avoir plusieurs cartes RFID
    # (historique : active, révoquée, perdue...)
    rfid_cards = db.relationship('RFIDCard', backref='person', lazy=True,
                                 foreign_keys='RFIDCard.person_id')

    # Plusieurs photos par personne pour améliorer la précision DeepFace
    photos = db.relationship('Photo', backref='person', lazy=True,
                             cascade='all, delete-orphan')

    # Historique de toutes les présences de cette personne
    attendances = db.relationship('Attendance', backref='person', lazy=True)

    def __repr__(self):
        return f'<Person {self.first_name} {self.last_name} id={self.identifier}>'

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'

    def get_active_card(self):
        """Retourne la carte RFID active de la personne"""
        return RFIDCard.query.filter_by(
            person_id=self.id,
            status='actif'
        ).first()

    def get_main_photo(self):
        """Retourne la photo principale de la personne"""
        return Photo.query.filter_by(
            person_id=self.id,
            is_main=True
        ).first()


# ============================================================
# TABLE : PHOTOS
# Photos faciales des personnes — chiffrées AES-256
# Plusieurs photos par personne pour améliorer DeepFace
# ============================================================
class Photo(db.Model):
    __tablename__ = 'photos'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Référence vers la personne propriétaire de la photo
    person_id = db.Column(db.String(36), db.ForeignKey('persons.id'), nullable=False)

    # Chemin du fichier chiffré sur le serveur
    # Le contenu est chiffré en AES-256 avant stockage
    file_path = db.Column(db.String(255), nullable=False)

    # Indique si c'est la photo principale utilisée par DeepFace
    is_main = db.Column(db.Boolean, default=False)

    # Score de qualité de la photo (0 à 1) — calculé à l'import
    # Une photo doit avoir un score >= 0.7 pour être acceptée
    quality_score = db.Column(db.Float, nullable=True)

    # Confirme que la photo est bien chiffrée
    is_encrypted = db.Column(db.Boolean, default=True)

    # Date d'ajout de la photo
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Photo person={self.person_id} main={self.is_main}>'


# ============================================================
# TABLE : CARTES RFID
# Cartes RFID associées aux personnes
# Historique complet : active, révoquée, perdue, expirée
# ============================================================
class RFIDCard(db.Model):
    __tablename__ = 'rfid_cards'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Numéro de la carte RFID — chiffré en AES-256 en base
    rfid_number = db.Column(db.String(255), unique=True, nullable=False)

    # Référence vers la personne propriétaire de la carte
    person_id = db.Column(db.String(36), db.ForeignKey('persons.id'), nullable=False)

    # Statut de la carte :
    # 'actif'    → carte valide et utilisable
    # 'revoque'  → carte désactivée volontairement
    # 'perdu'    → carte signalée perdue ou volée
    # 'expire'   → carte expirée
    status = db.Column(db.String(20), nullable=False, default='actif')

    # Agent ou RH qui a attribué cette carte
    assigned_by = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)

    # Date d'attribution de la carte
    assigned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Date de révocation (si carte perdue, volée ou désactivée)
    revoked_at = db.Column(db.DateTime, nullable=True)

    # Raison de la révocation
    revocation_reason = db.Column(db.String(255), nullable=True)

    # -------------------------------------------------------
    # RELATIONS
    # -------------------------------------------------------
    # Présences enregistrées avec cette carte
    attendances = db.relationship('Attendance', backref='rfid_card', lazy=True)

    def __repr__(self):
        return f'<RFIDCard status={self.status} person={self.person_id}>'

    def is_valid(self):
        """Vérifie si la carte est active et utilisable"""
        return self.status == 'actif'

    def revoke(self, reason):
        """Révoquer la carte avec une raison"""
        self.status = 'revoque'
        self.revoked_at =datetime.now(timezone.utc)
        self.revocation_reason = reason


# ============================================================
# TABLE : SESSIONS
# Cours (mode école) ou Périodes de travail (mode entreprise)
# Créées par un enseignant (école) ou un manager (entreprise)
# ============================================================
class Session(db.Model):
    __tablename__ = 'sessions'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Nom selon le contexte :
    # Mode école     → Nom du cours (ex: Cybersécurité - Groupe G1)
    # Mode entreprise → Période (ex: Journée du 23/04/2026)
    name = db.Column(db.String(200), nullable=False)

    # Enseignant ou Manager qui a créé la session
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)

    # Lieu selon le contexte :
    # Mode école     → Salle de cours (ex: Salle B12)
    # Mode entreprise → Site ou entrée (ex: Entrée principale Casablanca)
    location = db.Column(db.String(200), nullable=True)

    # Date et heure de début de la session
    start_time = db.Column(db.DateTime, nullable=False)

    # Date et heure de fin de la session
    end_time = db.Column(db.DateTime, nullable=True)

    # Date de création de la session
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # -------------------------------------------------------
    # RELATIONS
    # -------------------------------------------------------
    # Toutes les présences enregistrées pour cette session
    attendances = db.relationship('Attendance', backref='session', lazy=True,
                                  cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Session {self.name} lieu={self.location}>'

    def is_active(self):
        """Vérifie si la session est en cours"""
        now = datetime.now(timezone.utc)
        return self.start_time <= now <= (self.end_time or now)

    def get_attendance_count(self):
        """Retourne le nombre de présences validées"""
        return Attendance.query.filter_by(
            session_id=self.id,
            status='present'
        ).count()


# ============================================================
# TABLE : PRÉSENCES
# Enregistrement de chaque présence validée ou refusée
# Contient le score DeepFace pour audit et traçabilité
# ============================================================
class Attendance(db.Model):
    __tablename__ = 'attendances'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Référence vers la personne (étudiant ou employé)
    person_id = db.Column(db.String(36), db.ForeignKey('persons.id'), nullable=False)

    # Référence vers la session (cours ou journée)
    session_id = db.Column(db.String(36), db.ForeignKey('sessions.id'), nullable=False)

    # Référence vers la carte RFID utilisée (nullable si validation manuelle)
    rfid_card_id = db.Column(db.String(36), db.ForeignKey('rfid_cards.id'), nullable=True)

    # Date et heure exacte de l'enregistrement de la présence
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Score de similarité retourné par DeepFace (0 à 1)
    # Stocké pour audit : permet de retracer chaque décision du système
    similarity_score = db.Column(db.Float, nullable=True)

    # Statut de la présence :
    # 'present' → présence validée normalement
    # 'absent'  → personne absente (marqué automatiquement en fin de session)
    # 'retard'  → arrivée après l'heure prévue
    # 'refuse'  → tentative rejetée (fraude, score insuffisant, carte invalide)
    status = db.Column(db.String(20), nullable=False, default='present')

    # Méthode de validation :
    # 'rfid_visage' → validation automatique par carte RFID + reconnaissance faciale
    # 'manuel'      → validation manuelle par l'enseignant ou l'admin (secours)
    validation_method = db.Column(db.String(50), default='rfid_visage')

    def __repr__(self):
        return f'<Attendance person={self.person_id} status={self.status}>'

    def is_duplicate(self):
        """Vérifie si cette personne a déjà une présence dans cette session"""
        return Attendance.query.filter_by(
            person_id=self.person_id,
            session_id=self.session_id,
            status='present'
        ).count() > 0


# ============================================================
# TABLE : JOURNAL DE SÉCURITÉ
# Enregistrement de tous les événements du système
# Deux destinataires possibles : admin (métier) ou développeur (technique)
# ============================================================
class SecurityLog(db.Model):
    __tablename__ = 'security_logs'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Date et heure de l'événement
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Type d'événement — exemples :
    # 'connexion_reussie', 'connexion_echouee', 'deconnexion'
    # 'compte_bloque', 'compte_debloque', 'compte_valide', 'compte_rejete'
    # 'carte_inconnue', 'carte_revoquee', 'carte_clonee'
    # 'presence_validee', 'presence_refusee', 'tentative_fraude'
    # 'injection_sql', 'erreur_serveur', 'bdd_inaccessible'
    event_type = db.Column(db.String(100), nullable=False)

    # Niveau de gravité :
    # 'info'     → événement normal (connexion réussie, présence validée)
    # 'warning'  → événement suspect (tentative échouée, score bas)
    # 'critical' → événement grave (fraude, injection SQL, clonage RFID)
    severity = db.Column(db.String(20), nullable=False, default='info')

    # Description détaillée de l'événement
    description = db.Column(db.Text, nullable=True)

    # Adresse IP de la requête
    ip_address = db.Column(db.String(50), nullable=True)

    # Résultat : 'succes', 'echec', 'bloque'
    result = db.Column(db.String(20), nullable=True)

    # Destinataire de l'alerte :
    # 'admin'       → alertes métier (absences, présences refusées, comptes en attente)
    # 'developpeur' → alertes techniques (erreurs serveur, injection SQL, clonage RFID)
    # 'les_deux'    → événements très critiques envoyés aux deux
    recipient = db.Column(db.String(20), nullable=False, default='admin')

    # -------------------------------------------------------
    # RÉFÉRENCES OPTIONNELLES selon le type d'événement
    # -------------------------------------------------------
    # Utilisateur système concerné (admin, enseignant, agent)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)

    # Personne concernée (étudiant ou employé)
    person_id = db.Column(db.String(36), db.ForeignKey('persons.id'), nullable=True)

    # Carte RFID concernée
    rfid_card_id = db.Column(db.String(36), db.ForeignKey('rfid_cards.id'), nullable=True)

    def __repr__(self):
        return f'<SecurityLog {self.event_type} severity={self.severity} to={self.recipient}>'