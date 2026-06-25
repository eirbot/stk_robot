#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import cv2
import numpy as np
import zmq
import json
import time
import math
import threading
import sys

# ==============================================================================
# --- CONFIGURATION ET CONSTANTES GÉOMÉTRIQUES ---
# ==============================================================================

# Dimensions de la table Eurobot (en mm)
LARGEUR_TABLE_X = 3000.0
HAUTEUR_TABLE_Y = 2000.0

# Hauteur de la caméra zénithale et coordonnées de son centre de projection (en mm)
HAUTEUR_CAMERA = 2500.0
CENTRE_CAM_X = 1500.0
CENTRE_CAM_Y = 1000.0

# Hauteur du tag ArUco fixé sur le robot (en mm)
HAUTEUR_TAG_ROBOT = 300.0

# Position absolue de départ théorique du robot (pour le recalage d'offset)
DEPART_ABS_X = 200.0
DEPART_ABS_Y = 200.0

# ID des tags ArUco utilisés pour le vinyle de la table et coordonnées réelles associées (en mm)
TAGS_VINYLE_COORDS = {
    10: (1000.0, 1500.0), # Haut-Gauche
    11: (2000.0, 1500.0), # Haut-Droite
    12: (2000.0, 500.0),  # Bas-Droite
    13: (1000.0, 500.0)   # Bas-Gauche
}

# ID du tag ArUco posé sur le robot
TAG_ID_ROBOT = 47

# Paramètres de calibration intrinsèque de la caméra (ex: capteur 4K)
# Ces valeurs doivent être ajustées après calibration réelle de la lentille
MATRICE_CAMERA = np.array([
    [3000.0, 0.0, 1920.0],
    [0.0, 3000.0, 1080.0],
    [0.0, 0.0, 1.0]
], dtype=np.float32)

COEFFS_DISTORSION = np.array([-0.1, 0.05, 0.0, 0.0, -0.01], dtype=np.float32)

# ==============================================================================
# --- ETAT GLOBAL & SHUTDOWN SIGNALS ---
# ==============================================================================
do_calibration = False
offset_x = 0.0
offset_y = 0.0
derniere_homographie = None

# ==============================================================================
# --- THREAD D'ÉCOUTE ZEROMQ (SUB) ---
# ==============================================================================
def ecoute_ordres_zmq():
    global do_calibration
    context = zmq.Context()
    sub_socket = context.socket(zmq.SUB)
    
    # Connexion au canal d'ordres descendants du serveur Go
    sub_socket.connect("tcp://localhost:5556")
    sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    print("[ZMQ SUB] Connecté au port 5556, en attente d'ordres...")
    
    while True:
        try:
            # Réception du message
            msg = sub_socket.recv_string()
            paquet = json.loads(msg)
            
            # Intercepter l'action de calibration
            if paquet.get("type") == "action" and paquet.get("payload") == "calibrate_vision":
                print("[ZMQ SUB] 🎯 Ordre 'calibrate_vision' reçu ! Flag de calibration levé.")
                do_calibration = True
        except Exception as e:
            print(f"[ZMQ SUB] Erreur réception : {e}")
            time.sleep(0.1)

# Lancement du thread d'écoute en tâche de fond (daemon)
thread_zmq = threading.Thread(target=ecoute_ordres_zmq, daemon=True)
thread_zmq.start()

# ==============================================================================
# --- PIPELINE DE TRAITEMENT D'IMAGE & COMPOSITIONS MATHÉMATIQUES ---
# ==============================================================================
def corriger_parallaxe(x_brut, y_brut, h_tag, h_cam, x_cam, y_cam):
    """
    Applique le théorème de Thalès pour corriger l'effet de parallaxe induit
    par la hauteur du tag (h_tag) par rapport au sol (Z=0).
    """
    ratio = 1.0 - (h_tag / h_cam)
    x_corrige = x_cam + (x_brut - x_cam) * ratio
    y_corrige = y_cam + (y_brut - y_cam) * ratio
    return x_corrige, y_corrige

def calculer_homographie(corners, ids):
    """
    Calcule la matrice d'homographie à partir des 4 tags ArUco détectés sur le vinyle.
    Associe les coordonnées image des tags à leurs vraies coordonnées physiques.
    """
    pts_image = []
    pts_physiques = []
    
    # Mapper les tags détectés
    detectes = {}
    for i, tag_id in enumerate(ids.flatten()):
        if tag_id in TAGS_VINYLE_COORDS:
            # Calcul du centre du tag avec précision sous-pixellique
            coin = corners[i][0]
            centre = np.mean(coin, axis=0)
            detectes[tag_id] = (centre[0], centre[1])
            
    # S'assurer que les 4 tags du vinyle sont détectés pour mettre à jour la matrice
    if len(detectes) == 4:
        for tag_id, coord_physique in TAGS_VINYLE_COORDS.items():
            pts_image.append(detectes[tag_id])
            pts_physiques.append(coord_physique)
            
        pts_image = np.array(pts_image, dtype=np.float32)
        pts_physiques = np.array(pts_physiques, dtype=np.float32)
        
        # Calcul de la matrice d'homographie de perspective
        H, _ = cv2.findHomography(pts_image, pts_physiques)
        return H
    return None

# ==============================================================================
# --- SOURCE VIDÉO : COMPATIBILITÉ RÉELLE / SIMULATION ---
# ==============================================================================
# Tente d'ouvrir la caméra physique index 0
cap = cv2.VideoCapture(0)
simuler_flux = False

if not cap.isOpened():
    print("[CAM] ⚠️ Impossible d'ouvrir la caméra physique. Passage en mode SIMULATION de flux.")
    simuler_flux = True
else:
    # Essaye de configurer en haute résolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 3840)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 2160)
    print("[CAM] ✅ Caméra physique connectée en 4K.")

# Initialisation du détecteur ArUco OpenCV
dictionnaire_aruco = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
parametres_detecteur = cv2.aruco.DetectorParameters()
detecteur_aruco = cv2.aruco.ArucoDetector(dictionnaire_aruco, parametres_detecteur)

# Connexion ZeroMQ PUSH pour publier la télémétrie recalculée vers le serveur Go
zmq_context = zmq.Context()
push_socket = zmq_context.socket(zmq.PUSH)
push_socket.connect("tcp://localhost:5555")

# Variable pour simuler la trajectoire du robot si le flux est simulé
t_simu = 0.0

print("[MAIN] Pipeline de vision zénithale prêt et connecté.")

while True:
    frame = None
    
    # 1. Capture ou génération de la frame
    if simuler_flux:
        # Création d'une frame 4K noire pour la simulation
        frame = np.zeros((2160, 3840, 3), dtype=np.uint8)
        
        # Simuler un léger tremblement ou position des tags de la table sur l'image
        # Correspondance approximative Image <-> Monde pour les 4 coins
        # Tags de la table : (1000, 1500), (2000, 1500), (2000, 500), (1000, 500)
        # On dessine les marqueurs sur l'image simulée
        pts_img_simu = {
            10: (1200, 480),   # Haut-Gauche
            11: (2640, 480),   # Haut-Droite
            12: (2640, 1680),  # Bas-Droite
            13: (1200, 1680)   # Bas-Gauche
        }
        
        # Dessiner les tags vinyles de la table
        for tag_id, pt in pts_img_simu.items():
            # Créer l'image du marqueur
            try:
                marker_img = cv2.aruco.generateImageMarker(dictionnaire_aruco, tag_id, 100)
            except AttributeError:
                marker_img = cv2.aruco.drawMarker(dictionnaire_aruco, tag_id, 100)
                
            marker_bgr = cv2.cvtColor(marker_img, cv2.COLOR_GRAY2BGR)
            x, y = pt
            frame[y-50:y+50, x-50:x+50] = marker_bgr
            
        # Simuler le déplacement du robot
        # Le robot démarre physiquement à (200, 200)
        sim_x_phys = 200.0 + 80.0 * math.sin(t_simu)
        sim_y_phys = 200.0 + 50.0 * math.cos(t_simu)
        sim_theta_phys = -t_simu
        t_simu += 0.05
        
        # Conversion physique -> image simulée (approximation inverse)
        # On calcule les coordonnées de l'image de manière inverse pour tester les calculs
        # x_img = (x_phys - 1000) * 1.44 + 1200
        # y_img = (1500 - y_phys) * 1.2 + 480
        x_img = int((sim_x_phys - 1000.0) * 1.44 + 1200.0)
        y_img = int((1500.0 - sim_y_phys) * 1.2 + 480.0)
        
        # On dessine le tag du robot
        try:
            robot_marker_img = cv2.aruco.generateImageMarker(dictionnaire_aruco, TAG_ID_ROBOT, 80)
        except AttributeError:
            robot_marker_img = cv2.aruco.drawMarker(dictionnaire_aruco, TAG_ID_ROBOT, 80)
            
        # Rotation du tag pour simuler le cap
        M_rot = cv2.getRotationMatrix2D((40, 40), sim_theta_phys * 180.0 / math.pi, 1.0)
        robot_marker_rot = cv2.warpAffine(robot_marker_img, M_rot, (80, 80), borderValue=0)
        robot_bgr = cv2.cvtColor(robot_marker_rot, cv2.COLOR_GRAY2BGR)
        
        # Insérer sur la frame
        if 40 <= x_img < 3800 and 40 <= y_img < 2120:
            frame[y_img-40:y_img+40, x_img-40:x_img+40] = robot_bgr
            
        time.sleep(0.05) # Limiter le CPU en simu
    else:
        ret, frame = cap.read()
        if not ret:
            print("[CAM] Échec de la lecture de la frame réelle.")
            time.sleep(0.1)
            continue

    # a. Correction de la distorsion de la lentille
    image_corrigee = cv2.undistort(frame, MATRICE_CAMERA, COEFFS_DISTORSION)

    # b. Détection des tags ArUco
    coins, ids, rejetes = detecteur_aruco.detectMarkers(image_corrigee)

    if ids is not None and len(ids) > 0:
        # Tenter de calculer / mettre à jour l'homographie plane
        H_nouveau = calculer_homographie(coins, ids)
        if H_nouveau is not None:
            derniere_homographie = H_nouveau
            
        # Si nous avons une matrice d'homographie valide
        if derniere_homographie is not None:
            # Chercher le tag du robot dans les détections
            robot_idx = -1
            for i, tag_id in enumerate(ids.flatten()):
                if tag_id == TAG_ID_ROBOT:
                    robot_idx = i
                    break
                    
            if robot_idx != -1:
                # Récupération des coins du tag du robot
                coins_robot = coins[robot_idx][0]
                centre_image = np.mean(coins_robot, axis=0)
                
                # Calcul de l'orientation du robot dans l'image (vecteur avant du tag)
                devant_image = np.mean(coins_robot[0:2], axis=0) # Milieu des coins supérieurs (0 et 1)
                
                # c. Application de l'homographie sur le centre et le nez du robot
                points_projeter = np.array([[centre_image], [devant_image]], dtype=np.float32)
                points_monde_brut = cv2.perspectiveTransform(points_projeter, derniere_homographie)
                
                x_brut, y_brut = points_monde_brut[0][0]
                x_devant_brut, y_devant_brut = points_monde_brut[1][0]
                
                # d. Correction de parallaxe (Thalès) pour ramener le tag à Z=0
                x_parallaxe, y_parallaxe = corriger_parallaxe(
                    x_brut, y_brut, HAUTEUR_TAG_ROBOT, HAUTEUR_CAMERA, CENTRE_CAM_X, CENTRE_CAM_Y
                )
                x_devant_parallaxe, y_devant_parallaxe = corriger_parallaxe(
                    x_devant_brut, y_devant_brut, HAUTEUR_TAG_ROBOT, HAUTEUR_CAMERA, CENTRE_CAM_X, CENTRE_CAM_Y
                )
                
                # Calcul du cap (orientation theta) après correction
                dx = x_devant_parallaxe - x_parallaxe
                dy = y_devant_parallaxe - y_parallaxe
                theta = math.atan2(dy, dx)
                
                # e. Calibration dynamique (offset)
                if do_calibration:
                    offset_x = DEPART_ABS_X - x_parallaxe
                    offset_y = DEPART_ABS_Y - y_parallaxe
                    do_calibration = False
                    print(f"[VISION WORKER] 🎯 Calibration réussie ! Nouveaux offsets calculés : DX = {offset_x:.2f} mm, DY = {offset_y:.2f} mm")
                    
                # f. Application des offsets
                x_final = x_parallaxe + offset_x
                y_final = y_parallaxe + offset_y
                
                # g. Envoi des coordonnées finales via ZMQ PUSH (format state_update)
                message_telemetrie = {
                    "type": "state_update",
                    "data": {
                        "x": float(x_final),
                        "y": float(y_final),
                        "theta": float(theta)
                    }
                }
                
                try:
                    push_socket.send_json(message_telemetrie, flags=zmq.NOBLOCK)
                    # Afficher périodiquement
                    if simuler_flux and int(time.time() * 10) % 20 == 0:
                        print(f"[VISION WORKER] Robot détecté -> Final X: {x_final:.1f} mm, Y: {y_final:.1f} mm, θ: {math.degrees(theta):.1f}° (offsets: {offset_x:.1f}, {offset_y:.1f})")
                except zmq.Again:
                    pass
                except Exception as e:
                    print(f"[VISION WORKER] Erreur lors de l'envoi de la position : {e}")
            else:
                # Le tag du robot n'est pas vu
                pass
        else:
            # L'homographie n'est pas encore initialisée (aucun set complet de 4 tags détecté au moins une fois)
            if int(time.time() * 10) % 50 == 0:
                print("[VISION WORKER] ⚠️ En attente de détection des 4 tags vinyles pour l'homographie...")
    else:
        # Aucun tag détecté
        pass

# Nettoyage en cas de sortie
cap.release()
