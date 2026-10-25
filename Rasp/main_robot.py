#!/usr/bin/env python3
import sys
import os
import platform
import time
import threading
import subprocess
import webview

import hardware
import ihm.shared as shared
from strat.main_strat import strat_loop

# e_machine ELF -> platform.machine()
_ELF_ARCH = {0x3E: "x86_64", 0xB7: "aarch64", 0x28: "armv7l"}

def _lidar_bin_a_recompiler(bin_path, cpp_path):
    """Binaire absent, plus ancien que le .cpp, ou compilé pour une autre architecture (ex : x86 copié depuis un PC)."""
    if not os.path.exists(bin_path):
        return True
    if os.path.getmtime(cpp_path) > os.path.getmtime(bin_path):
        return True
    try:
        with open(bin_path, "rb") as f:
            header = f.read(20)
        arch = _ELF_ARCH.get(int.from_bytes(header[18:20], "little"))
        return header[:4] != b"\x7fELF" or arch != platform.machine()
    except OSError:
        return True

class RobotEffects:
    """Effets matériels déclenchés par la machine d'état du match (core/match_state.py)."""

    def _hw(self):
        return hardware.esp, hardware.actionneurs

    def led(self, cmd):
        shared.send_led_cmd(cmd)

    def on_match_start(self):
        _, actionneurs = self._hw()
        if actionneurs:
            actionneurs.debloquer()  # le match précédent a pu les bloquer (fin à 100 s / STOP)
        shared.send_led_cmd("PLAY:match_start")

    def on_match_end(self, reason):
        if reason == "timer":
            # Règlement : à 100 s, arrêt des moteurs ET des actionneurs
            esp, actionneurs = self._hw()
            if esp:
                esp.stop_robot()
            if actionneurs:
                actionneurs.bloquer()
        if shared.state.get("music_enabled") and shared.audio:
            shared.audio.stop()
            shared.audio.play("end")
        shared.send_led_cmd("MATCH_STOP")

    def on_stop(self):
        esp, actionneurs = self._hw()
        if esp:
            esp.stop_robot()
        if actionneurs:
            actionneurs.bloquer()

    def on_reset(self):
        _, actionneurs = self._hw()
        if actionneurs:
            actionneurs.debloquer()


# --- MAIN ---
if __name__ == "__main__":
    print("--- ROBOT 2026 : Démarrage ---")
    
    led_process = None
    try:
        # 0. Thread IHM (Serveur Web) - PRIORITAIRE pour le debug
        print("[MAIN] 1. Lancement de l'IHM...")
        from ihm import run_ihm
        ihm_thread = threading.Thread(target=run_ihm, daemon=True)
        ihm_thread.start()

        # 1. Service LED
        led_script = os.path.join(os.path.dirname(__file__), 'utils', 'led_service.py')
        if os.path.exists(led_script):
            print(f"[MAIN] 2. Lancement du service LED : {led_script}")
            led_process = subprocess.Popen([sys.executable, led_script], preexec_fn=shared.die_with_parent)
        
        # 2. Driver LiDAR C++
        lidar_cpp = os.path.join(os.path.dirname(__file__), 'LiDAR', 'lidar_udp.cpp')
        lidar_bin = os.path.join(os.path.dirname(__file__), 'LiDAR', 'lidar_udp')
        if _lidar_bin_a_recompiler(lidar_bin, lidar_cpp):
            print("[MAIN] 3. Compilation du driver LiDAR C++...")
            subprocess.run(["g++", "-O3", lidar_cpp, "-o", lidar_bin], check=True)
            
        shared.lidar_bin = lidar_bin
        
        # On ne lance le LiDAR physiquement que si le mode initial n'est pas OFF
        if shared.state.get("lidar_mode", "OFF") != "OFF":
            print("[MAIN] 4. Lancement du service LiDAR UDP...")
            shared.lidar_process = subprocess.Popen([lidar_bin], preexec_fn=shared.die_with_parent)
        else:
            print("[MAIN] 4. LiDAR configuré sur OFF par défaut. Lancement physique différé.")
        
        # Effets matériels de la machine d'état du match
        shared.match.effects = RobotEffects()

        # 3. Matériel (ESP moteurs + actionneurs, caméra) et évitement. Un seul RobotActions,
        #    partagé par le LiDAR et la stratégie.
        print("[MAIN] 5. Démarrage du matériel et du thread d'évitement...")
        hardware.start(shared.cfg)
        from strat.actions import RobotActions
        from LiDAR.lidar_thread import LidarCollisionThread
        robot_instance = RobotActions()
        collision_thread = LidarCollisionThread(robot=robot_instance, seuil_mm=350.0)
        collision_thread.start()

        # 3b. Vidéo Streaming (MJPEG pour PC déporté et cam.py)
        print("[MAIN] 5b. Lancement Thread Camera Streamer (MJPEG port 8081)...")
        from Vision.mjpeg_streamer import MjpegStreamer
        cam_streamer = MjpegStreamer(host='0.0.0.0', port=8081)
        cam_streamer.start()

        # 4. Stratégie
        print("[MAIN] 6. Lancement Thread Stratégie...")
        strat_thread = threading.Thread(target=strat_loop, args=(robot_instance,), daemon=True)
        strat_thread.start()
        
        # 5. Boutons
        print("[MAIN] 7. Lancement Thread Boutons...")
        from buttons_thread import run_buttons_loop
        btn_thread = threading.Thread(target=run_buttons_loop, daemon=True)
        btn_thread.start()

        # (Le chrono est géré par shared.match.tick(), appelé par la boucle de fond de l'IHM)

        # Petit délai pour laisser le temps à Flask/SocketIO de démarrer
        time.sleep(3)

        # --- LIEN VERS LE SERVEUR DÉPORTÉ ---
        server_ip = shared.cfg.get('server_ip', '192.168.10.2')
        print(f"[MAIN] Connexion au serveur déporté {server_ip}:8080...")

        # --- UPDATE LED INITIALE (Couleur Equipe) ---
        # Ne pas écraser si on a une alerte tirette en cours
        if shared.state.get('tirette_msg') != "REMOVE_TO_RESET":
            print(f"[MAIN] Application de la couleur d'équipe : {shared.state['team']}")
            shared.match.show_team_color(force=True)
        else:
             print("[MAIN] Alerte Tirette active, on ne force pas la couleur d'équipe.")
             # On renvoie la commande car le service LED n'était peut-être pas prêt lors du thread boutons
             shared.send_led_cmd("ANIM:BLINK:255,100,0,350")

        # 4. Interface Graphique (RÉACTIVÉE)
        print("[MAIN] Lancement de l'affichage local...")
        webview.create_window('Robot 2026', f'http://{server_ip}:8080?mode=robot', fullscreen=True)
        webview.start()
        
    except KeyboardInterrupt:
        print("\n[MAIN] Arrêt demandé.")
    except Exception as e:
        print(f"\n[MAIN] Erreur critique : {e}")
    finally:
        if led_process:
            print("[MAIN] Arrêt du service LED...")
            led_process.terminate()
            try:
                led_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                led_process.kill()
        
        if shared.lidar_process:
            print("[MAIN] Arrêt du capteur LiDAR (C++)...")
            shared.lidar_process.terminate()
            try:
                shared.lidar_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                shared.lidar_process.kill()
        
        sys.exit(0)