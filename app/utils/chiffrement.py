import os
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding


def _get_cle():
    """Récupérer la clé AES-256 depuis .env (32 bytes obligatoire)."""
    cle = os.getenv('AES_SECRET_KEY', '')
    if len(cle) != 32:
        raise ValueError(f"AES_SECRET_KEY doit faire exactement 32 caractères (actuel: {len(cle)})")
    return cle.encode('utf-8')


def chiffrer_texte(texte_clair):
    """Chiffrer un texte (ex: numéro RFID). Retourne une chaîne base64."""
    cle = _get_cle()
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(cle), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(128).padder()
    donnees = padder.update(texte_clair.encode('utf-8')) + padder.finalize()
    chiffre = encryptor.update(donnees) + encryptor.finalize()
    return base64.b64encode(iv + chiffre).decode('utf-8')


def dechiffrer_texte(texte_chiffre):
    """Déchiffrer un texte chiffré par chiffrer_texte()."""
    cle = _get_cle()
    donnees = base64.b64decode(texte_chiffre.encode('utf-8'))
    iv = donnees[:16]
    chiffre = donnees[16:]
    cipher = Cipher(algorithms.AES(cle), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded = decryptor.update(chiffre) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode('utf-8')


def chiffrer_fichier(donnees_binaires):
    """Chiffrer des données binaires (ex: photo JPG). Retourne bytes."""
    cle = _get_cle()
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(cle), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(128).padder()
    donnees = padder.update(donnees_binaires) + padder.finalize()
    chiffre = encryptor.update(donnees) + encryptor.finalize()
    return iv + chiffre


def dechiffrer_fichier(donnees_chiffrees):
    """Déchiffrer des données binaires chiffrées par chiffrer_fichier()."""
    cle = _get_cle()
    iv = donnees_chiffrees[:16]
    chiffre = donnees_chiffrees[16:]
    cipher = Cipher(algorithms.AES(cle), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded = decryptor.update(chiffre) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()