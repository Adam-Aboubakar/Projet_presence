import uuid
from datetime import datetime, timezone
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

    # Mode du système : 'ecole' ou 'entreprise'
    mode = db.Column(db.String(20), nullable=False, default='ecole')

    # Seuil minimum de similarité faciale (ex: 0.90 = 90%)
    seuil_similarite = db.Column(db.Float, nullable=False, default=0.90)

    # Nombre maximum de tentatives échouées avant blocage du compte
    max_tentatives = db.Column(db.Integer, nullable=False, default=5)

    # Durée de conservation des données biométriques en jours (RGPD)
    duree_retention_jours = db.Column(db.Integer, nullable=False, default=365)

    # Langue par défaut : 'fr', 'en', 'ar'
    langue_defaut = db.Column(db.String(5), nullable=False, default='fr')

    # Email du développeur — alertes techniques et sécurité critique
    email_developpeur = db.Column(db.String(150), nullable=True)

    # Email de l'admin — alertes métier
    email_admin = db.Column(db.String(150), nullable=True)

    def __repr__(self):
        return f'<Configuration mode={self.mode}>'


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
    # Incrémentée automatiquement à chaque modification
    # Empêche 2 admins de modifier le même enregistrement simultanément
    version = db.Column(db.Integer, default=1, nullable=False)

    # Informations personnelles
    prenom = db.Column(db.String(100), nullable=False)
    nom = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)

    # Mot de passe haché avec bcrypt — JAMAIS stocké en clair
    mot_de_passe_hache = db.Column(db.String(255), nullable=False)

    # Département ou filière — aide l'admin à attribuer le bon rôle
    departement = db.Column(db.String(100), nullable=True)

    # -------------------------------------------------------
    # GESTION DES RÔLES
    # -------------------------------------------------------
    # Rôle attribué par l'admin après validation
    # Valeurs : 'admin', 'enseignant', 'agent'
    # NULL tant que le compte n'est pas validé
    role = db.Column(db.String(50), nullable=True, default=None)

    # Nouveau commentaire
    # Toujours NULL — l'admin attribue directement le rôle
    # lors de la validation du compte via son interface
    role_souhaite = db.Column(db.String(50), nullable=True)

    # -------------------------------------------------------
    # GESTION DES STATUTS DU COMPTE
    # -------------------------------------------------------
    # Statut du compte :
    # 'en_attente'     → inscrit, email non encore vérifié
    # 'email_verifie'  → email confirmé, attend validation admin
    # 'actif'          → rôle attribué, accès complet
    # 'desactive'      → bloqué par l'admin
    # 'rejete'         → demande refusée par l'admin
    statut_compte = db.Column(db.String(20), nullable=False, default='en_attente')

    # Raison du rejet par l'admin (si statut = 'rejete')
    raison_rejet = db.Column(db.String(255), nullable=True)

    # -------------------------------------------------------
    # VÉRIFICATION DE L'EMAIL
    # -------------------------------------------------------
    # Token envoyé par email pour confirmer l'adresse
    token_email = db.Column(db.String(255), nullable=True)

    # Date d'expiration du token (valable 24h)
    expiration_token = db.Column(db.DateTime, nullable=True)

    # -------------------------------------------------------
    # VALIDATION PAR L'ADMIN
    # -------------------------------------------------------
    # ID de l'admin qui a validé ou rejeté la demande
    valide_par = db.Column(db.String(36), db.ForeignKey('utilisateurs.id'), nullable=True)

    # Date de validation ou de rejet
    valide_le = db.Column(db.DateTime, nullable=True)

    # -------------------------------------------------------
    # SÉCURITÉ — TENTATIVES DE CONNEXION
    # -------------------------------------------------------
    # Nombre de tentatives de connexion échouées consécutives
    tentatives_echouees = db.Column(db.Integer, default=0)

    # Indique si le compte est actif (False = bloqué après tentatives)
    est_actif = db.Column(db.Boolean, default=True)

    # -------------------------------------------------------
    # MÉTADONNÉES
    # -------------------------------------------------------
    # Date et heure de la dernière connexion réussie
    derniere_connexion = db.Column(db.DateTime, nullable=True)

    # Date de création du compte
    cree_le = db.Column(db.DateTime, default=datetime.utcnow)

    # -------------------------------------------------------
    # OPTIMISTIC LOCKING
    # Empêche les conflits lors d'accès simultanés par plusieurs admins
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
        """Retourne le nom complet de l'utilisateur"""
        return f'{self.prenom} {self.nom}'

    def est_admin(self):
        """Vérifie si l'utilisateur est admin"""
        return self.role == 'admin'

    def est_enseignant(self):
        """Vérifie si l'utilisateur est enseignant"""
        return self.role == 'enseignant'

    def est_agent(self):
        """Vérifie si l'utilisateur est agent"""
        return self.role == 'agent'

    def compte_actif(self):
        """Vérifie si le compte est actif et non bloqué"""
        return self.statut_compte == 'actif' and self.est_actif

    @staticmethod
    def peut_ajouter_admin():
        """Vérifie si on peut encore ajouter un admin — maximum 3"""
        nombre = Utilisateur.query.filter_by(role='admin').count()
        return nombre < 3

    @staticmethod
    def nombre_admins():
        """Retourne le nombre d'admins actuels"""
        return Utilisateur.query.filter_by(role='admin').count()


# ============================================================
# TABLE : PERSONNES
# Étudiants (mode école) ou Employés (mode entreprise)
# Ces personnes N'ONT PAS accès à l'interface web
# Elles s'authentifient uniquement via carte RFID + visage
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

    # Département / Filière selon le contexte :
    # Mode école      → Filière (ex: Cybersécurité)
    # Mode entreprise → Département (ex: IT, RH)
    departement = db.Column(db.String(100), nullable=True)

    # Niveau / Poste selon le contexte :
    # Mode école      → Niveau (ex: 2ème année)
    # Mode entreprise → Poste (ex: Développeur)
    niveau_ou_poste = db.Column(db.String(100), nullable=True)

    # Groupe / Site selon le contexte :
    # Mode école      → Groupe (ex: G1, G2)
    # Mode entreprise → Site (ex: Casablanca, Rabat)
    groupe_ou_site = db.Column(db.String(100), nullable=True)

    # Statut : True = actif, False = inactif
    est_actif = db.Column(db.Boolean, default=True)

    # Agent ou RH qui a créé ce profil
    cree_par = db.Column(db.String(36), db.ForeignKey('utilisateurs.id'), nullable=True)

    # Date de création du profil
    cree_le = db.Column(db.DateTime, default=datetime.utcnow)

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


# ============================================================
# TABLE : PHOTOS
# Photos faciales des personnes — chiffrées AES-256
# Plusieurs photos par personne pour améliorer DeepFace
# ============================================================
class Photo(db.Model):
    __tablename__ = 'photos'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # Référence vers la personne propriétaire de la photo
    personne_id = db.Column(db.String(36), db.ForeignKey('personnes.id'), nullable=False)

    # Chemin du fichier chiffré sur le serveur (AES-256)
    chemin_fichier = db.Column(db.String(255), nullable=False)

    # Indique si c'est la photo principale utilisée par DeepFace
    est_principale = db.Column(db.Boolean, default=False)

    # Score de qualité de la photo (0 à 1)
    # Une photo doit avoir un score >= 0.7 pour être acceptée
    score_qualite = db.Column(db.Float, nullable=True)

    # Confirme que la photo est bien chiffrée
    est_chiffree = db.Column(db.Boolean, default=True)

    # Date d'ajout de la photo
    cree_le = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Photo personne={self.personne_id} principale={self.est_principale}>'


# ============================================================
# TABLE : CARTES RFID
# Cartes RFID associées aux personnes
# Historique complet : active, révoquée, perdue, expirée
# ============================================================
class CarteRFID(db.Model):
    __tablename__ = 'cartes_rfid'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # Numéro de la carte RFID — chiffré en AES-256 en base
    numero_rfid = db.Column(db.String(255), unique=True, nullable=False)

    # Référence vers la personne propriétaire
    personne_id = db.Column(db.String(36), db.ForeignKey('personnes.id'), nullable=False)

    # Statut de la carte :
    # 'actif'   → carte valide et utilisable
    # 'revoque' → carte désactivée volontairement
    # 'perdu'   → carte signalée perdue ou volée
    # 'expire'  → carte expirée
    statut = db.Column(db.String(20), nullable=False, default='actif')

    # Agent ou RH qui a attribué cette carte
    attribuee_par = db.Column(db.String(36), db.ForeignKey('utilisateurs.id'), nullable=True)

    # Date d'attribution
    attribuee_le = db.Column(db.DateTime, default=datetime.utcnow)

    # Date de révocation
    revoquee_le = db.Column(db.DateTime, nullable=True)

    # Raison de la révocation
    raison_revocation = db.Column(db.String(255), nullable=True)

    # -------------------------------------------------------
    # RELATIONS
    # -------------------------------------------------------
    presences = db.relationship('Presence', backref='carte_rfid', lazy=True)

    def __repr__(self):
        return f'<CarteRFID statut={self.statut} personne={self.personne_id}>'

    def est_valide(self):
        """Vérifie si la carte est active et utilisable"""
        return self.statut == 'actif'

    def revoquer(self, raison):
        """Révoquer la carte avec une raison"""
        self.statut = 'revoque'
        self.revoquee_le = datetime.utcnow()
        self.raison_revocation = raison


# ============================================================
# TABLE : SESSIONS
# Cours (mode école) ou Périodes de travail (mode entreprise)
# ============================================================
class Session(db.Model):
    __tablename__ = 'sessions'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # Nom selon le contexte :
    # Mode école      → Nom du cours (ex: Cybersécurité G1)
    # Mode entreprise → Période (ex: Journée du 23/04/2026)
    nom = db.Column(db.String(200), nullable=False)

    # Enseignant ou Manager qui a créé la session
    cree_par = db.Column(db.String(36), db.ForeignKey('utilisateurs.id'), nullable=True)

    # Lieu selon le contexte :
    # Mode école      → Salle de cours (ex: Salle B12)
    # Mode entreprise → Site (ex: Entrée principale)
    lieu = db.Column(db.String(200), nullable=True)

    # Date et heure de début
    heure_debut = db.Column(db.DateTime, nullable=False)

    # Date et heure de fin
    heure_fin = db.Column(db.DateTime, nullable=True)

    # Date de création
    cree_le = db.Column(db.DateTime, default=datetime.utcnow)

    # -------------------------------------------------------
    # RELATIONS
    # -------------------------------------------------------
    presences = db.relationship('Presence', backref='session', lazy=True,
                                cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Session {self.nom} lieu={self.lieu}>'

    def est_active(self):
        """Vérifie si la session est en cours"""
        maintenant = datetime.utcnow()
        return self.heure_debut <= maintenant <= (self.heure_fin or maintenant)

    def nombre_presences(self):
        """Retourne le nombre de présences validées"""
        return Presence.query.filter_by(
            session_id=self.id,
            statut='present'
        ).count()


# ============================================================
# TABLE : PRESENCES
# Enregistrement de chaque présence validée ou refusée
# ============================================================
class Presence(db.Model):
    __tablename__ = 'presences'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # Référence vers la personne (étudiant ou employé)
    personne_id = db.Column(db.String(36), db.ForeignKey('personnes.id'), nullable=False)

    # Référence vers la session (cours ou journée)
    session_id = db.Column(db.String(36), db.ForeignKey('sessions.id'), nullable=False)

    # Référence vers la carte RFID utilisée (nullable si validation manuelle)
    carte_rfid_id = db.Column(db.String(36), db.ForeignKey('cartes_rfid.id'), nullable=True)

    # Date et heure exacte de l'enregistrement
    horodatage = db.Column(db.DateTime, default=datetime.utcnow)

    # Score de similarité retourné par DeepFace (0 à 1)
    score_similarite = db.Column(db.Float, nullable=True)

    # Statut de la présence :
    # 'present' → présence validée
    # 'absent'  → marqué automatiquement en fin de session
    # 'retard'  → arrivée après l'heure prévue
    # 'refuse'  → tentative rejetée (fraude, score insuffisant)
    statut = db.Column(db.String(20), nullable=False, default='present')

    # Méthode de validation :
    # 'rfid_visage' → automatique par RFID + reconnaissance faciale
    # 'manuel'      → validation manuelle par l'enseignant (secours)
    methode_validation = db.Column(db.String(50), default='rfid_visage')

    def __repr__(self):
        return f'<Presence personne={self.personne_id} statut={self.statut}>'

    def est_doublon(self):
        """Vérifie si cette personne a déjà une présence dans cette session"""
        return Presence.query.filter_by(
            personne_id=self.personne_id,
            session_id=self.session_id,
            statut='present'
        ).count() > 0


# ============================================================
# TABLE : JOURNAL DE SÉCURITÉ
# Enregistrement de tous les événements du système
# ============================================================
class JournalSecurite(db.Model):
    __tablename__ = 'journal_securite'

    id = db.Column(db.String(36), primary_key=True, default=generer_uuid)

    # Date et heure de l'événement
    horodatage = db.Column(db.DateTime, default=datetime.utcnow)

    # Type d'événement
    type_evenement = db.Column(db.String(100), nullable=False)

    # Niveau de gravité :
    # 'info'     → événement normal
    # 'warning'  → événement suspect
    # 'critique' → événement grave
    severite = db.Column(db.String(20), nullable=False, default='info')

    # Description détaillée
    description = db.Column(db.Text, nullable=True)

    # Adresse IP de la requête
    adresse_ip = db.Column(db.String(50), nullable=True)

    # Résultat : 'succes', 'echec', 'bloque'
    resultat = db.Column(db.String(20), nullable=True)

    # Destinataire de l'alerte :
    # 'admin'       → alertes métier
    # 'developpeur' → alertes techniques
    # 'les_deux'    → événements très critiques
    destinataire = db.Column(db.String(20), nullable=False, default='admin')

    # Références optionnelles
    utilisateur_id = db.Column(db.String(36), db.ForeignKey('utilisateurs.id'), nullable=True)
    personne_id = db.Column(db.String(36), db.ForeignKey('personnes.id'), nullable=True)
    carte_rfid_id = db.Column(db.String(36), db.ForeignKey('cartes_rfid.id'), nullable=True)

    def __repr__(self):
        return f'<JournalSecurite {self.type_evenement} severite={self.severite}>'