# test_deepface2.py
from deepface import DeepFace
import os

chemin_ref = r'test_ref_dechiffree.jpg'
chemin_live = r'test_photo.jpg'

print(f"ref existe: {os.path.exists(chemin_ref)}")
print(f"live existe: {os.path.exists(chemin_live)}")

result = DeepFace.verify(
    img1_path=chemin_ref,
    img2_path=chemin_live,
    enforce_detection=False
)

print(f"Distance : {result['distance']:.4f}")
print(f"Resultat : {'MEME PERSONNE' if result['verified'] else 'DIFFERENT'}")