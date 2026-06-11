import os
import json
import socket
import time

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

# Etat Global Partagé
state = {
    "config": cfg,
    "team": cfg.get("team", "BLEUE"),
    "score_current": 0,
    "match_running": False,
    "match_finished": False,
    "timer_str": "100.0",
    "start_time": None,
    "tirette": "NON-ARMED",
    "lidar_mode": cfg.get("lidar_mode", "MATCH"),
    "music_enabled": cfg.get("music_enabled", True),
    "leds_enabled": cfg.get("leds_enabled", True),
    "manual_score_enabled": cfg.get("manual_score_enabled", True),
    "strat_id": "strat_homologation", 
    "fsm_state": "INIT",
    "strat_mode": cfg.get("strat_mode", "DYNAMIC"),
    "strat_id": cfg.get("strat_id", 1),
    "ekf_enabled": cfg.get("ekf_enabled", True)
}

# Variable exposée en tant qu'attribut pour le bypass de sécu
ekf_enabled = state["ekf_enabled"]

# Position Robot Partagée (Mise à jour par le Main, Lue par l'IHM)
robot_pos = {'x': 1500, 'y': 1000, 'theta': 0}

def send_led_cmd(cmd):
    if not state["leds_enabled"]: return
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.sendto(cmd.encode(), "/tmp/ledsock")
        sock.close()
    except: pass