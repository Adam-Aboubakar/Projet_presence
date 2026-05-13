from deepface import DeepFace
import cv2

cap = cv2.VideoCapture(0)
print("=== TEST COMPARAISON DE VISAGES ===")
print("Etape 1 : Capture photo de reference (comme la photo stockee en BDD)")
print("Appuie sur ESPACE pour capturer, Q pour quitter")

while True:
    ret, frame = cap.read()
    if not ret:
        break
    cv2.putText(frame, "PHOTO REFERENCE - Appuie ESPACE", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.imshow("Webcam", frame)
    key = cv2.waitKey(1)
    if key == ord(' '):
        cv2.imwrite("photo_reference.jpg", frame)
        print("Photo de reference capturee !")
        break
    elif key == ord('q'):
        break

print("\nEtape 2 : Capture photo de verification (comme au moment du pointage)")
print("Appuie sur ESPACE pour capturer")

while True:
    ret, frame = cap.read()
    if not ret:
        break
    cv2.putText(frame, "PHOTO VERIFICATION - Appuie ESPACE", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    cv2.imshow("Webcam", frame)
    key = cv2.waitKey(1)
    if key == ord(' '):
        cv2.imwrite("photo_verification.jpg", frame)
        print("Photo de verification capturee !")
        break
    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

print("\nComparaison en cours...")
try:
    result = DeepFace.verify(
        img1_path="photo_reference.jpg",
        img2_path="photo_verification.jpg",
        enforce_detection=False
    )
    
    distance = result['distance']
    seuil = result['threshold']
    verified = result['verified']
    
    print(f"Distance     : {distance:.4f}")
    print(f"Seuil        : {seuil:.4f}")
    print(f"Resultat     : {'✅ MEME PERSONNE' if verified else '❌ PERSONNE DIFFERENTE'}")
    
except Exception as e:
    print(f"Erreur : {e}")