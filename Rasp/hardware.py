"""Matériel du robot : créé UNE fois par start(), au démarrage (main_robot.py, simulateur, tests).

Ailleurs, on lit les attributs du module au moment de s'en servir :
    import hardware
    if hardware.esp: hardware.esp.goto(...)
None = matériel absent (simulation, module indisponible) : le code doit le tolérer.

Importer ce module ne démarre rien (avant : ouvrir les ports série des ESP et la caméra
en important strat.actions / ihm.shared).
"""

esp = None          # ESPMotors : ESP des roues (interface_deplacement/esp_motors.py)
actionneurs = None  # ESPActionneurs : ESP des actionneurs (interface_actionneur/esp_actionneur.py)
camera = None       # LibCamera : caméra embarquée (flux MJPEG)

CAMERA_RESOLUTION = (1640, 1232)
CAMERA_FRAMERATE = 10

_started = False


def start(cfg):
    """Ouvre les deux ESP et, si la config le demande, la caméra. Sans effet au 2e appel."""
    global esp, actionneurs, _started
    if _started:
        return
    _started = True

    try:
        from interface_actionneur.esp_actionneur import ESPActionneurs
        actionneurs = ESPActionneurs()
        actionneurs.start()
    except Exception as e:
        print(f"⚠️ Attention : module actionneurs indisponible ({e}) -> mode simulation")
        actionneurs = None

    try:
        from interface_deplacement.esp_motors import ESPMotors
        esp = ESPMotors()
        esp.start()
    except ImportError as e:
        print(f"⚠️ Attention : module de déplacement indisponible ({e}) -> mode simulation")
        esp = None

    set_camera_enabled(cfg.get("camera", {}).get("enabled", True))


def set_camera_enabled(enabled):
    """Démarre ou arrête la caméra embarquée (réglage `camera.enabled`)."""
    global camera
    if enabled and camera is None:
        try:
            from utils.sensors.camera_libcamera import LibCamera
            camera = LibCamera(resolution=CAMERA_RESOLUTION, framerate=CAMERA_FRAMERATE).start()
        except Exception as e:
            print(f"[CAM] Erreur initialisation caméra : {e}")
            camera = None
    elif not enabled and camera is not None:
        try:
            camera.stop()
        except Exception as e:
            print(f"[CAM] Erreur lors de l'arrêt de la caméra : {e}")
        camera = None


def camera_running():
    return camera is not None and camera.running
