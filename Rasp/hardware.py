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
camera = None       # LibCamera : caméra embarquée (flux MJPEG, image grise de la détection)
vision = None       # VisionAruco : tags ArUco vus par la caméra embarquée (Vision/aruco.py)

_started = False
_cfg = {}           # config du robot (même dict que shared.cfg, toujours à jour)


def start(cfg):
    """Ouvre les deux ESP et, si la config le demande, la caméra. Sans effet au 2e appel."""
    global esp, actionneurs, _started, _cfg
    if _started:
        return
    _started = True
    _cfg = cfg

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
    """Démarre ou arrête la caméra embarquée et sa détection ArUco (section `camera` de la config)."""
    global camera, vision
    if enabled and camera is None:
        c = _cfg.get("camera") or {}
        try:
            from utils.sensors.camera_libcamera import LibCamera
            camera = LibCamera(resolution=tuple(c.get("resolution", (1640, 1232))), framerate=c.get("fps", 10),
                               affichage=tuple(c.get("affichage", (820, 616))),
                               rotation_180=c.get("rotation_180", True), tuning=c.get("tuning"),
                               controles=c.get("controles"), webcam_id=c.get("webcam")).start()
        except Exception as e:
            print(f"[CAM] Erreur initialisation caméra : {e}")
            camera = None
        if camera is not None:
            try:
                from Vision.aruco import VisionAruco
                vision = VisionAruco(camera, c)
            except Exception as e:
                print(f"[VISION] ArUco indisponible : {e}")
                vision = None
    elif not enabled and camera is not None:
        if vision is not None:
            vision.stop()
            vision = None
        try:
            camera.stop()
        except Exception as e:
            print(f"[CAM] Erreur lors de l'arrêt de la caméra : {e}")
        camera = None


def camera_running():
    return camera is not None and camera.running
