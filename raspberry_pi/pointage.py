import cv2
import base64
import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
#SERVEUR_URL = os.getenv('SERVEUR_URL', 'http://192.168.1.7:5000')
SERVEUR_URL = os.getenv('SERVEUR_URL', 'http://127.0.0.1:5000')
API_POINTAGE = f"{SERVEUR_URL}/presences/api/pointer"

# ============================================================
# SIMULATION RFID (remplacer par RC522 quand matériel dispo)
# ============================================================
def lire_carte_rfid():
    """
    Sur PC : saisie manuelle du numéro RFID
    Sur Raspberry Pi : lecture via RC522
    """
    # TODO: Remplacer par le code RC522 quand matériel disponible
    # from mfrc522 import SimpleMFRC522
    # reader = SimpleMFRC522()
    # id, text = reader.read()
    # return str(id)
    
    numero = input("Entrez le numéro RFID (ou scannez la carte) : ").strip().upper()
    return numero


# ============================================================
# CAPTURE PHOTO
# ============================================================
def capturer_photo():
    """Capturer une photo avec la webcam."""
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Erreur : impossible d'ouvrir la caméra")
        return None
    
    print("Regardez la caméra...")
    time.sleep(1)  # Laisser le temps de se positionner
    
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        print("Erreur : impossible de capturer la photo")
        return None
    
    # Afficher la photo capturée
    cv2.imshow("Photo capturée - Appuyez sur une touche", frame)
    cv2.waitKey(2000)
    cv2.destroyAllWindows()
    
    # Encoder en base64
    _, buffer = cv2.imencode('.jpg', frame)
    photo_base64 = base64.b64encode(buffer).decode('utf-8')
    
    return photo_base64


# ============================================================
# AFFICHER RÉSULTAT
# ============================================================
def afficher_resultat(succes, message, personne=None, statut=None):
    """Afficher le résultat sur l'écran."""
    print("\n" + "="*50)
    if succes:
        print(f"✅ PRÉSENCE VALIDÉE")
        print(f"   Personne : {personne}")
        print(f"   Statut   : {statut.upper()}")
    else:
        print(f"❌ REFUSÉ")
        print(f"   Raison : {message}")
    print("="*50 + "\n")
    
    # TODO: Ajouter LED verte/rouge quand Raspberry Pi disponible
    # import RPi.GPIO as GPIO
    # if succes:
    #     GPIO.output(LED_VERTE, GPIO.HIGH)
    #     time.sleep(2)
    #     GPIO.output(LED_VERTE, GPIO.LOW)
    # else:
    #     GPIO.output(LED_ROUGE, GPIO.HIGH)
    #     time.sleep(2)
    #     GPIO.output(LED_ROUGE, GPIO.LOW)


# ============================================================
# FLUX PRINCIPAL
# ============================================================
def main():
    print("=== Système de Pointage ===")
    print(f"Serveur : {SERVEUR_URL}")
    print("Appuyez sur Ctrl+C pour quitter\n")
    
    while True:
        try:
            # Étape 1 : Lire la carte RFID
            print("Approchez votre carte RFID...")
            numero_rfid = lire_carte_rfid()
            
            if not numero_rfid:
                continue
            
            print(f"Carte lue : {numero_rfid}")
            
            # Étape 2 : Capturer la photo
            print("Capture photo en cours...")
            photo_base64 = capturer_photo()
            
            if not photo_base64:
                print("Erreur capture photo")
                continue
            
            # Étape 3 : Envoyer au serveur
            print("Vérification en cours...")
            response = requests.post(
                API_POINTAGE,
                json={
                    'numero_rfid': numero_rfid,
                    'photo': photo_base64
                },
                timeout=30
            )
            
            data = response.json()
            
            # Étape 4 : Afficher le résultat
            afficher_resultat(
                succes=data.get('succes', False),
                message=data.get('message', 'Erreur inconnue'),
                personne=data.get('personne'),
                statut=data.get('statut')
            )
            
            time.sleep(2)  # Pause entre deux pointages
            
        except KeyboardInterrupt:
            print("\nArrêt du système...")
            break
        except requests.exceptions.ConnectionError:
            print("❌ Impossible de contacter le serveur")
            time.sleep(5)
        except Exception as e:
            print(f"Erreur : {str(e)}")
            time.sleep(2)


if __name__ == '__main__':
    main()