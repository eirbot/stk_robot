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
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

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
# --- BUFFER DE STREAMING ET SERVEUR HTTP MJPEG (PORT 8082) ---
# ==============================================================================
CAMERA_PRESETS = {
    "4K": {"width": 3840, "height": 2160, "fps": 30, "label": "4K @ 30fps"},
    "1080P": {"width": 1920, "height": 1080, "fps": 60, "label": "1080p @ 60fps"},
    "2K": {"width": 2560, "height": 1440, "fps": 30, "label": "2K @ 30fps"}
}

class StreamFrameBuffer:
    def __init__(self):
        self.lock = threading.Lock()
        self.raw_jpeg = None
        self.annotated_jpeg = None
        self.show_aruco_default = True
        self.current_preset = "4K"
        self.preset_label = "4K @ 30fps"
        self.pending_preset = None
        self.fps = 0.0
        self.status_data = {
            "connected": True,
            "simulated": False,
            "homography_ready": False,
            "robot_detected": False,
            "robot_x": 0.0,
            "robot_y": 0.0,
            "robot_theta_deg": 0.0,
            "offset_x": 0.0,
            "offset_y": 0.0,
            "detected_ids": [],
            "resolution": "4K",
            "resolution_label": "4K @ 30fps",
            "width": 3840,
            "height": 2160
        }

    def update(self, raw_frame, annotated_frame, fps, status):
        def encode_frame(img):
            if img is None:
                return None
            h, w = img.shape[:2]
            target_w = 1920  # Résolution Full HD optimale pour affichage plein écran net et fluide
            if w > target_w:
                ratio = target_w / float(w)
                dim = (target_w, int(h * ratio))
                send_img = cv2.resize(img, dim, interpolation=cv2.INTER_AREA)
            else:
                send_img = img
            ret, buf = cv2.imencode('.jpg', send_img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            return buf.tobytes() if ret else None

        raw_bytes = encode_frame(raw_frame)
        annotated_bytes = encode_frame(annotated_frame)

        with self.lock:
            self.raw_jpeg = raw_bytes
            self.annotated_jpeg = annotated_bytes
            self.fps = fps
            self.status_data.update(status)

    def get_frame(self, force_aruco=None):
        with self.lock:
            use_aruco = force_aruco if force_aruco is not None else self.show_aruco_default
            if use_aruco:
                return self.annotated_jpeg or self.raw_jpeg
            return self.raw_jpeg or self.annotated_jpeg

    def toggle_aruco(self, state=None):
        with self.lock:
            if state is not None:
                self.show_aruco_default = bool(state)
            else:
                self.show_aruco_default = not self.show_aruco_default
            return self.show_aruco_default

    def request_preset(self, preset=None):
        with self.lock:
            if preset:
                p = preset.upper()
                if p in CAMERA_PRESETS:
                    self.pending_preset = p
            else:
                # Bascule principale entre 4K et 1080p (60fps)
                if self.current_preset == "4K":
                    self.pending_preset = "1080P"
                else:
                    self.pending_preset = "4K"
            return self.pending_preset or self.current_preset

    def get_pending_preset(self):
        with self.lock:
            p = self.pending_preset
            self.pending_preset = None
            return p

    def set_active_preset(self, preset_key, label, w, h):
        with self.lock:
            self.current_preset = preset_key
            self.preset_label = label
            self.status_data["resolution"] = preset_key
            self.status_data["resolution_label"] = label
            self.status_data["width"] = w
            self.status_data["height"] = h

    def get_status_json(self):
        with self.lock:
            data = dict(self.status_data)
            data["fps"] = round(self.fps, 1)
            data["show_aruco"] = self.show_aruco_default
            data["resolution"] = self.current_preset
            data["resolution_label"] = self.preset_label
            return data

frame_buffer = StreamFrameBuffer()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

class VisionMJPEGHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Désactiver les logs verbeux de chaque frame dans la console

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        def set_cors():
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', '*')

        if path in ('/stream', '/stream_aruco', '/stream_raw'):
            self.send_response(200)
            self.send_header('Age', '0')
            self.send_header('Cache-Control', 'no-cache, private, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            set_cors()
            self.end_headers()

            force_aruco = None
            if path == '/stream_aruco':
                force_aruco = True
            elif path == '/stream_raw':
                force_aruco = False
            elif 'aruco' in query:
                val = query['aruco'][0].lower()
                force_aruco = (val in ('1', 'true', 'yes', 'on'))

            try:
                last_time = 0
                while True:
                    now = time.time()
                    if now - last_time < 0.033:  # Max 30 FPS pour préserver la bande passante
                        time.sleep(0.005)
                        continue

                    jpeg_bytes = frame_buffer.get_frame(force_aruco)
                    if jpeg_bytes:
                        self.wfile.write(b'--frame\r\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', str(len(jpeg_bytes)))
                        self.end_headers()
                        self.wfile.write(jpeg_bytes)
                        self.wfile.write(b'\r\n')
                        last_time = now
                    else:
                        time.sleep(0.05)
            except Exception:
                pass  # Client déconnecté

        elif path == '/api/toggle_aruco':
            state_val = None
            if 'state' in query:
                state_val = query['state'][0].lower() in ('1', 'true', 'yes', 'on')
            current = frame_buffer.toggle_aruco(state_val)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            set_cors()
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "show_aruco": current}).encode())

        elif path in ('/api/toggle_resolution', '/api/toggle_mode'):
            mode = query.get('mode', [None])[0]
            new_preset = frame_buffer.request_preset(mode)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            set_cors()
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "requested": new_preset,
                "current": frame_buffer.current_preset,
                "label": frame_buffer.preset_label
            }).encode())

        elif path == '/api/set_resolution':
            mode = query.get('mode', ['4K'])[0]
            new_preset = frame_buffer.request_preset(mode)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            set_cors()
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "requested": new_preset
            }).encode())

        elif path == '/api/status':
            status = frame_buffer.get_status_json()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            set_cors()
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())

        else:
            self.send_response(404)
            set_cors()
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

def start_mjpeg_server(port=8082):
    server = ThreadedHTTPServer(('0.0.0.0', port), VisionMJPEGHandler)
    print(f"[STREAM] Serveur vidéo USB démarré sur http://0.0.0.0:{port}/stream")
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    return server

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

# Lancement du serveur vidéo HTTP MJPEG (port 8082)
mjpeg_server = start_mjpeg_server(port=8082)

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
    
    detectes = {}
    for i, tag_id in enumerate(ids.flatten()):
        if tag_id in TAGS_VINYLE_COORDS:
            coin = corners[i][0]
            centre = np.mean(coin, axis=0)
            detectes[tag_id] = (centre[0], centre[1])
            
    if len(detectes) == 4:
        for tag_id, coord_physique in TAGS_VINYLE_COORDS.items():
            pts_image.append(detectes[tag_id])
            pts_physiques.append(coord_physique)
            
        pts_image = np.array(pts_image, dtype=np.float32)
        pts_physiques = np.array(pts_physiques, dtype=np.float32)
        
        H, _ = cv2.findHomography(pts_image, pts_physiques)
        return H
    return None

def apply_camera_preset(cap, preset_key, cur_w, cur_h, simuler=False):
    global MATRICE_CAMERA, derniere_homographie
    key = preset_key.upper()
    if key not in CAMERA_PRESETS:
        key = "4K"
    cfg = CAMERA_PRESETS[key]
    new_w, new_h, new_fps = cfg["width"], cfg["height"], cfg["fps"]

    if not simuler and cap is not None and cap.isOpened():
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, new_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, new_h)
        cap.set(cv2.CAP_PROP_FPS, new_fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[CAM] 🔄 Résolution basculée sur {key} : {actual_w}x{actual_h} @ {new_fps}fps")
        new_w, new_h = actual_w, actual_h
    else:
        print(f"[CAM] 🔄 Résolution simulée basculée sur {key} : {new_w}x{new_h}")

    scale = new_w / 3840.0
    MATRICE_CAMERA = np.array([
        [3000.0 * scale, 0.0, new_w / 2.0],
        [0.0, 3000.0 * scale, new_h / 2.0],
        [0.0, 0.0, 1.0]
    ], dtype=np.float32)

    if derniere_homographie is not None and cur_w > 0 and cur_h > 0 and (cur_w != new_w or cur_h != new_h):
        sx = new_w / float(cur_w)
        sy = new_h / float(cur_h)
        S_inv = np.array([
            [1.0 / sx, 0.0, 0.0],
            [0.0, 1.0 / sy, 0.0],
            [0.0, 0.0, 1.0]
        ], dtype=np.float32)
        derniere_homographie = derniere_homographie @ S_inv

    return key, new_w, new_h, cfg["label"]

# ==============================================================================
# --- SOURCE VIDÉO : COMPATIBILITÉ RÉELLE / SIMULATION ---
# ==============================================================================
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
if not cap.isOpened():
    cap = cv2.VideoCapture(0)

simuler_flux = False
frame_w = 3840
frame_h = 2160
current_preset_key = "4K"

if not cap.isOpened():
    print("[CAM] ⚠️ Impossible d'ouvrir la caméra physique. Passage en mode SIMULATION de flux.")
    simuler_flux = True
else:
    # Configuration initiale 4K en MJPG matériel
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 3840)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 2160)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[CAM] ✅ Caméra physique USB connectée ({frame_w}x{frame_h} @ {int(cap.get(cv2.CAP_PROP_FPS))}fps).")

# Initialisation du détecteur ArUco OpenCV
dictionnaire_aruco = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
parametres_detecteur = cv2.aruco.DetectorParameters()
detecteur_aruco = cv2.aruco.ArucoDetector(dictionnaire_aruco, parametres_detecteur)

# Connexion ZeroMQ PUSH pour publier la télémétrie recalculée vers le serveur Go
zmq_context = zmq.Context()
push_socket = zmq_context.socket(zmq.PUSH)
push_socket.connect("tcp://localhost:5555")

t_simu = 0.0
last_fps_time = time.time()
fps_calc = 20.0

print("[MAIN] Pipeline de vision zénithale prêt et connecté.")

while True:
    t_start = time.time()

    # Vérification d'une demande de changement de résolution
    pending = frame_buffer.get_pending_preset()
    if pending:
        cur_key, cur_w, cur_h, cur_lbl = apply_camera_preset(
            cap, pending, frame_w, frame_h, simuler=simuler_flux
        )
        frame_w, frame_h = cur_w, cur_h
        current_preset_key = cur_key
        frame_buffer.set_active_preset(cur_key, cur_lbl, cur_w, cur_h)

    frame = None
    
    # 1. Capture ou génération de la frame
    if simuler_flux:
        frame = np.zeros((frame_h, frame_w, 3), dtype=np.uint8)
        scale_sim = frame_w / 3840.0
        
        pts_img_simu = {
            10: (int(1200 * scale_sim), int(480 * scale_sim)),
            11: (int(2640 * scale_sim), int(480 * scale_sim)),
            12: (int(2640 * scale_sim), int(1680 * scale_sim)),
            13: (int(1200 * scale_sim), int(1680 * scale_sim))
        }
        
        for tag_id, pt in pts_img_simu.items():
            try:
                marker_img = cv2.aruco.generateImageMarker(dictionnaire_aruco, tag_id, 100)
            except AttributeError:
                marker_img = cv2.aruco.drawMarker(dictionnaire_aruco, tag_id, 100)
                
            marker_bgr = cv2.cvtColor(marker_img, cv2.COLOR_GRAY2BGR)
            x, y = pt
            frame[y-50:y+50, x-50:x+50] = marker_bgr
            
        sim_x_phys = 200.0 + 80.0 * math.sin(t_simu)
        sim_y_phys = 200.0 + 50.0 * math.cos(t_simu)
        sim_theta_phys = -t_simu
        t_simu += 0.05
        
        x_img = int((sim_x_phys - 1000.0) * 1.44 + 1200.0)
        y_img = int((1500.0 - sim_y_phys) * 1.2 + 480.0)
        
        try:
            robot_marker_img = cv2.aruco.generateImageMarker(dictionnaire_aruco, TAG_ID_ROBOT, 80)
        except AttributeError:
            robot_marker_img = cv2.aruco.drawMarker(dictionnaire_aruco, TAG_ID_ROBOT, 80)
            
        M_rot = cv2.getRotationMatrix2D((40, 40), sim_theta_phys * 180.0 / math.pi, 1.0)
        robot_marker_rot = cv2.warpAffine(robot_marker_img, M_rot, (80, 80), borderValue=0)
        robot_bgr = cv2.cvtColor(robot_marker_rot, cv2.COLOR_GRAY2BGR)
        
        if 40 <= x_img < 3800 and 40 <= y_img < 2120:
            frame[y_img-40:y_img+40, x_img-40:x_img+40] = robot_bgr
            
        time.sleep(0.04)
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

    # Création d'une copie dédiée pour l'affichage avec overlay des détections ArUco
    image_annotee = image_corrigee.copy()

    robot_trouve = False
    x_final = 0.0
    y_final = 0.0
    theta_rad = 0.0
    detected_id_list = []

    # Facteur d'échelle adaptatif pour que l'interface soit parfaitement proportionnée en 1080p comme en 4K
    scale_ui = max(1.0, frame_w / 1920.0)

    if ids is not None and len(ids) > 0:
        detected_id_list = [int(i) for i in ids.flatten()]

        # Tracé des contours ArUco avec épaisseur adaptative
        for i, coin in enumerate(coins):
            c = coin[0].astype(int)
            cv2.polylines(image_annotee, [c], True, (0, 255, 0), thickness=max(2, int(3 * scale_ui)))
            tag_id = int(ids.flatten()[i])
            corner_pt = (c[0][0], max(int(25 * scale_ui), c[0][1] - int(10 * scale_ui)))
            cv2.putText(image_annotee, f"#{tag_id}", corner_pt, cv2.FONT_HERSHEY_SIMPLEX,
                        0.75 * scale_ui, (0, 255, 128), max(2, int(2 * scale_ui)))

        # Tenter de calculer / mettre à jour l'homographie plane
        H_nouveau = calculer_homographie(coins, ids)
        if H_nouveau is not None:
            derniere_homographie = H_nouveau

        # Dessiner des annotations spécifiques pour les tags de table
        for i, tag_id in enumerate(ids.flatten()):
            coin = coins[i][0]
            c_pt = np.mean(coin, axis=0).astype(int)
            if tag_id in TAGS_VINYLE_COORDS:
                # Point central et cercle extérieur cyan
                r_c = int(12 * scale_ui)
                cv2.circle(image_annotee, tuple(c_pt), r_c, (255, 255, 0), -1)
                cv2.circle(image_annotee, tuple(c_pt), r_c + int(4 * scale_ui), (0, 180, 255), max(1, int(2 * scale_ui)))
                cv2.putText(image_annotee, f"TABLE #{tag_id}", (c_pt[0] + int(18 * scale_ui), c_pt[1] - int(10 * scale_ui)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.85 * scale_ui, (255, 255, 0), max(2, int(2.5 * scale_ui)))
            
        # Si nous avons une matrice d'homographie valide
        if derniere_homographie is not None:
            robot_idx = -1
            for i, tag_id in enumerate(ids.flatten()):
                if tag_id == TAG_ID_ROBOT:
                    robot_idx = i
                    break
                    
            if robot_idx != -1:
                robot_trouve = True
                coins_robot = coins[robot_idx][0]
                centre_image = np.mean(coins_robot, axis=0)
                devant_image = np.mean(coins_robot[0:2], axis=0)
                
                # Application de l'homographie sur le centre et le nez du robot
                points_projeter = np.array([[centre_image], [devant_image]], dtype=np.float32)
                points_monde_brut = cv2.perspectiveTransform(points_projeter, derniere_homographie)
                
                x_brut, y_brut = points_monde_brut[0][0]
                x_devant_brut, y_devant_brut = points_monde_brut[1][0]
                
                # Correction de parallaxe
                x_parallaxe, y_parallaxe = corriger_parallaxe(
                    x_brut, y_brut, HAUTEUR_TAG_ROBOT, HAUTEUR_CAMERA, CENTRE_CAM_X, CENTRE_CAM_Y
                )
                x_devant_parallaxe, y_devant_parallaxe = corriger_parallaxe(
                    x_devant_brut, y_devant_brut, HAUTEUR_TAG_ROBOT, HAUTEUR_CAMERA, CENTRE_CAM_X, CENTRE_CAM_Y
                )
                
                dx = x_devant_parallaxe - x_parallaxe
                dy = y_devant_parallaxe - y_parallaxe
                theta_rad = math.atan2(dy, dx)
                
                # Calibration dynamique (offset)
                if do_calibration:
                    offset_x = DEPART_ABS_X - x_parallaxe
                    offset_y = DEPART_ABS_Y - y_parallaxe
                    do_calibration = False
                    print(f"[VISION WORKER] 🎯 Calibration réussie ! Nouveaux offsets calculés : DX = {offset_x:.2f} mm, DY = {offset_y:.2f} mm")
                    
                x_final = x_parallaxe + offset_x
                y_final = y_parallaxe + offset_y
                
                # Envoi des coordonnées finales via ZMQ PUSH
                message_telemetrie = {
                    "type": "state_update",
                    "data": {
                        "x": float(x_final),
                        "y": float(y_final),
                        "theta": float(theta_rad)
                    }
                }
                
                try:
                    push_socket.send_json(message_telemetrie, flags=zmq.NOBLOCK)
                except zmq.Again:
                    pass
                except Exception as e:
                    print(f"[VISION WORKER] Erreur lors de l'envoi de la position : {e}")

                # Dessiner le cap et les coordonnées sur l'image annotée
                pt_centre = (int(centre_image[0]), int(centre_image[1]))
                pt_devant = (int(devant_image[0]), int(devant_image[1]))
                
                # Calcul d'une flèche allongée et bien visible
                v_dx = pt_devant[0] - pt_centre[0]
                v_dy = pt_devant[1] - pt_centre[1]
                v_len = math.hypot(v_dx, v_dy)
                if v_len > 0:
                    tgt_len = int(110 * scale_ui)
                    pt_arrow = (int(pt_centre[0] + (v_dx / v_len) * tgt_len),
                                int(pt_centre[1] + (v_dy / v_len) * tgt_len))
                else:
                    pt_arrow = pt_devant

                cv2.circle(image_annotee, pt_centre, int(15 * scale_ui), (0, 255, 255), -1)
                cv2.arrowedLine(image_annotee, pt_centre, pt_arrow, (0, 255, 255), max(3, int(6 * scale_ui)), tipLength=0.25)
                
                label_robot = f"ROBOT #{TAG_ID_ROBOT} : X={x_final:.0f} Y={y_final:.0f} O={math.degrees(theta_rad):.1f}deg"
                lbl_pos = (pt_centre[0] - int(120 * scale_ui), pt_centre[1] - int(35 * scale_ui))
                (tw, th), _ = cv2.getTextSize(label_robot, cv2.FONT_HERSHEY_SIMPLEX, 0.85 * scale_ui, max(2, int(2.5 * scale_ui)))
                cv2.rectangle(image_annotee, (lbl_pos[0] - 8, lbl_pos[1] - th - 8), (lbl_pos[0] + tw + 8, lbl_pos[1] + 8), (12, 16, 20), -1)
                cv2.rectangle(image_annotee, (lbl_pos[0] - 8, lbl_pos[1] - th - 8), (lbl_pos[0] + tw + 8, lbl_pos[1] + 8), (0, 255, 255), max(1, int(1.5 * scale_ui)))
                cv2.putText(image_annotee, label_robot, lbl_pos,
                            cv2.FONT_HERSHEY_SIMPLEX, 0.85 * scale_ui, (0, 255, 255), max(2, int(2.5 * scale_ui)))

    # Calcul du FPS
    dt = time.time() - t_start
    if dt > 0:
        fps_calc = 0.9 * fps_calc + 0.1 * (1.0 / dt)

    # Dessin d'un bandeau HUD synthétique haute lisibilité en haut à gauche
    hud_x = int(20 * scale_ui)
    hud_y = int(20 * scale_ui)
    hud_w = int(760 * scale_ui)
    hud_h = int(165 * scale_ui)

    overlay_bg = image_annotee.copy()
    cv2.rectangle(overlay_bg, (hud_x, hud_y), (hud_x + hud_w, hud_y + hud_h), (12, 16, 20), -1)
    cv2.addWeighted(overlay_bg, 0.82, image_annotee, 0.18, 0, image_annotee)
    cv2.rectangle(image_annotee, (hud_x, hud_y), (hud_x + hud_w, hud_y + hud_h), (0, 210, 255), max(2, int(2.5 * scale_ui)))

    f_scale_main = 0.90 * scale_ui
    f_scale_sub = 0.72 * scale_ui
    th_main = max(2, int(2.5 * scale_ui))
    th_sub = max(2, int(2.0 * scale_ui))

    txt_fps = f"CAM USB - {fps_calc:.1f} FPS [{current_preset_key} {frame_w}x{frame_h}]"
    cv2.putText(image_annotee, txt_fps, (hud_x + int(20 * scale_ui), hud_y + int(45 * scale_ui)),
                cv2.FONT_HERSHEY_SIMPLEX, f_scale_main, (0, 210, 255), th_main)
    
    homo_txt = "HOMOGRAPHIE: 4/4 TAGS OK (CALIBRE)" if (derniere_homographie is not None) else f"ATTENTE VINYLES ({len(detected_id_list)}/4 tags vus)"
    homo_col = (0, 255, 128) if (derniere_homographie is not None) else (0, 165, 255)
    cv2.putText(image_annotee, homo_txt, (hud_x + int(20 * scale_ui), hud_y + int(92 * scale_ui)),
                cv2.FONT_HERSHEY_SIMPLEX, f_scale_sub, homo_col, th_sub)

    robot_txt = f"ROBOT: DETECTE (X={x_final:.0f} Y={y_final:.0f})" if robot_trouve else f"ROBOT: NON DETECTE (Tag #{TAG_ID_ROBOT})"
    robot_col = (0, 255, 128) if robot_trouve else (0, 165, 255)
    cv2.putText(image_annotee, robot_txt, (hud_x + int(20 * scale_ui), hud_y + int(138 * scale_ui)),
                cv2.FONT_HERSHEY_SIMPLEX, f_scale_sub, robot_col, th_sub)

    # Mise à jour du buffer de streaming partagé
    status_dict = {
        "connected": True,
        "simulated": simuler_flux,
        "homography_ready": (derniere_homographie is not None),
        "robot_detected": robot_trouve,
        "robot_x": round(float(x_final), 1),
        "robot_y": round(float(y_final), 1),
        "robot_theta_deg": round(math.degrees(theta_rad), 1),
        "offset_x": round(float(offset_x), 1),
        "offset_y": round(float(offset_y), 1),
        "detected_ids": detected_id_list,
        "resolution": current_preset_key,
        "resolution_label": frame_buffer.preset_label,
        "width": frame_w,
        "height": frame_h
    }
    frame_buffer.update(image_corrigee, image_annotee, fps_calc, status_dict)

# Nettoyage en cas de sortie
cap.release()
