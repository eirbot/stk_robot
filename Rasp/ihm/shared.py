import os
import json
import socket
import time
from collections import deque

from utils import LedStrip, AudioManager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR) 
CONFIG_PATH = os.path.join(ROOT_DIR, "config.json")
AUDIO_DIR = os.path.join(BASE_DIR, "audio")

if not os.path.exists(AUDIO_DIR): os.makedirs(AUDIO_DIR)

strategies_list = {}

def load_config():
    if not os.path.exists(CONFIG_PATH): return {}
    with open(CONFIG_PATH, 'r') as f: return json.load(f)

def save_config(new_cfg):
    global cfg
    cfg.update(new_cfg)
    with open(CONFIG_PATH, 'w') as f: json.dump(cfg, f, indent=4)

cfg = load_config()

zmq_client_instance = None

def send_sys_info(sys_info_data):
    if zmq_client_instance:
        zmq_client_instance.send_event("sys_info", sys_info_data)

def send_log(msg, log_type="info"):
    if zmq_client_instance:
        zmq_client_instance.send_event("new_log", {"msg": msg, "type": log_type, "time": ""})

# Hardware
from utils.sensors.camera_libcamera import LibCamera
leds = LedStrip(enabled=cfg.get("leds_enabled", True))
audio = AudioManager(cfg.get("audio", {}))

# Caméra partagée
camera = None
cam_cfg = cfg.get("camera", {})
if cam_cfg.get("enabled", True):
    try:
        # On initialise la caméra une seule fois pour tout le robot
        camera = LibCamera(resolution=(1640, 1232), framerate=10).start()
    except Exception as e:
        print(f"[CAM] Erreur initialisation globale : {e}")
        camera = None

# LiDAR partagé
lidar_bin = None

def die_with_parent():
    """preexec_fn pour les Popen : le fils reçoit SIGTERM si le thread qui l'a lancé meurt
    (stop.sh tue main_robot.py par SIGTERM, sans passer par ses blocs finally)."""
    try:
        import ctypes, signal
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except Exception:
        pass
lidar_process = None

# Etat Global Partagé
state = {
    "config": cfg,
    "team": cfg.get("team", "BLEUE"),
    "match_running": False,
    "match_finished": False,
    "timer_str": "100.0",
    "start_time": None,
    "tirette": "NON-ARMED",
    "lidar_mode": cfg.get("lidar_mode", "MATCH"),
    "music_enabled": cfg.get("music_enabled", True),
    "leds_enabled": cfg.get("leds_enabled", True),
    "fsm_state": "INIT",
    "strat_mode": cfg.get("strat_mode", "DYNAMIC"),
    "static_strat": cfg.get("static_strat"),
    # En STATIC on démarre directement sur la strat de la config (sinon le robot lançait « 1 »)
    "strat_id": cfg.get("static_strat") if cfg.get("strat_mode") == "STATIC" and cfg.get("static_strat") else cfg.get("strat_id", 1)
}

# Position Robot Partagée (Mise à jour par le Main, Lue par l'IHM)
robot_pos = {'x': 1500, 'y': 1000, 'theta': 0}

# Dernières poses de la caméra zénithale (base) : (heure de réception Rasp, x, y, theta en degrés)
vision_poses = deque(maxlen=60)

def send_led_cmd(cmd):
    if not state["leds_enabled"]: return
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.sendto(cmd.encode(), "/tmp/ledsock")
        sock.close()
    except: pass

def team_color_cmd():
    """Commande LED de la couleur de l'équipe courante."""
    return "COLOR:255,160,0" if state.get("team") == "JAUNE" else "COLOR:0,0,255"

def update_config_from_server(new_cfg):
    global cfg
    cfg.update(new_cfg)
    state["config"] = cfg
    
    # 1. Couleur Equipe : appliquer seulement si l'équipe a changé et qu'aucune alerte n'est active
    if "team" in new_cfg:
        new_team = new_cfg["team"]
        old_team = state.get("team")
        if new_team != old_team:
            state["team"] = new_team
            # STOPPED ne bloque plus : après un arrêt on doit pouvoir changer d'équipe et le voir
            has_active_alert = (
                state.get("bat_low", False) or
                state.get("tirette_msg") == "REMOVE_TO_RESET" or
                state.get("tirette") == "ARMED" or
                state.get("match_running", False)
            )
            if not has_active_alert:
                send_led_cmd(team_color_cmd())
            
    # 2. Mode LiDAR
    if "lidar_mode" in new_cfg:
        state["lidar_mode"] = new_cfg["lidar_mode"]
        
    # 4. Musique
    if "music_enabled" in new_cfg:
        state["music_enabled"] = new_cfg["music_enabled"]
        
    # 5. LEDs activées
    if "leds_enabled" in new_cfg:
        state["leds_enabled"] = new_cfg["leds_enabled"]
        
        
    # 7. Mode stratégie (Statique / Dynamique)
    if "strat_mode" in new_cfg:
        old_mode = state.get("strat_mode")
        state["strat_mode"] = new_cfg["strat_mode"]
        # Réassigner strat_id seulement si on bascule en STATIC
        if old_mode != 'STATIC' and new_cfg["strat_mode"] == 'STATIC' and cfg.get('static_strat'):
            state['strat_id'] = cfg['static_strat']
            
    # 8. Choix de la stratégie statique
    if "static_strat" in new_cfg:
        old_strat = state.get("static_strat")
        state["static_strat"] = new_cfg["static_strat"]
        # Réassigner strat_id seulement si la config static_strat a elle-même changé
        if old_strat != new_cfg["static_strat"] and state.get("strat_mode") == 'STATIC':
            state['strat_id'] = new_cfg["static_strat"]
            
    # 9. Volume Audio
    if "audio" in new_cfg:
        try:
            audio.load_config(cfg.get('audio', {}))
        except Exception as e:
            print(f"[CONFIG] Erreur rechargement audio : {e}")
            
    # 10. Gestion dynamique de la caméra
    global camera
    if "camera" in new_cfg:
        cam_info = new_cfg["camera"]
        new_enabled = True
        if isinstance(cam_info, dict):
            new_enabled = cam_info.get("enabled", True)
        else:
            new_enabled = bool(cam_info)
            
        if new_enabled and camera is None:
            try:
                print("[CONFIG] 📷 Initialisation dynamique de la caméra...")
                camera = LibCamera(resolution=(1640, 1232), framerate=10).start()
            except Exception as e:
                print(f"[CAM] Erreur initialisation dynamique : {e}")
                camera = None
        elif not new_enabled and camera is not None:
            print("[CONFIG] 📷 Arrêt dynamique de la caméra...")
            try:
                camera.stop()
            except Exception as e:
                print(f"[CAM] Erreur lors de l'arrêt de la caméra : {e}")
            camera = None