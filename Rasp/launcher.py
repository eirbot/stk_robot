import RPi.GPIO as GPIO
import os
import time
import subprocess

# PIN correspondant au Bouton 3 (PIN_REBOOT dans buttons_thread.py)
PIN_BUTTON_3 = 15  # Mode BOARD

# Chemin vers les scripts
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXEC_SCRIPT = os.path.join(BASE_DIR, "exec.sh")
STOP_SCRIPT = os.path.join(BASE_DIR, "stop.sh")
LOG_FILE = "/home/eirbot/launcher_debug.log"

# Log de démarrage immédiat pour test
with open(LOG_FILE, "a") as f:
    f.write(f"\n[SYSTEM] Launcher démarré à {time.ctime()}\n")

def get_robot_status():
    """Vérifie si le processus main_robot.py est en cours d'exécution."""
    try:
        out = subprocess.check_output(["pgrep", "-f", "main_robot.py"]).decode().strip().split()
        my_pid = str(os.getpid())
        active_pids = [p for p in out if p != my_pid]
        return len(active_pids) > 0
    except subprocess.CalledProcessError:
        return False

def toggle_robot():
    """Lance ou arrête le robot selon son état actuel."""
    # Petit délai pour éviter les rebonds résiduels
    time.sleep(0.05)
    if GPIO.input(PIN_BUTTON_3) != 0:
        return

    print("[LAUNCHER] Bouton 3 détecté !")
    
    if get_robot_status():
        print("[LAUNCHER] Le robot tourne déjà -> Arrêt...")
        subprocess.run(["/bin/bash", STOP_SCRIPT])
    else:
        print("[LAUNCHER] Le robot est arrêté -> Démarrage...")
        env = os.environ.copy()
        # On log tout ce qui sort dans un fichier de debug
        log_file = open("/home/eirbot/launcher_debug.log", "a")
        log_file.write(f"\n--- Démarrage le {time.ctime()} ---\n")
        subprocess.Popen(["/bin/bash", EXEC_SCRIPT], 
                         stdout=log_file, 
                         stderr=log_file,
                         start_new_session=True,
                         env=env)

# Configuration GPIO
GPIO.setmode(GPIO.BOARD)
GPIO.setup(PIN_BUTTON_3, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print(f"[LAUNCHER] Service prêt. Écoute sur le PIN {PIN_BUTTON_3} (Bouton 3).")
print(f"[LAUNCHER] Script Exec: {EXEC_SCRIPT}")
print(f"[LAUNCHER] Script Stop: {STOP_SCRIPT}")

last_val = 1
debounce_counter = 0
DEBOUNCE_THRESH = 3

try:
    while True:
        val = GPIO.input(PIN_BUTTON_3)
        if val != last_val:
            debounce_counter += 1
            if debounce_counter >= DEBOUNCE_THRESH:
                last_val = val
                debounce_counter = 0
                if val == 0:  # Front descendant (appui sur le bouton)
                    toggle_robot()
        else:
            debounce_counter = 0
        time.sleep(0.05)
except KeyboardInterrupt:
    print("[LAUNCHER] Arrêt du service.")
    GPIO.cleanup()
