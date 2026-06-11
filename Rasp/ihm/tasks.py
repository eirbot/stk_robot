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
    
    while True:
        # 1. Timer Match (inchangé)
        if state["match_running"] and state["start_time"]:
            elapsed = time.time() - state["start_time"]
            remaining = 100.0 - elapsed
            if remaining <= 0:
                state["timer_str"] = "0.0"; state["match_running"] = False; state["match_finished"] = True
                if state["music_enabled"] and audio: audio.stop(); audio.play('end')
                send_led_cmd("MATCH_STOP")
            else:
                state["timer_str"] = f"{remaining:.1f}"

        # 2. Infos Système (inchangé)
        devs = {
            'lidar': os.path.exists('/dev/lidar'),
            'esp_motors': os.path.exists('/dev/esp32_motors'),
            'esp_arms': os.path.exists('/dev/esp32_arms'),
            'camera': False 
        }
        
        volts = get_voltage_float()

        # --- Détection Batterie Faible (Seuil 18V pour batterie 20V) ---
        if 3.0 <= volts < 18.0:
             now = time.time()
             last_alert = state.get("last_bat_alert", 0)
             
             # On renvoie la commande toutes les 2 secondes pour être PRIORITAIRE sur les autres anims
             if not state.get("bat_low", False) or (now - last_alert > 2.0):
                 if not state.get("bat_low", False):
                     print(f"[TASKS] ⚠️ BATTERIE FAIBLE ({volts}V) ! Alerte Prioritaire.")
                     state["bat_low"] = True
                 
                 state["last_bat_alert"] = now
                 send_led_cmd("ANIM:BLINK:255,0,0,300") # Clignotement rapide rouge
        
        # Hystérésis pour le rétablissement
        elif volts > 19.5:
             if state.get("bat_low", False):
                 print(f"[TASKS] Batterie rétablie ({volts}V).")
                 state["bat_low"] = False
                 send_led_cmd("COLOR:0,255,0") # Retour au vert


        send_sys_info({
            'cpu': f"{psutil.cpu_percent()}%", 
            'temp': get_cpu_temp(),
            'volt': get_battery_voltage(), 
            'volt_float': volts,
            'current': get_battery_current(),
            'ip': get_ip(), 
            'devs': devs
        })

        time.sleep(0.1) # 10Hz (Suffisant pour une fluidité visuelle)