import cv2
import base64
import requests
import time
import threading
import numpy as np
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SERVEUR_URL = os.getenv('SERVEUR_URL', 'http://127.0.0.1:5000')
API_POINTAGE = f"{SERVEUR_URL}/presences/api/pointer"
API_VERIFIER = f"{SERVEUR_URL}/sessions/api/verifier-rfid"
API_SESSION  = f"{SERVEUR_URL}/sessions/api/session-active"

W, H = 1280, 720

# Couleurs BGR
NOIR         = (13,  17,  23)
SURFACE      = (22,  27,  34)
SURFACE2     = (33,  38,  45)
BORDURE      = (48,  54,  61)
ORANGE       = (26,  83, 232)
ORANGE_SOFT  = (15,  40, 100)
VERT         = (88, 157,  15)
VERT_SOFT    = (18,  50,   7)
VERT_CLAIR   = (52, 168,  83)
ROUGE        = (74,  45, 163)
ROUGE_SOFT   = (19,  10,  50)
ROUGE_CLAIR  = (74,  75, 226)
AMBRE        = (23, 117, 186)
AMBRE_SOFT   = ( 8,  15,  50)
AMBRE_CLAIR  = (39, 159, 239)
BLANC        = (255,255,255)
GRIS         = (139,148,158)
GRIS_FONCE   = ( 48, 54,  61)

FONT      = cv2.FONT_HERSHEY_SIMPLEX
FONT_BOLD = cv2.FONT_HERSHEY_DUPLEX

etat = {
    'mode': 'attente',
    'personne': '',
    'statut': '',
    'erreur': '',
    'temps_debut': 0,
    'rfid_en_attente': None,
    'frame_camera': None,
}


def txt(img, texte, x, y, taille, couleur, font=FONT_BOLD, ep=2):
    cv2.putText(img, texte, (x, y), font, taille, couleur, ep, cv2.LINE_AA)


def txt_centre(img, texte, y, taille, couleur, font=FONT_BOLD, ep=2):
    (w, _), _ = cv2.getTextSize(texte, font, taille, ep)
    x = (W - w) // 2
    cv2.putText(img, texte, (x, y), font, taille, couleur, ep, cv2.LINE_AA)


def barre_top(img, session=None):
    cv2.rectangle(img, (0, 0), (W, 65), SURFACE, -1)
    cv2.line(img, (0, 65), (W, 65), ORANGE, 2)

    heure = datetime.now().strftime('%H:%M:%S')
    txt(img, heure, 24, 44, 1.1, ORANGE, ep=2)

    titre = "SYSTEME DE GESTION DE PRESENCE"
    (tw, _), _ = cv2.getTextSize(titre, FONT, 0.55, 1)
    txt(img, titre, (W - tw) // 2, 42, 0.55, (180, 190, 200), FONT, 1)

    date = datetime.now().strftime('%A %d %B %Y').capitalize()
    (dw, _), _ = cv2.getTextSize(date, FONT, 0.55, 1)
    txt(img, date, W - dw - 24, 42, 0.55, GRIS, FONT, 1)

    if session:
        cv2.rectangle(img, (0, 65), (W, 110), (15, 26, 46), -1)
        cv2.line(img, (0, 110), (W, 110), GRIS_FONCE, 1)

        # Point animé
        t = time.time()
        r = int(5 + 2 * abs(np.sin(t * 3)))
        cv2.circle(img, (20, 87), r, ORANGE, -1)

        nom = session.get('nom', '').encode('ascii', 'replace').decode('ascii').replace('?', '-')
        txt(img, nom, 36, 92, 0.75, ORANGE, ep=2)

        debut = session.get('heure_debut', '')[:16].replace('T', ' ')
        fin   = session.get('heure_fin', '')[:16].replace('T', ' ')
        lieu  = session.get('lieu', '') or 'N/A'
        info  = f"{debut} -> {fin}   Salle: {lieu}"
        (iw, _), _ = cv2.getTextSize(info, FONT, 0.5, 1)
        txt(img, info, W - iw - 24, 92, 0.5, GRIS, FONT, 1)


def barre_bas(img):
    cv2.rectangle(img, (0, H - 30), (W, H), SURFACE, -1)
    cv2.line(img, (0, H - 30), (W, H - 30), GRIS_FONCE, 1)
    txt_centre(img, "Systeme de Gestion de Presence", H - 10, 0.4, GRIS_FONCE, FONT, 1)

def cercles_pulse(img, cx, cy, couleur, t):
    for i, (r, alpha) in enumerate([(90, 0.08), (72, 0.15), (56, 0.25)]):
        pulse = int(r + 4 * abs(np.sin(t * 2 + i)))
        overlay = img.copy()
        cv2.circle(overlay, (cx, cy), pulse, couleur, 1)
        cv2.addWeighted(overlay, alpha * 3, img, 1 - alpha * 3, 0, img)
    cv2.circle(img, (cx, cy), 46, couleur, -1)


def coins_cadre(img, x1, y1, x2, y2, couleur, long=28, ep=3):
    for px, py, dx, dy in [(x1,y1,1,1),(x2,y1,-1,1),(x1,y2,1,-1),(x2,y2,-1,-1)]:
        cv2.line(img, (px, py), (px + dx*long, py), couleur, ep, cv2.LINE_AA)
        cv2.line(img, (px, py), (px, py + dy*long), couleur, ep, cv2.LINE_AA)


def ecran_attente():
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:] = NOIR
    barre_top(img)

    cx, cy = W // 2, H // 2 + 10
    t = time.time()
    pulse = int(60 + 6 * abs(np.sin(t * 1.2)))
    cv2.circle(img, (cx, cy - 30), pulse, GRIS_FONCE, 1)
    cv2.circle(img, (cx, cy - 30), 44, SURFACE2, -1)
    cv2.circle(img, (cx, cy - 30), 44, GRIS_FONCE, 1)

    # Lune
    for dx, dy, r in [(0, 0, 18), (-6, -4, 12)]:
        cv2.circle(img, (cx + dx, cy - 30 + dy), r,
                   GRIS_FONCE if dx == -6 else GRIS, -1)

    txt_centre(img, "Aucune session en cours", cy + 48, 0.85, GRIS)
    txt_centre(img, "Le systeme est en veille", cy + 82, 0.5, GRIS_FONCE, FONT, 1)
    barre_bas(img)
    return img


def ecran_scan_rfid(session):
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:] = NOIR
    barre_top(img, session)

    cx = W // 2
    cy = 420 if session else H // 2

    t = time.time()
    cercles_pulse(img, cx, cy - 20, ORANGE, t)

    # Icône carte
    cw, ch = 32, 22
    cv2.rectangle(img, (cx-cw, cy-20-ch//2), (cx+cw, cy-20+ch//2), BLANC, -1)
    cv2.rectangle(img, (cx-cw+4, cy-20-4), (cx+cw-4, cy-20+4), ORANGE, -1)

    txt_centre(img, "APPROCHEZ VOTRE CARTE", cy + 44, 1.0, BLANC)
    txt_centre(img, "Placez la carte sur le lecteur RFID", cy + 80, 0.55, GRIS, FONT, 1)
    barre_bas(img)
    return img


def ecran_camera(frame, session=None):
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:] = (7, 10, 15)
    barre_top(img, session)

    top = 110 if session else 65

    if frame is not None:
        h_cam, w_cam = frame.shape[:2]
        zone_h = H - top - 60
        ratio = min(zone_h / h_cam, (W * 0.6) / w_cam)
        new_h, new_w = int(h_cam * ratio), int(w_cam * ratio)
        frame_r = cv2.resize(frame, (new_w, new_h))
        x_off = (W - new_w) // 2
        y_off = top + (zone_h - new_h) // 2
        img[y_off:y_off+new_h, x_off:x_off+new_w] = frame_r

        cx_f = x_off + new_w // 2
        cy_f = y_off + new_h // 2
        rw, rh = int(new_w * 0.28), int(new_h * 0.55)
        cv2.rectangle(img, (cx_f-rw, cy_f-rh), (cx_f+rw, cy_f+rh), ORANGE, 2)
        coins_cadre(img, cx_f-rw, cy_f-rh, cx_f+rw, cy_f+rh, ORANGE)

    cv2.rectangle(img, (0, H-60), (W, H-30), (10, 14, 20), -1)
    txt_centre(img, "REGARDEZ LA CAMERA", H - 46, 0.85, ORANGE)
    txt_centre(img, "Centrez votre visage dans le cadre orange", H - 18, 0.5, GRIS, FONT, 1)
    return img


def ecran_traitement(session=None):
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:] = NOIR
    barre_top(img, session)

    cx, cy = W // 2, H // 2 + 10
    t = time.time()

    # Spinner
    n = 10
    for i in range(n):
        angle = (i / n) * 2 * np.pi + t * 3
        r = 52
        x = int(cx + r * np.cos(angle))
        y = int(cy - 20 + r * np.sin(angle))
        alpha = (i + 1) / n
        c = tuple(int(v * alpha) for v in ORANGE)
        cv2.circle(img, (x, y), int(5 + 3 * alpha), c, -1)

    cv2.circle(img, (cx, cy - 20), 32, SURFACE2, -1)
    cv2.circle(img, (cx, cy - 20), 32, GRIS_FONCE, 1)

    txt_centre(img, "VERIFICATION EN COURS", cy + 52, 0.9, BLANC)
    txt_centre(img, "Analyse du visage en cours...", cy + 86, 0.5, GRIS, FONT, 1)
    barre_bas(img)
    return img


def ecran_succes(personne, statut):
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:] = NOIR
    cv2.rectangle(img, (0, 0), (W, H), VERT_SOFT, -1)
    barre_top(img)

    cx, cy = W // 2, H // 2

    cv2.circle(img, (cx, cy - 50), 70, VERT, -1)
    cv2.circle(img, (cx, cy - 50), 74, VERT_CLAIR, 2)

    # Check
    pts = np.array([
        [cx - 36, cy - 50],
        [cx - 12, cy - 22],
        [cx + 42, cy - 90]
    ], np.int32)
    cv2.polylines(img, [pts], False, BLANC, 7, cv2.LINE_AA)

    txt_centre(img, "PRESENCE VALIDEE", cy + 44, 1.1, VERT_CLAIR)

    nom = personne.upper()
    txt_centre(img, nom, cy + 88, 0.9, BLANC)

    label = "PRESENT" if statut == 'present' else "RETARD"
    couleur_label = VERT_CLAIR if statut == 'present' else AMBRE_CLAIR
    (lw, _), _ = cv2.getTextSize(label, FONT_BOLD, 0.65, 2)
    lx = (W - lw - 32) // 2
    cv2.rectangle(img, (lx - 4, cy + 104), (lx + lw + 36, cy + 130),
                  VERT if statut == 'present' else AMBRE, -1)
    txt(img, label, lx + 12, cy + 124, 0.65, BLANC, ep=2)

    barre_bas(img)
    return img


def ecran_echec(message):
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:] = NOIR
    cv2.rectangle(img, (0, 0), (W, H), ROUGE_SOFT, -1)
    barre_top(img)

    cx, cy = W // 2, H // 2

    cv2.circle(img, (cx, cy - 50), 70, ROUGE, -1)
    cv2.circle(img, (cx, cy - 50), 74, ROUGE_CLAIR, 2)

    cv2.line(img, (cx-38, cy-92), (cx+38, cy-8), BLANC, 7, cv2.LINE_AA)
    cv2.line(img, (cx+38, cy-92), (cx-38, cy-8), BLANC, 7, cv2.LINE_AA)

    if 'visage' in message.lower():
        txt_centre(img, "VISAGE NON DETECTE", cy + 44, 1.1, ROUGE_CLAIR)
        txt_centre(img, "Regardez directement la camera", cy + 84, 0.65, GRIS, FONT, 1)
        txt_centre(img, "Restez face a la camera", cy + 114, 0.5, GRIS_FONCE, FONT, 1)
    else:
        txt_centre(img, "ACCES REFUSE", cy + 44, 1.1, ROUGE_CLAIR)
        msg = message[:55]
        txt_centre(img, msg, cy + 84, 0.6, GRIS, FONT, 1)
        txt_centre(img, "Veuillez reessayer ou contacter un responsable",
                   cy + 114, 0.5, GRIS_FONCE, FONT, 1)

    barre_bas(img)
    return img


def ecran_deja_pointe(personne):
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:] = NOIR
    cv2.rectangle(img, (0, 0), (W, H), AMBRE_SOFT, -1)
    barre_top(img)

    cx, cy = W // 2, H // 2

    cv2.circle(img, (cx, cy - 50), 70, AMBRE, -1)
    cv2.circle(img, (cx, cy - 50), 74, AMBRE_CLAIR, 2)

    cv2.rectangle(img, (cx - 8, cy - 92), (cx + 8, cy - 28), BLANC, -1)
    cv2.circle(img, (cx, cy - 16), 8, BLANC, -1)

    txt_centre(img, "DEJA ENREGISTRE", cy + 44, 1.1, AMBRE_CLAIR)
    txt_centre(img, personne.upper(), cy + 88, 0.9, BLANC)
    txt_centre(img, "Presence deja enregistree pour cette session",
               cy + 122, 0.55, GRIS, FONT, 1)

    barre_bas(img)
    return img


def thread_rfid():
    while True:
        if etat['mode'] == 'scan_rfid':
            numero = input()
            if numero.strip():
                etat['rfid_en_attente'] = numero.strip().upper()
        time.sleep(0.1)


def get_session_en_cours():
    try:
        r = requests.get(f"{SERVEUR_URL}/sessions/api/session-active", timeout=3)
        return r.json().get('session')
    except:
        return None


def faire_pointage(numero_rfid):
    t0 = time.time()
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return {'succes': False, 'message': 'Camera non disponible'}

    t_cam = time.time()
    frame_finale = None
    while time.time() - t_cam < 1.5:
        ret, frame = cap.read()
        if ret:
            etat['frame_camera'] = frame
            frame_finale = frame
        time.sleep(0.03)

    cap.release()
    etat['frame_camera'] = None

    if frame_finale is None:
        return {'succes': False, 'message': 'Erreur capture photo'}

    _, buf = cv2.imencode('.jpg', frame_finale, [cv2.IMWRITE_JPEG_QUALITY, 95])
    photo_b64 = base64.b64encode(buf).decode('utf-8')

    etat['mode'] = 'traitement'
    try:
        r = requests.post(API_POINTAGE,
                          json={'numero_rfid': numero_rfid, 'photo': photo_b64},
                          timeout=25)
        data = r.json()
        print(f"[TEMPS] {time.time() - t0:.2f}s")
        return data
    except Exception as e:
        return {'succes': False, 'message': f'Erreur serveur: {str(e)}'}


def main():
    print(f"=== Ecran de Pointage ===")
    print(f"Serveur : {SERVEUR_URL}")

    threading.Thread(target=thread_rfid, daemon=True).start()

    cv2.namedWindow("Pointage", cv2.WINDOW_NORMAL)
    img_init = np.zeros((H, W, 3), dtype=np.uint8)
    cv2.imshow("Pointage", img_init)
    cv2.resizeWindow("Pointage", W, H)

    session_actuelle = None
    t_check = 0

    while True:
        now = time.time()

        if now - t_check > 10:
            t_check = now
            session_actuelle = get_session_en_cours()
            if session_actuelle:
                if etat['mode'] == 'attente':
                    etat['mode'] = 'scan_rfid'
            else:
                if etat['mode'] in ['attente', 'scan_rfid']:
                    etat['mode'] = 'attente'

        mode = etat['mode']

        if mode == 'attente':
            img = ecran_attente()

        elif mode == 'scan_rfid':
            img = ecran_scan_rfid(session_actuelle)

            if etat['rfid_en_attente']:
                rfid = etat['rfid_en_attente']
                etat['rfid_en_attente'] = None
                etat['mode'] = 'verif_rfid'

                def process(numero=rfid):
                    try:
                        # Vérifier carte sans caméra
                        r = requests.post(API_VERIFIER,
                                        json={'numero_rfid': numero},
                                        timeout=5)
                        d = r.json()

                        if d.get('statut') == 'deja_pointe':
                            etat['personne'] = d.get('personne', '')
                            etat['mode'] = 'deja_pointe'
                            etat['temps_debut'] = time.time()
                            return

                        if not d.get('succes'):
                            etat['erreur'] = d.get('message', 'Erreur')
                            etat['mode'] = 'echec'
                            etat['temps_debut'] = time.time()
                            return

                        # Carte OK → caméra + DeepFace
                        # Essayer jusqu'à 3 fois si pas de visage
                        max_essais = 3
                        for essai in range(max_essais):
                            etat['mode'] = 'camera'
                            data = faire_pointage(numero)

                            if data.get('statut') == 'pas_de_visage':
                                etat['erreur'] = 'Aucun visage detecte\nRegardez la camera'
                                etat['mode'] = 'echec'
                                etat['temps_debut'] = time.time()
                                time.sleep(2)
                                continue  # Réessayer

                            if data.get('succes'):
                                etat['personne'] = data.get('personne', '')
                                etat['statut'] = data.get('statut', '')
                                etat['mode'] = 'resultat'
                            else:
                                etat['erreur'] = data.get('message', 'Erreur')
                                etat['mode'] = 'echec'

                            etat['temps_debut'] = time.time()
                            return

                        # Après 3 essais échoués
                        etat['erreur'] = 'Visage non detecte apres 3 essais'
                        etat['mode'] = 'echec'
                        etat['temps_debut'] = time.time()

                    except Exception as e:
                        print(f"[ERR] {e}")
                        etat['erreur'] = str(e)
                        etat['mode'] = 'echec'
                        etat['temps_debut'] = time.time()

        elif mode == 'verif_rfid':
            img = ecran_traitement(session_actuelle)

        elif mode == 'camera':
            img = ecran_camera(etat.get('frame_camera'), session_actuelle)

        elif mode == 'traitement':
            img = ecran_traitement(session_actuelle)

        elif mode == 'resultat':
            img = ecran_succes(etat['personne'], etat['statut'])
            if now - etat['temps_debut'] > 2.0:
                etat['mode'] = 'scan_rfid'

        elif mode == 'echec':
            img = ecran_echec(etat['erreur'])
            if now - etat['temps_debut'] > 3.0:
                etat['mode'] = 'scan_rfid'

        elif mode == 'deja_pointe':
            img = ecran_deja_pointe(etat['personne'])
            if now - etat['temps_debut'] > 2.0:
                etat['mode'] = 'scan_rfid'

        else:
            img = ecran_attente()

        cv2.imshow("Pointage", img)
        key = cv2.waitKey(30) & 0xFF
        if key == ord('q') or key == 27:
            break

    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()