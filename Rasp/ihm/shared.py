import os
import json
import socket
import time
from collections import deque

import hardware
from utils import AudioManager
from core.config_store import ConfigError, ConfigStore
from core.match_state import MatchError, MatchState, TEAM_COLORS
from core.localisation import Localisation
from core.planif import Chaleur
from utils.loc_recorder import LocRecorder

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR) 
# ROBOT_CONFIG : autre fichier de config (tests, simulation)
CONFIG_PATH = os.environ.get("ROBOT_CONFIG", os.path.join(ROOT_DIR, "config.json"))
AUDIO_DIR = os.path.join(BASE_DIR, "audio")

if not os.path.exists(AUDIO_DIR): os.makedirs(AUDIO_DIR)

strategies_list = {}

# Config du robot : source unique de vérité (validée, enregistrée par core/config_store.py).
# `cfg` est le dict de config_store, modifié en place : il reste toujours à jour.
config_store = ConfigStore(CONFIG_PATH)
cfg = config_store.data

zmq_client_instance = None
robot = None          # RobotActions unique (créé par main_robot.py) : commandes hors stratégie
calibration = None    # strat/calibration.py, créée à la première demande

def send_sys_info(sys_info_data):
    if zmq_client_instance:
        zmq_client_instance.send_event("sys_info", sys_info_data)

def send_log(msg, log_type="info"):
    if zmq_client_instance:
        zmq_client_instance.send_event("new_log", {"msg": msg, "type": log_type, "time": ""})

# Sons (lance un lecteur externe à la demande : rien n'est ouvert ici). Le reste du matériel
# (ESP, caméra) est démarré par hardware.start(), appelé par main_robot.py.
audio = AudioManager(cfg.get("audio", {}))

# LiDAR partagé
lidar_bin = None
lidar_points = []     # points du dernier tour (repère table, hors table retirés), cf. LiDAR/lidar_thread.py
lidar_points_t = 0.0  # instant de ce tour (0 = jamais)

def die_with_parent():
    """preexec_fn pour les Popen : le fils reçoit SIGTERM si le thread qui l'a lancé meurt
    (stop.sh tue main_robot.py par SIGTERM, sans passer par ses blocs finally)."""
    try:
        import ctypes, signal
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except Exception:
        pass
lidar_process = None

# Etat Global Partagé. Les champs du match (fsm_state, match_running, tirette, timer_str,
# team, strat_id, test_mode...) sont écrits UNIQUEMENT par `match` (core/match_state.py) :
# le reste du code les lit ici, et appelle les méthodes de `match` pour les modifier.
state = {
    "config": cfg,
    "lidar_mode": cfg.get("lidar_mode", "MATCH"),
    "music_enabled": cfg.get("music_enabled", True),
    "leds_enabled": cfg.get("leds_enabled", True),
}

# Les effets matériels (LED, moteurs, actionneurs, son) sont branchés par main_robot.py
match = MatchState(state, config_store)

# Position Robot Partagée (Mise à jour par le Main, Lue par l'IHM)
robot_pos = {'x': 1500, 'y': 1000, 'theta': 0}

# Dernières poses de la caméra zénithale (base) : (heure de réception Rasp, x, y, theta en degrés)
vision_poses = deque(maxlen=60)

# Robots adverses vus par la caméra zénithale : id -> (t, x, y, vx, vy) (repère table, mm, mm/s)
adversaires = {}
# Heat map de l'adversaire pour le planificateur (core/planif.py)
chaleur = Chaleur()
# Dernier chemin planifié (strat/actions.py : aller) : {"points": [[x, y]...], "cible": [x, y, theta]}
plan_courant = None
# Événements de stratégie (goto, plan, action, retour...) : boîte noire + base
evenements = deque(maxlen=1000)


def evenement(kind, **data):
    """Note un événement de stratégie (boîte noire, utils/telemetry_logger.py) et l'envoie à la base."""
    evenements.append((time.time(), kind, data))
    if zmq_client_instance:
        zmq_client_instance.send_event("evenement", {"type": kind, **data})


def adversaires_recents(age_max_s=1.0, now=None):
    """[(x, y, vx, vy)] des adversaires vus il y a moins de age_max_s."""
    now = time.time() if now is None else now
    return [(x, y, vx, vy) for t, x, y, vx, vy in list(adversaires.values()) if now - t <= age_max_s]


def noter_adversaire(id_, x, y, t):
    """Nouvelle observation d'un adversaire : vitesse lissée, heat map (5 Hz max par robot)."""
    prec = adversaires.get(id_)
    vx = vy = 0.0
    if prec and 0.02 < t - prec[0] < 1.0:
        a = 0.3
        vx = (1 - a) * prec[3] + a * (x - prec[1]) / (t - prec[0])
        vy = (1 - a) * prec[4] + a * (y - prec[2]) / (t - prec[0])
    if prec is None or t - prec[0] >= 0.2:
        chaleur.observer(x, y, t)
    if prec is None or t - prec[0] >= 0.02:
        adversaires[id_] = (t, x, y, vx, vy)

# Fusion odométrie ESP + caméra : robot_pos est la pose fusionnée (repère table),
# l'ESP garde son propre repère (cf. core/localisation.py)
loc = Localisation(lambda: config_store.data.get("vision_odom", {}))
# Odométrie brute + caméra, pour régler la fusion (tools/regler_fusion.py)
loc_log = LocRecorder(enabled=cfg.get("vision_odom", {}).get("enregistrer", True))


def refresh_robot_pos():
    """Recopie la pose fusionnée dans robot_pos (après une correction caméra)."""
    pose = loc.pose()
    if pose:
        robot_pos.update({'x': pose[0], 'y': pose[1], 'theta': pose[2]})


# Instant du dernier set_pos (None = pose jamais donnée : l'odométrie part de (0, 0, 0), un coin)
pose_connue_t = None


def pose_fiable(sigma_max_mm=150.0):
    """Pose fusionnée (x, y, theta) si on peut s'y fier (set_pos fait ou caméra acceptée, incertitude
    raisonnable), sinon None. Sert à ce qui raisonne dans le repère table (filtre LiDAR, planificateur)."""
    pose = loc.pose()
    if pose is None or (pose_connue_t is None and not loc.stats.get("acceptees")):
        return None
    return pose if loc.sigma()[0] <= sigma_max_mm else None


def set_known_pose(x, y, theta, odo_pose=None):
    """Pose connue (set_pos) : remet la fusion à zéro et met à jour robot_pos."""
    global pose_connue_t
    t = time.time()
    pose_connue_t = t
    loc.reset((x, y, theta), odo_pose, t=t)
    loc_log.write("s", t, *(odo_pose if odo_pose is not None else (x, y, theta)))
    robot_pos.update({'x': x, 'y': y, 'theta': theta})

def send_led_cmd(cmd):
    if not state["leds_enabled"]: return
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.sendto(cmd.encode(), "/tmp/ledsock")
        sock.close()
    except: pass

def team_color_cmd():
    """Commande LED de la couleur de l'équipe courante."""
    return TEAM_COLORS.get(state.get("team"), TEAM_COLORS["BLEUE"])

def update_config_from_server(new_cfg):
    """Modification de config demandée par la base (ou un bouton) : validée, enregistrée,
    puis effets appliqués. Renvoie (clés modifiées, message d'erreur ou None)."""
    try:
        changed = match.apply_config(new_cfg)
    except (MatchError, ConfigError) as e:
        print(f"[CONFIG] Modification refusée {new_cfg} : {e}")
        return {}, str(e)
    if not changed:
        return {}, None
    new_cfg = {}
    for key, value in changed.items():  # clés pointées -> dict imbriqué pour la suite
        cur = new_cfg
        parts = key.split(".")
        for k in parts[:-1]:
            cur = cur.setdefault(k, {})
        cur[parts[-1]] = value
    state["config"] = cfg

    # 2. Mode LiDAR
    if "lidar_mode" in new_cfg:
        state["lidar_mode"] = new_cfg["lidar_mode"]
        
    # 4. Musique
    if "music_enabled" in new_cfg:
        state["music_enabled"] = new_cfg["music_enabled"]
        
    # 5. LEDs activées
    if "leds_enabled" in new_cfg:
        state["leds_enabled"] = new_cfg["leds_enabled"]
        
        
    # (équipe, stratégie, mode test : gérés par match.apply_config)

    # 9. Volume Audio
    if "audio" in new_cfg:
        try:
            audio.load_config(cfg.get('audio', {}))
        except Exception as e:
            print(f"[CONFIG] Erreur rechargement audio : {e}")
            
    # 10. Caméra embarquée
    if "camera" in new_cfg:
        cam_info = new_cfg["camera"]
        hardware.set_camera_enabled(cam_info.get("enabled", True) if isinstance(cam_info, dict) else bool(cam_info))

    return changed, None
