import uuid
from datetime import datetime
from flask_login import UserMixin
from app import db

# --- Fonction utilitaire ---
def generate_uuid():
    """Générer un identifiant unique universel (UUID)"""
    return str(uuid.uuid4())


# ============================================================
# TABLE : CONFIGURATION
# Paramètres globaux du système (mode, seuils, etc.)
# ============================================================
class Configuration(db.Model):
    __tablename__ = 'configuration'

    # Identifiant unique — UUID au lieu de 1,2,3 pour la sécurité
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Mode du système : 'ecole' ou 'entreprise'
    mode = db.Column(db.String(20), nullable=False, default='ecole')

    # Seuil minimum de similarité faciale (0.85 = 85%)
    similarity_threshold = db.Column(db.Float, nullable=False, default=0.85)

    # Nombre maximum de tentatives échouées avant blocage
    max_attempts = db.Column(db.Integer, nullable=False, default=5)

    # Durée de conservation des données en jours (RGPD)
    data_retention_days = db.Column(db.Integer, nullable=False, default=365)

    # Langue par défaut du système
    default_language = db.Column(db.String(5), nullable=False, default='fr')

    def __repr__(self):
        return f'<Configuration mode={self.mode}>'


# ============================================================
# TABLE : UTILISATEURS
# Personnes qui ont accès à l'interface du système
# ============================================================
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    # Identifiant unique UUID
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Informations personnelles
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)

    # Email unique — utilisé pour la connexion
    email = db.Column(db.String(150), unique=True, nullable=False)

    # Mot de passe haché avec bcrypt — JAMAIS en clair !
    password_hash = db.Column(db.String(255), nullable=False)

    # Rôle : 'admin', 'enseignant', 'agent', 'manager', 'rh'
    role = db.Column(db.String(50), nullable=False, default='enseignant')

    # Statut : True = actif, False = bloqué
    is_active = db.Column(db.Boolean, default=True)

    # Nombre de tentatives de connexion échouées
    failed_attempts = db.Column(db.Integer, default=0)

    # Date et heure de la dernière connexion
    last_login = db.Column(db.DateTime, nullable=True)

    # Date de création du compte
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.email} role={self.role}>'


# ============================================================
# TABLE : PERSONNES
# Étudiants (mode école) ou Employés (mode entreprise)
# ============================================================
class Person(db.Model):
    __tablename__ = 'persons'

    # Identifiant unique UUID
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Informations personnelles
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=True)

    # Identifiant selon le contexte :
    # Mode école → CNE / Code étudiant
    # Mode entreprise → Matricule / Badge
    identifier = db.Column(db.String(100), unique=True, nullable=False)

    # Groupe selon le contexte :
    # Mode école → Filière (ex: Informatique, Cybersécurité)
    # Mode entreprise → Département (ex: IT, RH, Finance)
    department = db.Column(db.String(100), nullable=True)

    # Niveau selon le contexte :
    # Mode école → Niveau (ex: 2ème année)
    # Mode entreprise → Poste (ex: Développeur, Manager)
    level_or_position = db.Column(db.String(100), nullable=True)

    # Groupe selon le contexte :
    # Mode école → Groupe (ex: G1, G2)
    # Mode entreprise → Site / Bureau (ex: Casablanca, Rabat)
    group_or_site = db.Column(db.String(100), nullable=True)

    # Photo du visage chiffrée en AES-256
    # On stocke le chemin du fichier chiffré, pas l'image directement
    photo_path = db.Column(db.String(255), nullable=True)

    # Statut : True = actif, False = inactif
    is_active = db.Column(db.Boolean, default=True)

    # Date d'inscription / d'embauche
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations avec les autres tables
    rfid_cards = db.relationship('RFIDCard', backref='person', lazy=True)
    attendances = db.relationship('Attendance', backref='person', lazy=True)

    def __repr__(self):
        return f'<Person {self.first_name} {self.last_name}>'


# ============================================================
# TABLE : CARTES_RFID
# Cartes RFID associées aux personnes
# ============================================================
class RFIDCard(db.Model):
    __tablename__ = 'rfid_cards'

    # Identifiant unique UUID
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Numéro de la carte RFID — chiffré en base
    rfid_number = db.Column(db.String(255), unique=True, nullable=False)

    # Référence vers la personne propriétaire de la carte
    person_id = db.Column(db.String(36), db.ForeignKey('persons.id'), nullable=False)

    # Statut : 'actif', 'révoqué', 'perdu', 'expiré'
    status = db.Column(db.String(20), nullable=False, default='actif')

    # Date d'attribution de la carte
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Date de révocation (si carte perdue ou volée)
    revoked_at = db.Column(db.DateTime, nullable=True)

    # Raison de la révocation
    revocation_reason = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f'<RFIDCard {self.rfid_number} status={self.status}>'


# ============================================================
# TABLE : SESSIONS
# Cours (mode école) ou Journées de travail (mode entreprise)
# ============================================================
class Session(db.Model):
    __tablename__ = 'sessions'

    # Identifiant unique UUID
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Nom selon le contexte :
    # Mode école → Nom du cours (ex: Mathématiques, Cybersécurité)
    # Mode entreprise → Journée de travail (ex: Lundi 19/04/2026)
    name = db.Column(db.String(200), nullable=False)

    # Référence vers l'utilisateur responsable :
    # Mode école → Enseignant
    # Mode entreprise → Manager
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)

    # Lieu selon le contexte :
    # Mode école → Salle de cours (ex: Salle B12)
    # Mode entreprise → Site / Point de pointage (ex: Entrée principale)
    location = db.Column(db.String(200), nullable=True)

    # Date et heure de début
    start_time = db.Column(db.DateTime, nullable=False)

    # Date et heure de fin
    end_time = db.Column(db.DateTime, nullable=True)

    # Date de création
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relation avec les présences
    attendances = db.relationship('Attendance', backref='session', lazy=True)

    def __repr__(self):
        return f'<Session {self.name}>'


# ============================================================
# TABLE : PRESENCES
# Enregistrement de chaque présence validée ou refusée
# ============================================================
class Attendance(db.Model):
    __tablename__ = 'attendances'

    # Identifiant unique UUID
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Référence vers la personne (étudiant ou employé)
    person_id = db.Column(db.String(36), db.ForeignKey('persons.id'), nullable=False)

    # Référence vers la session (cours ou journée)
    session_id = db.Column(db.String(36), db.ForeignKey('sessions.id'), nullable=False)

    # Référence vers la carte RFID utilisée
    rfid_card_id = db.Column(db.String(36), db.ForeignKey('rfid_cards.id'), nullable=True)

    # Date et heure exacte de la présence
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Score de similarité faciale (0 à 1)
    # Stocké pour audit et traçabilité
    similarity_score = db.Column(db.Float, nullable=True)

    # Statut : 'present', 'absent', 'retard'
    status = db.Column(db.String(20), nullable=False, default='present')

    # Méthode de validation : 'rfid_face', 'manuel'
    validation_method = db.Column(db.String(50), default='rfid_face')

    def __repr__(self):
        return f'<Attendance person={self.person_id} status={self.status}>'


# ============================================================
# TABLE : JOURNAL DE SÉCURITÉ
# Enregistrement de tous les événements de sécurité
# ============================================================
class SecurityLog(db.Model):
    __tablename__ = 'security_logs'

    # Identifiant unique UUID
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Date et heure de l'événement
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Type d'événement :
    # 'connexion', 'deconnexion', 'echec_auth', 'carte_inconnue',
    # 'photo_refusee', 'tentative_fraude', 'modification_bdd'
    event_type = db.Column(db.String(100), nullable=False)

    # Référence vers la personne concernée (peut être vide)
    person_id = db.Column(db.String(36), db.ForeignKey('persons.id'), nullable=True)

    # Référence vers la carte RFID concernée (peut être vide)
    rfid_card_id = db.Column(db.String(36), db.ForeignKey('rfid_cards.id'), nullable=True)

    # Description détaillée de l'événement
    description = db.Column(db.Text, nullable=True)

    # Niveau de gravité : 'info', 'warning', 'critical'
    severity = db.Column(db.String(20), nullable=False, default='info')

    # Adresse IP de la requête
    ip_address = db.Column(db.String(50), nullable=True)

    # Résultat : 'succes', 'echec', 'bloque'
    result = db.Column(db.String(20), nullable=True)

    def __repr__(self):
        return f'<SecurityLog {self.event_type} severity={self.severity}>'