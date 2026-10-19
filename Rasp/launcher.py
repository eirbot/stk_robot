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
# Témoin posé par le déploiement : relancer le programme au démarrage du launcher (cf. autostart_after_update)
AUTOSTART_FLAG = os.path.join(BASE_DIR, ".relance_apres_maj")
# ~/launcher_debug.log (= /home/eirbot/launcher_debug.log sous le service), surchargeable
LOG_FILE = os.environ.get("ROBOT_LAUNCHER_LOG", os.path.join(os.path.expanduser("~"), "launcher_debug.log"))
LOG_MAX_BYTES = 5 * 1024 * 1024  # Rotation au-delà de 5 Mo
LOG_BACKUPS = 3                  # launcher_debug.log.1 (le plus récent) à .3

def rotate_log():
    """Si le log dépasse LOG_MAX_BYTES : .2 -> .3, .1 -> .2, log -> .1 (le .3 précédent est écrasé)."""
    try:
        if os.path.getsize(LOG_FILE) <= LOG_MAX_BYTES:
            return
        for i in range(LOG_BACKUPS - 1, 0, -1):
            src = f"{LOG_FILE}.{i}"
            if os.path.exists(src):
                os.replace(src, f"{LOG_FILE}.{i + 1}")
        os.replace(LOG_FILE, f"{LOG_FILE}.1")
    except OSError as e:
        # Jamais bloquant : au pire on continue d'écrire dans le même fichier
        print(f"[LAUNCHER] Rotation du log impossible : {e}")

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

def start_robot(reason):
    """Lance main_robot.py (via exec.sh), sortie dans le log de debug."""
    print(f"[LAUNCHER] Démarrage du robot ({reason})...")
    env = os.environ.copy()
    # On log tout ce qui sort dans un fichier de debug
    rotate_log()
    log_file = open(LOG_FILE, "a")
    log_file.write(f"\n--- Démarrage le {time.ctime()} ({reason}) ---\n")
    subprocess.Popen(["/bin/bash", EXEC_SCRIPT],
                     stdout=log_file,
                     stderr=log_file,
                     start_new_session=True,
                     env=env)


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
        start_robot("bouton 3")


def autostart_after_update():
    """Mise à jour du code (base : deployRaspCode, tools/deploy.sh) : si le programme tournait avant,
    le déploiement a laissé AUTOSTART_FLAG avant de redémarrer ce service -> on le relance."""
    try:
        os.remove(AUTOSTART_FLAG)
    except FileNotFoundError:
        return
    except OSError as e:
        print(f"[LAUNCHER] Témoin de relance illisible : {e}")
        return
    if not get_robot_status():
        start_robot("relance après mise à jour")

# Configuration GPIO
GPIO.setmode(GPIO.BOARD)
GPIO.setup(PIN_BUTTON_3, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print(f"[LAUNCHER] Service prêt. Écoute sur le PIN {PIN_BUTTON_3} (Bouton 3).")
print(f"[LAUNCHER] Script Exec: {EXEC_SCRIPT}")
print(f"[LAUNCHER] Script Stop: {STOP_SCRIPT}")
autostart_after_update()

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
