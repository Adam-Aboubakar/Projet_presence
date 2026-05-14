import cv2
import base64
import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
SERVEUR_URL = os.getenv('SERVEUR_URL', 'http://192.168.1.7:5000')
API_POINTAGE = f"{SERVEUR_URL}/presences/api/pointer"

# GPIO Pins pour les LEDs
LED_VERTE = 11
LED_ROUGE = 13

# ============================================================
# INITIALISATION HARDWARE
# ============================================================
def init_hardware():
    """Initialiser le RC522 et les LEDs."""
    import RPi.GPIO as GPIO
    from mfrc522 import SimpleMFRC522
    
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(LED_VERTE, GPIO.OUT)
    GPIO.setup(LED_ROUGE, GPIO.OUT)
    
    reader = SimpleMFRC522()
    return reader, GPIO


# ============================================================
# LIRE CARTE RFID
# ============================================================
def lire_carte_rfid(reader):
    """Lire la carte RFID via RC522."""
    print("Approchez votre carte RFID...")
    id, text = reader.read()
    return str(id).strip()


# ============================================================
# CAPTURER PHOTO
# ============================================================
def capturer_photo():
    """Capturer une photo avec la webcam USB."""
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Erreur : caméra non disponible")
        return None
    
    # Laisser le temps à la caméra de s'initialiser
    time.sleep(0.5)
    
    # Capturer plusieurs frames pour avoir une bonne qualité
    for _ in range(5):
        ret, frame = cap.read()
    
    cap.release()
    
    if not ret:
        return None
    
    # Encoder en base64
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    photo_base64 = base64.b64encode(buffer).decode('utf-8')
    
    return photo_base64


# ============================================================
# AFFICHER RÉSULTAT AVEC LED
# ============================================================
def afficher_resultat(GPIO, succes, message, personne=None, statut=None):
    """Afficher le résultat avec les LEDs."""
    if succes:
        print(f"\n✅ {personne} — {statut.upper()}")
        # LED verte pendant 3 secondes
        GPIO.output(LED_VERTE, GPIO.HIGH)
        time.sleep(3)
        GPIO.output(LED_VERTE, GPIO.LOW)
    else:
        print(f"\n❌ {message}")
        # LED rouge clignote 3 fois
        for _ in range(3):
            GPIO.output(LED_ROUGE, GPIO.HIGH)
            time.sleep(0.3)
            GPIO.output(LED_ROUGE, GPIO.LOW)
            time.sleep(0.3)


# ============================================================
# FLUX PRINCIPAL
# ============================================================
def main():
    print("=== Système de Pointage — Raspberry Pi ===")
    print(f"Serveur : {SERVEUR_URL}")
    
    try:
        reader, GPIO = init_hardware()
    except Exception as e:
        print(f"Erreur initialisation hardware : {e}")
        return
    
    print("Système prêt !\n")
    
    try:
        while True:
            try:
                # Étape 1 : Lire la carte RFID
                numero_rfid = lire_carte_rfid(reader)
                print(f"Carte : {numero_rfid}")
                
                # Étape 2 : Capturer photo
                print("Regardez la caméra...")
                photo_base64 = capturer_photo()
                
                if not photo_base64:
                    afficher_resultat(GPIO, False, "Erreur caméra")
                    continue
                
                # Étape 3 : Envoyer au serveur
                print("Vérification...")
                response = requests.post(
                    API_POINTAGE,
                    json={
                        'numero_rfid': numero_rfid,
                        'photo': photo_base64
                    },
                    timeout=30
                )
                
                data = response.json()
                
                # Étape 4 : Résultat
                afficher_resultat(
                    GPIO,
                    succes=data.get('succes', False),
                    message=data.get('message', 'Erreur'),
                    personne=data.get('personne'),
                    statut=data.get('statut')
                )
                
                time.sleep(1)
                
            except requests.exceptions.ConnectionError:
                print("❌ Serveur inaccessible")
                GPIO.output(LED_ROUGE, GPIO.HIGH)
                time.sleep(5)
                GPIO.output(LED_ROUGE, GPIO.LOW)
                
            except Exception as e:
                print(f"Erreur : {str(e)}")
                time.sleep(2)
    
    except KeyboardInterrupt:
        print("\nArrêt...")
    
    finally:
        GPIO.cleanup()


if __name__ == '__main__':
    main()