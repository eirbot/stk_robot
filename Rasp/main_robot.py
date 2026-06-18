#!/usr/bin/env python3
import sys
import os
import time
import threading
import subprocess
import webview

# Import de l'IHM
from ihm import run_ihm
import ihm.shared as shared
from strat.main_strat import strat_loop

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
            led_process = subprocess.Popen([sys.executable, led_script])
        
        # 2. Driver LiDAR C++
        lidar_cpp = os.path.join(os.path.dirname(__file__), 'LiDAR', 'lidar_udp.cpp')
        lidar_bin = os.path.join(os.path.dirname(__file__), 'LiDAR', 'lidar_udp')
        if not os.path.exists(lidar_bin):
            print("[MAIN] 3. Compilation du driver LiDAR C++...")
            subprocess.run(["g++", "-O3", lidar_cpp, "-o", lidar_bin], check=True)
            
        shared.lidar_bin = lidar_bin
        
        # On ne lance le LiDAR physiquement que si le mode initial n'est pas OFF
        if shared.state.get("lidar_mode", "OFF") != "OFF":
            print("[MAIN] 4. Lancement du service LiDAR UDP...")
            shared.lidar_process = subprocess.Popen([lidar_bin])
        else:
            print("[MAIN] 4. LiDAR configuré sur OFF par défaut. Lancement physique différé.")
        
        # 3. Hardware & Collision
        print("[MAIN] 5. Initialisation RobotActions & Collision Thread...")
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
        strat_thread = threading.Thread(target=strat_loop, daemon=True)
        strat_thread.start()
        
        # 5. Boutons
        print("[MAIN] 7. Lancement Thread Boutons...")
        from buttons_thread import run_buttons_loop
        btn_thread = threading.Thread(target=run_buttons_loop, daemon=True)
        btn_thread.start()

        # 6. Timer
        print("[MAIN] 8. Lancement Thread Timer...")
        from timer_thread import start_timer_thread
        start_timer_thread()
        
        # Petit délai pour laisser le temps à Flask/SocketIO de démarrer
        time.sleep(3)

        # --- LIEN VERS LE SERVEUR DÉPORTÉ ---
        server_ip = shared.cfg.get('server_ip', '192.168.10.2')
        print(f"[MAIN] Connexion au serveur déporté {server_ip}:8080...")

        # --- UPDATE LED INITIALE (Couleur Equipe) ---
        # Ne pas écraser si on a une alerte tirette en cours
        if shared.state.get('tirette_msg') != "REMOVE_TO_RESET":
            print(f"[MAIN] Application de la couleur d'équipe : {shared.state['team']}")
            if shared.state['team'] == 'JAUNE':
                 shared.send_led_cmd("COLOR:255,160,0") # Jaune
            else:
                 shared.send_led_cmd("COLOR:0,0,255") # Bleue
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