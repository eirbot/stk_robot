# ihm/tasks.py
import time
import psutil
import os
import numpy as np
# On assure d'importer robot_pos
from ihm.shared import state, audio, send_led_cmd, robot_pos, send_sys_info
from utils import get_ip, get_battery_voltage, get_cpu_temp, get_battery_current, get_voltage_float

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
                'camera': shared.camera is not None and shared.camera.running
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
                'devs': devs
            })

        time.sleep(0.1) # 10Hz (Suffisant pour le chronomètre de match)