#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adaptateur entre la vision déportée (sous-module Base/Vision/vision_deporte,
calcul de pose par solvePnP sur les ArUco 20-23 de la table + tag 2 du robot)
et la base (serveur Go).

Expose la même interface que l'ancien vision_worker C++ :
  - HTTP MJPEG / API REST sur le port 8082 (/stream, /api/status, ...)
  - ZMQ PUSH tcp://localhost:5555 : {"type":"vision_update","data":{x,y,theta,detected,adversaires,pierres}}
  - ZMQ SUB  tcp://localhost:5556 : ordres de la base (calibrate_vision)

Lancement (fait automatiquement par base_stk) :
  uv run --project vision_deporte --with pyzmq python vision_deporte_worker.py
"""

import json
import math
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np
import zmq
from scipy.spatial.transform import Rotation

# Le code de vision importe ses modules à plat (from computePosition import ...)
VISION_SRC = Path(__file__).resolve().parent / "vision_deporte" / "src" / "vision_deporte"
sys.path.insert(0, str(VISION_SRC))

from computePosition import computePosition  # noqa: E402
from tools.detectArucos import arucoDirectory, detectArucos  # noqa: E402

# ==============================================================================
# --- CONFIGURATION ---
# ==============================================================================
CAMERA_ID = int(os.environ.get("VISION_CAMERA_ID", "0"))
# Fenêtre MuJoCo (viewer d'Antony) sur l'écran local de la base (visible en VNC)
VIEWER_ON = os.environ.get("VISION_VIEWER", "1") not in ("0", "false", "no", "off")
TAG_ID_ROBOT = 2
# Tags des robots (règlement Eurobot : 1-5 équipe bleue, 6-10 jaune) autres que le nôtre : adversaires.
# Même taille que notre tag (arucoRobot) ; leur pose est calculée par computePosition (allPoses).
ADVERSAIRE_TAG_IDS = tuple(i for i in range(1, 11) if i != TAG_ID_ROBOT)
arucoDirectory.update({str(i): arucoDirectory[str(TAG_ID_ROBOT)] for i in ADVERSAIRE_TAG_IDS})
# Pierres 2027 : tag 13 sur les 4 grandes faces ; vue de dessus, seule la face du haut compte.
TAG_ID_PIERRE = 13
TAILLE_TAG_PIERRE_MM = float(os.environ.get("VISION_TAG_PIERRE_MM", "50"))   # à mesurer sur une vraie pierre
PIERRE_AXE_TAG_DEG = float(os.environ.get("VISION_PIERRE_AXE_TAG_DEG", "0"))  # axe long de la pierre / axe x du tag
HAUTEUR_PIERRE_MM = 110.0   # pierres posées à plat : la face du haut d'une pile de n pierres est à ~n x 110 mm
_c = TAILLE_TAG_PIERRE_MM / 2
arucoDirectory[str(TAG_ID_PIERRE)] = np.array([[-_c, _c, 0.0], [_c, _c, 0.0], [_c, -_c, 0.0], [-_c, -_c, 0.0]])
TABLE_TAG_IDS = (20, 21, 22, 23)
# Tags de la table : 96 mm mesurés (vision_deporte les déclare à 100 mm -> distances +4 %, vérifié le 2026-10-27 :
# 1 000 mm au mètre lus ~1 040 par la caméra)
TAILLE_TAG_TABLE_MM = float(os.environ.get("VISION_TAG_TABLE_MM", "96"))
_t = TAILLE_TAG_TABLE_MM / 2
for _id in TABLE_TAG_IDS:
    arucoDirectory[str(_id)] = np.array([[-_t, _t, 0.0], [_t, _t, 0.0], [_t, -_t, 0.0], [-_t, -_t, 0.0]])

# Résolution de la calibration (cameraParams.npz) : les intrinsèques sont
# remises à l'échelle si on bascule sur un autre preset.
CALIB_W, CALIB_H = 3840, 2160

CAMERA_PRESETS = {
    "4K": {"width": 3840, "height": 2160, "fps": 30, "label": "4K @ 30fps"},
    "1080P": {"width": 1920, "height": 1080, "fps": 60, "label": "1080p @ 60fps"},
    "2K": {"width": 2560, "height": 1440, "fps": 30, "label": "2K @ 30fps"},
}


# Repères : définition unique dans Rasp/core/frames.py (même dépôt sur la base)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Rasp"))
from core.frames import camera_to_table  # noqa: E402


def _vers_table(compute_pos, pos_monde, R_monde_tag):
    """Pose monde (computePosition) -> (x, y, z mm, cap degrés, axe z du tag) dans le repère table/robot."""
    R_wt = compute_pos.R_world_table
    pos_table = R_wt.inv().apply(np.asarray(pos_monde) - compute_pos.posTable)
    R_table_tag = R_wt.inv() * R_monde_tag
    ax = R_table_tag.apply([1.0, 0.0, 0.0])
    cap = math.degrees(math.atan2(ax[1], ax[0]))
    x, y, cap = table_to_base(pos_table, cap)
    return x, y, float(pos_table[2]) * 1000.0, cap, R_table_tag.apply([0.0, 0.0, 1.0])


def adversaires_table(compute_pos):
    """Robots adverses (tags ADVERSAIRE_TAG_IDS) dans le repère table/robot (mm), comme notre robot :
    allPoses est en repère monde, ramené sur la table par posTable / R_world_table."""
    out = []
    for i in ADVERSAIRE_TAG_IDS:
        p = getattr(compute_pos, "allPoses", {}).get(str(i))
        if p is None:
            continue
        x, y, _, cap, _ = _vers_table(compute_pos, p[0], Rotation.from_quat(p[1], scalar_first=True))
        out.append({"id": i, "x": round(float(x), 1), "y": round(float(y), 1), "theta": round(float(cap), 1)})
    return out


def pierres_table(compute_pos, detections, ids):
    """Pierres (tag 13 face vers le haut), une par détection : computePosition ne garde qu'une pose
    par numéro de tag, or toutes les pierres portent le 13. detections[k] (solvePnP) va avec ids[k].
    [{x, y, z, theta, nb}] repère table/robot ; theta = axe long de la boîte ; nb = pierres dans la pile
    (hauteur du tag / 110 mm : seule la face du haut de la pile est vue)."""
    cam = getattr(compute_pos, "allPoses", {}).get("cam")
    if cam is None:
        return []
    R_monde_cam = Rotation.from_quat(cam[1], scalar_first=True)
    out = []
    for k, i in enumerate(ids):
        if int(i) != TAG_ID_PIERRE or k >= len(detections):
            continue
        rvec, tvec = np.array(detections[k][1:]).reshape(2, 3)
        R_monde_tag = R_monde_cam * Rotation.from_rotvec(rvec)
        pos_monde = R_monde_cam.apply(tvec / 1000.0) + np.asarray(cam[0])
        x, y, z, cap, normale = _vers_table(compute_pos, pos_monde, R_monde_tag)
        if abs(normale[2]) < 0.8:            # face de côté vue en biais : position peu fiable
            continue
        if any(math.hypot(x - p["x"], y - p["y"]) < 80 for p in out):
            continue
        nb = int(max(1, min(6, round(z / HAUTEUR_PIERRE_MM)))) if z > 0 else 1
        out.append({"x": round(float(x), 1), "y": round(float(y), 1), "z": round(z, 1),
                    "theta": round(float(cap + PIERRE_AXE_TAG_DEG), 1), "nb": nb})
    return out


def hauteur_camera_mm(compute_pos):
    """Hauteur de la caméra au-dessus du plan des tags de table vus (contrôle d'échelle : 1 550 mm mesurés
    le 2026-10-27), None si la caméra ou aucun tag de table n'est placé."""
    poses = compute_pos.allPoses
    tables = [poses[str(i)][0][2] for i in TABLE_TAG_IDS if str(i) in poses]
    if "cam" not in poses or not tables:
        return None
    return round(float(poses["cam"][0][2] - np.mean(tables)) * 1000.0)


def table_to_base(pos_m, theta_deg):
    """Pose computePosition (m, degrés) -> repère table/robot (mm, degrés), cf. core/frames.py."""
    return camera_to_table(pos_m[0], pos_m[1], theta_deg)


# ==============================================================================
# --- BUFFER DE STREAMING + SERVEUR HTTP MJPEG (PORT 8082) ---
# ==============================================================================
class StreamFrameBuffer:
    def __init__(self):
        self.lock = threading.Lock()
        self.raw_jpeg = None
        self.annotated_jpeg = None
        self.show_aruco = True
        self.current_preset = "4K"
        self.preset_label = CAMERA_PRESETS["4K"]["label"]
        self.pending_preset = None
        self.status = {}

    @staticmethod
    def _encode(img):
        h, w = img.shape[:2]
        if w > 1920:
            img = cv2.resize(img, (1920, int(h * 1920 / w)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return buf.tobytes() if ok else None

    def update(self, raw, annotated, status):
        raw_bytes = self._encode(raw)
        annotated_bytes = self._encode(annotated)
        with self.lock:
            self.raw_jpeg = raw_bytes
            self.annotated_jpeg = annotated_bytes
            self.status = status

    def get_frame(self, force_aruco=None):
        with self.lock:
            use_aruco = self.show_aruco if force_aruco is None else force_aruco
            if use_aruco:
                return self.annotated_jpeg or self.raw_jpeg
            return self.raw_jpeg or self.annotated_jpeg

    def toggle_aruco(self, state=None):
        with self.lock:
            self.show_aruco = (not self.show_aruco) if state is None else bool(state)
            return self.show_aruco

    def request_preset(self, preset=None):
        with self.lock:
            if preset and preset.upper() in CAMERA_PRESETS:
                self.pending_preset = preset.upper()
            elif not preset:
                self.pending_preset = "1080P" if self.current_preset == "4K" else "4K"
            return self.pending_preset or self.current_preset

    def pop_pending_preset(self):
        with self.lock:
            p, self.pending_preset = self.pending_preset, None
            return p

    def set_active_preset(self, key, label):
        with self.lock:
            self.current_preset = key
            self.preset_label = label

    def get_status(self):
        with self.lock:
            data = dict(self.status)
            data["show_aruco"] = self.show_aruco
            data["resolution"] = self.current_preset
            data["resolution_label"] = self.preset_label
            return data


frame_buffer = StreamFrameBuffer()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class VisionHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def _json(self, obj):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path in ("/stream", "/stream_aruco", "/stream_raw"):
            force_aruco = None
            if path == "/stream_aruco":
                force_aruco = True
            elif path == "/stream_raw":
                force_aruco = False
            elif "aruco" in query:
                force_aruco = query["aruco"][0].lower() in ("1", "true", "yes", "on")

            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self._cors()
            self.end_headers()
            try:
                last = None
                while True:
                    jpeg = frame_buffer.get_frame(force_aruco)
                    if jpeg is None or jpeg is last:
                        time.sleep(0.02)
                        continue
                    last = jpeg
                    self.wfile.write(b"--frame\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(jpeg)))
                    self.end_headers()
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
            except Exception:
                pass  # Client déconnecté

        elif path == "/api/status":
            self._json(frame_buffer.get_status())

        elif path == "/api/toggle_aruco":
            state = None
            if "state" in query:
                state = query["state"][0].lower() in ("1", "true", "yes", "on")
            self._json({"status": "ok", "show_aruco": frame_buffer.toggle_aruco(state)})

        elif path in ("/api/toggle_resolution", "/api/toggle_mode", "/api/set_resolution"):
            requested = frame_buffer.request_preset(query.get("mode", [None])[0])
            self._json({
                "status": "ok",
                "requested": requested,
                "current": frame_buffer.current_preset,
                "label": frame_buffer.preset_label,
            })

        else:
            self.send_response(404)
            self._cors()
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()


# ==============================================================================
# --- ZMQ ---
# ==============================================================================
reset_filter = threading.Event()


def listen_orders():
    sub = zmq.Context.instance().socket(zmq.SUB)
    sub.connect("tcp://localhost:5556")
    sub.setsockopt_string(zmq.SUBSCRIBE, "")
    print("[ZMQ SUB] Connecté au port 5556, en attente d'ordres...", flush=True)
    while True:
        try:
            msg = sub.recv_string()
            if "calibrate_vision" in msg:
                # La pose est absolue (tags de table) : pas d'offset à calculer,
                # on réinitialise seulement le filtre passe-bas de la table.
                print("[ZMQ SUB] 🎯 'calibrate_vision' reçu : réinitialisation du filtre table.", flush=True)
                reset_filter.set()
        except Exception as e:
            print(f"[ZMQ SUB] Erreur réception : {e}", flush=True)
            time.sleep(0.1)


# ==============================================================================
# --- CAMÉRA ---
# ==============================================================================
def scaled_camera_params(base_params, w, h):
    sx, sy = w / CALIB_W, h / CALIB_H
    K = np.array(base_params["cameraMatrix"], dtype=np.float64).copy()
    K[0, 0] *= sx
    K[0, 2] *= sx
    K[1, 1] *= sy
    K[1, 2] *= sy
    return {"cameraMatrix": K, "distCoeffs": np.array(base_params["distCoeffs"])}


def apply_preset(cap, key):
    cfg = CAMERA_PRESETS[key]
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["width"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["height"])
    cap.set(cv2.CAP_PROP_FPS, cfg["fps"])
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[CAM] Résolution {key} : {w}x{h} @ {cfg['fps']}fps", flush=True)
    return w, h


def open_camera():
    cap = cv2.VideoCapture(CAMERA_ID, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap = cv2.VideoCapture(CAMERA_ID)
    if not cap.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir la caméra {CAMERA_ID}")
    return cap


# ==============================================================================
# --- ANNOTATIONS ---
# ==============================================================================
def annotate(img, corners, ids, robot, fps, preset_key, table_seen):
    scale = max(1.0, img.shape[1] / 1920.0)
    th = max(2, int(2.5 * scale))
    for c, tag_id in zip(corners, ids):
        pts = c.astype(np.int32).reshape((-1, 1, 2))
        known = str(tag_id) in arucoDirectory
        color = (0, 255, 0) if known else (120, 120, 120)
        cv2.polylines(img, [pts], True, color, th)
        cv2.putText(img, f"#{tag_id}", (int(c[0, 0]), int(c[0, 1] - 10 * scale)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9 * scale, color, th)
        if tag_id == TAG_ID_ROBOT and robot is not None:
            centre = c.mean(axis=0)
            label = f"ROBOT X={robot[0]:.0f} Y={robot[1]:.0f} O={robot[2]:.1f}deg"
            cv2.putText(img, label, (int(centre[0] - 150 * scale), int(centre[1] - 60 * scale)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9 * scale, (0, 255, 255), th)

    lines = [
        (f"VISION DEPORTEE - {fps:.1f} FPS [{preset_key} {img.shape[1]}x{img.shape[0]}]", (0, 210, 255)),
        ("TABLE: OK" if table_seen else "TABLE: ATTENTE TAGS 20-23", (0, 255, 128) if table_seen else (0, 165, 255)),
        (f"ROBOT: X={robot[0]:.0f} Y={robot[1]:.0f} O={robot[2]:.1f}deg" if robot else f"ROBOT: NON DETECTE (Tag #{TAG_ID_ROBOT})",
         (0, 255, 128) if robot else (0, 165, 255)),
    ]
    x0, y0 = int(20 * scale), int(20 * scale)
    cv2.rectangle(img, (x0, y0), (x0 + int(760 * scale), y0 + int(165 * scale)), (12, 16, 20), -1)
    for i, (txt, col) in enumerate(lines):
        cv2.putText(img, txt, (x0 + int(20 * scale), y0 + int((45 + 46 * i) * scale)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8 * scale, col, th)
    return img


# ==============================================================================
# --- BOUCLE PRINCIPALE ---
# ==============================================================================
def die_with_parent():
    """S'arrête si le parent (uv, lancé par base_stk) meurt : libère caméra et port 8082."""
    try:
        import ctypes
        import signal
        PR_SET_PDEATHSIG = 1
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
    except Exception:
        pass


def ensure_display():
    """base_stk lancé en ssh : viser l'écran :0 de la session graphique."""
    if os.environ.get("DISPLAY"):
        return
    os.environ["DISPLAY"] = ":0"
    if not os.environ.get("XAUTHORITY"):
        candidates = [p for p in Path("/tmp").glob("xauth_*") if p.is_file() and p.stat().st_uid == os.getuid()]
        candidates += [p for p in [Path.home() / ".Xauthority"] if p.exists()]
        if candidates:
            os.environ["XAUTHORITY"] = str(max(candidates, key=lambda p: p.stat().st_mtime))


def ecran_branche():
    """Un écran est-il branché (DRM) ? Sans écran, GLFW avorte le processus (assertion C dans
    glfwGetVideoMode, impossible à rattraper en Python) : base capot fermé / écran éteint."""
    statuts = list(Path("/sys/class/drm").glob("card*-*/status"))
    if not statuts:
        return True  # pas de DRM lisible (VM, autre OS) : on tente
    return any(p.read_text().strip() == "connected" for p in statuts)


def make_compute_position():
    if VIEWER_ON and not ecran_branche():
        print("[MUJOCO] Aucun écran branché : poursuite sans affichage.", flush=True)
    elif VIEWER_ON:
        ensure_display()
        try:
            cp = computePosition(mujocoOn=True)
            print(f"[MUJOCO] Viewer ouvert sur {os.environ.get('DISPLAY')}", flush=True)
            return cp
        except Exception as e:
            print(f"[MUJOCO] Viewer indisponible ({e}), poursuite sans affichage.", flush=True)
    return computePosition(mujocoOn=False)


def main():
    die_with_parent()
    base_params = dict(np.load(VISION_SRC / "tools" / "cameraParams.npz"))

    threading.Thread(target=listen_orders, daemon=True).start()
    server = ThreadedHTTPServer(("0.0.0.0", 8082), VisionHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("[STREAM] Serveur vidéo démarré sur http://0.0.0.0:8082/stream", flush=True)

    push = zmq.Context.instance().socket(zmq.PUSH)
    push.setsockopt(zmq.SNDHWM, 2)
    push.connect("tcp://localhost:5555")

    cap = open_camera()
    preset_key = "4K"
    w, h = apply_preset(cap, preset_key)
    frame_buffer.set_active_preset(preset_key, CAMERA_PRESETS[preset_key]["label"])

    detector = detectArucos(scaled_camera_params(base_params, w, h))
    compute_pos = make_compute_position()
    fps = 0.0
    print("[MAIN] Pipeline vision déportée prêt.", flush=True)

    while True:
        t0 = time.time()

        pending = frame_buffer.pop_pending_preset()
        if pending:
            preset_key = pending
            w, h = apply_preset(cap, preset_key)
            frame_buffer.set_active_preset(preset_key, CAMERA_PRESETS[preset_key]["label"])
            detector.cameraParams = scaled_camera_params(base_params, w, h)

        if reset_filter.is_set():
            reset_filter.clear()
            compute_pos.posTable = np.array([0.0, 0.0, 0.0])
            compute_pos.R_world_table = Rotation.identity()

        ok, frame = cap.read()
        if not ok:
            print("[CAM] Échec de lecture de la frame.", flush=True)
            time.sleep(0.1)
            continue

        detector.changeImage(frame)  # Applique la rotation 180° de la caméra
        detector.detect()
        raw_ids = [] if detector.detected_ids is None else [int(i) for i in np.ravel(detector.detected_ids)]
        corners = detector.detected_corners if raw_ids else []

        # detect() ne calcule la pose que des tags connus : on aligne les ids
        # sur detectedArucos, sinon computePosition rejette la frame dès qu'un
        # tag étranger (éléments de jeu...) est visible.
        known_ids = np.array([i for i in raw_ids if str(i) in arucoDirectory], dtype=int)
        table_seen = any(i in TABLE_TAG_IDS for i in known_ids)

        robot = None
        if len(known_ids):
            result = compute_pos.detectToRobotPosition(detector.detectedArucos, known_ids)
            if isinstance(result, tuple):
                robot = table_to_base(result[0], float(result[1]))

        # Affichage seul : pas de mj_step (contrairement à main.py), sinon la physique
        # fait bouger le robot simulé (freejoint), dont computePosition lit la pose.
        # update_mujoco fait déjà mj_forward. Fermer la fenêtre n'arrête pas la vision.
        if compute_pos.mujocoOn and compute_pos.viewer.is_running():
            compute_pos.viewer.sync()

        if robot is not None:
            msg = {"type": "vision_update",
                   "data": {"x": robot[0], "y": robot[1], "theta": robot[2], "detected": True,
                            "adversaires": adversaires_table(compute_pos),
                            "pierres": pierres_table(compute_pos, detector.detectedArucos, known_ids)}}
            try:
                push.send_json(msg, flags=zmq.NOBLOCK)
            except zmq.Again:
                pass

        dt = time.time() - t0
        if dt > 0:
            fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt

        raw = detector.image
        annotated = annotate(raw.copy(), corners, raw_ids, robot, fps, preset_key, table_seen)
        frame_buffer.update(raw, annotated, {
            "connected": True,
            "simulated": False,
            "homography_ready": table_seen,
            "robot_detected": robot is not None,
            "robot_tag_id": TAG_ID_ROBOT,
            "robot_x": round(robot[0], 1) if robot else 0.0,
            "robot_y": round(robot[1], 1) if robot else 0.0,
            "robot_theta_deg": round(robot[2], 1) if robot else 0.0,
            "offset_x": 0.0,
            "offset_y": 0.0,
            "fps": round(fps, 1),
            "width": w,
            "height": h,
            "detected_ids": raw_ids,
            "hauteur_camera_mm": hauteur_camera_mm(compute_pos) if robot else None,
        })


if __name__ == "__main__":
    main()
