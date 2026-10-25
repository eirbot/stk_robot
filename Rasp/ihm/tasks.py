# ihm/tasks.py
import time
import psutil
import os
import numpy as np

import hardware
from core import frames, preflight
# On assure d'importer robot_pos
from ihm.shared import state, audio, send_led_cmd, robot_pos, send_sys_info
from utils import get_ip, get_battery_voltage, get_cpu_temp, get_battery_current, get_voltage_float
from utils import system_info

_depart_cache = {}  # chemin de la stratégie -> (mtime, pose de départ côté BLEUE)


def _depart(nom):
    """Pose du premier set_pos de la stratégie (côté BLEUE), relue seulement si le fichier change."""
    chemin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "strat", "strategies", f"{nom}.py")
    try:
        mtime = os.path.getmtime(chemin)
    except OSError:
        return None
    if _depart_cache.get(chemin, (None,))[0] != mtime:
        with open(chemin, encoding="utf-8") as f:
            _depart_cache[chemin] = (mtime, preflight.depart_strategie(f.read()))
    return _depart_cache[chemin][1]


def checklist(shared, volts, now):
    """Entrées de core/preflight.py lues dans l'état du robot, puis évaluation."""
    esp, act = hardware.esp, hardware.actionneurs
    strat = state.get("strat_id")  # ce que strat/main_strat.py lancera
    depart = _depart(strat) if strat else None
    if depart:
        depart = frames.mirror_for_team(*depart, team=state.get("team", "BLEUE"))
    pose_cam, age_cam = None, None
    if shared.vision_poses:
        t, x, y, th = shared.vision_poses[-1]
        age_cam = now - t
        pose_cam = frames.apply_camera_repere(x, y, th, shared.cfg.get("vision_odom", {}).get("repere", {}))
    try:
        temp = float(str(get_cpu_temp()).replace("°C", ""))
    except ValueError:
        temp = None
    cam_cfg = shared.cfg.get("camera", {})
    return preflight.evaluer({
        "esp_moteurs": bool(esp and esp.connected),
        "esp_moteurs_age_s": now - esp.last_rx_time if esp and getattr(esp, "last_rx_time", None) else None,
        "esp_actionneurs": bool(act and act.ser and act.ser.is_open),
        "lidar_mode": state.get("lidar_mode", "MATCH"),
        "lidar_age_s": now - shared.lidar_points_t if shared.lidar_points_t else None,
        "camera_zen_age_s": age_cam, "pose_camera": pose_cam,
        "tension_v": volts if system_info.SENSOR_AVAILABLE else None,  # sans capteur : 12,4 V simulés
        "strategie": strat, "strategie_existe": not strat or str(strat) in shared.strategies_list,
        "depart": depart,
        "equipe": state.get("team"), "tirette": state.get("tirette"), "test_mode": state.get("test_mode"),
        "match_running": state.get("match_running"),
        "camera_embarquee": cam_cfg.get("enabled", True), "camera_embarquee_ok": hardware.camera_running(),
        "temp_cpu": temp,
    })

def background_loop():
    print("[IHM] Background loop démarrée.")
    last_sys_info_time = 0
    
    while True:
        # 1. Chrono du match (fin à 100 s, mode test...) : géré par core/match_state.py
        import ihm.shared as shared
        shared.match.tick()

        # 2. Infos Système & Santé (cadencé à 1Hz pour ne pas saturer la bande passante ZMQ/WebSocket)
        now = time.time()
        if now - last_sys_info_time >= 1.0:
            last_sys_info_time = now
            import ihm.shared as shared
            devs = {
                'lidar': os.path.exists('/dev/lidar'),
                'esp_motors': os.path.exists('/dev/esp_motors'),
                'esp_arms': os.path.exists('/dev/esp_action'),
                'camera': hardware.camera_running()
            }
            
            volts = get_voltage_float()

            # --- Détection Batterie Faible (Seuil 18V pour batterie 20V) ---
            if 3.0 <= volts < 18.0:
                 last_alert = state.get("last_bat_alert", 0)
                 
                 # On renvoie la commande toutes les 2 secondes pour être PRIORITAIRE sur les autres anims
                 if not state.get("bat_low", False) or (now - last_alert > 2.0):
                     if not state.get("bat_low", False):
                         print(f"[TASKS] BATTERIE FAIBLE ({volts}V) ! Alerte prioritaire.")
                         shared.match.set_battery_low(True)
                     
                     state["last_bat_alert"] = now
                     send_led_cmd("ANIM:BLINK:255,0,0,300") # Clignotement rapide rouge
            
            # Hystérésis pour le rétablissement
            elif volts > 19.5:
                 if state.get("bat_low", False):
                     print(f"[TASKS] Batterie rétablie ({volts}V).")
                     # Fin d'alerte : MatchState remet la couleur d'équipe
                     shared.match.set_battery_low(False)

            ip = get_ip()
            send_sys_info({
                'cpu': f"{psutil.cpu_percent()}%", 
                'temp': get_cpu_temp(),
                'volt': get_battery_voltage(), 
                'volt_float': volts,
                'current': get_battery_current(),
                'ip': ip,
                'rasp_ip': ip,
                'devs': devs,
                'checks': checklist(shared, volts, now),
            })

        time.sleep(0.1) # 10Hz (Suffisant pour le chronomètre de match)