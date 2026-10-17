#!/usr/bin/env python3
"""Simulateur du robot : le VRAI code Python du robot (Rasp/) avec du faux matériel.

Usage (sur le PC de dev, base locale lancée par ./Base/build.sh --run) :
    python3 tools/robot_sim.py                       # se connecte à la base 127.0.0.1
    python3 tools/robot_sim.py --server 192.168.10.2 --speed 300

Puis piloter depuis l'interface web comme le vrai robot (équipe, stratégie, GO / STOP,
mode test...). L'ESP moteurs simulé déplace réellement la position (visible sur la carte).
Le simulateur travaille sur une COPIE de Rasp/config.json : la config du dépôt n'est
pas modifiée.

Sert aussi aux tests de bout en bout (test/test_e2e_base_robot.py).
"""

import argparse
import json
import math
import os
import shutil
import sys
import tempfile
import threading
import time
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RASP = os.path.join(ROOT, "Rasp")


# ---------------------------------------------------------------------------
# Faux matériel
class FakeESPMotors:
    """ESP moteurs simulé : déplacements en ligne droite à vitesse constante (SIM_SPEED mm/s),
    la position est écrite dans shared.robot_pos comme le ferait la trame odométrie « T »."""
    speed_mm_s = float(os.environ.get("SIM_SPEED", "600"))

    def __init__(self, *a, **k):
        self.calls = []
        self._stop = threading.Event()
        self.watchdog_count = 0
        self.watchdog_tripped = False

    def start(self):
        pass

    def _pos(self):
        import ihm.shared as shared
        return shared.robot_pos

    def set_pos(self, x, y, theta):
        self.calls.append(("set_pos", round(x, 3), round(y, 3), round(theta, 3)))
        self._pos().update({"x": x, "y": y, "theta": theta})

    def goto(self, x, y, theta, manual=False):
        self.calls.append(("goto", round(x, 3), round(y, 3), round(theta, 3)))
        self._stop.clear()
        pos = self._pos()
        x0, y0 = pos.get("x", 0.0), pos.get("y", 0.0)
        dist = math.hypot(x - x0, y - y0)
        duration = dist / self.speed_mm_s if self.speed_mm_s > 0 else 0.0
        steps = max(1, int(duration / 0.05))
        if dist > 1:
            pos["theta"] = math.degrees(math.atan2(y - y0, x - x0))
        for i in range(1, steps + 1):
            if self._stop.is_set():
                return True
            f = i / steps
            pos.update({"x": x0 + (x - x0) * f, "y": y0 + (y - y0) * f})
            if duration > 0:
                time.sleep(duration / steps)
        pos["theta"] = theta
        return True

    def set_speed(self, vx, vtheta):
        self.calls.append(("set_speed", vx, vtheta))

    def stop_robot(self):
        self.calls.append(("stop_robot",))
        self._stop.set()


class FakeActionneurs:
    """Actionneurs simulés : enregistre les appels."""
    def __init__(self, *a, **k):
        self.calls = []

    def start(self):
        pass

    def __getattr__(self, name):
        def rec(*a, **k):
            self.calls.append((name,) + a)
        return rec


def _module(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


def install_fakes():
    """Remplace les modules matériels absents du PC (à appeler AVANT d'importer Rasp/)."""
    if "psutil" not in sys.modules:
        try:
            import psutil  # noqa: F401
        except ImportError:
            _module("psutil", cpu_percent=lambda *a, **k: 0.0)
    for name in ("cv2", "webview"):
        if name not in sys.modules:
            try:
                __import__(name)
            except ImportError:
                _module(name, create_window=lambda *a, **k: None, start=lambda *a, **k: None)
    _module("interface_deplacement")
    _module("interface_deplacement.esp_motors", ESPMotors=FakeESPMotors)
    _module("interface_actionneur")
    _module("interface_actionneur.esp_actionneur", ESPActionneurs=FakeActionneurs)

    class NoCamera:
        def __init__(self, *a, **k):
            raise RuntimeError("pas de caméra en simulation")
    _module("utils.sensors.camera_libcamera", LibCamera=NoCamera)
    _module("Vision.cam", cam=NoCamera)


def prepare_config(server, source=None):
    """Copie de Rasp/config.json (ou `source`) pointant vers `server`, dans un dossier temporaire."""
    tmp = tempfile.mkdtemp(prefix="robot_sim_")
    path = os.path.join(tmp, "config.json")
    shutil.copy(source or os.path.join(RASP, "config.json"), path)
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.update({"server_ip": server, "lidar_mode": "OFF", "music_enabled": False,
                "camera": {**cfg.get("camera", {}), "enabled": False}})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)
    return path


def start_robot(server="127.0.0.1", config_path=None, tirette_inserted=False):
    """Démarre le code robot (client ZMQ, tâches de fond, stratégie) avec du faux matériel.
    Renvoie le module ihm.shared."""
    os.environ["ROBOT_CONFIG"] = config_path or prepare_config(server)
    install_fakes()
    if RASP not in sys.path:
        sys.path.insert(0, RASP)
    os.chdir(RASP)  # main_strat cherche les stratégies en relatif

    # IP annoncée par le robot simulé : surtout pas celle du PC, sinon la base ferait confiance
    # au navigateur du PC comme s'il était l'écran du robot (code PIN contourné)
    import utils
    import utils.system_info as system_info
    sim_ip = os.environ.get("SIM_ROBOT_IP", "127.0.0.2")
    system_info.get_ip = utils.get_ip = lambda *a, **k: sim_ip

    import ihm.shared as shared
    import strat.main_strat as main_strat
    import main_robot
    from ihm import run_ihm

    shared.match.effects = main_robot.RobotEffects()
    threading.Thread(target=run_ihm, daemon=True).start()
    threading.Thread(target=main_strat.strat_loop, daemon=True).start()
    shared.match.ready(tirette_inserted)
    return shared


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", default="127.0.0.1", help="IP de la base (défaut : 127.0.0.1)")
    parser.add_argument("--config", help="config.json de départ (défaut : Rasp/config.json)")
    parser.add_argument("--speed", type=float, help="vitesse simulée en mm/s (défaut : 600)")
    args = parser.parse_args()
    if args.speed:
        FakeESPMotors.speed_mm_s = args.speed

    config_path = prepare_config(args.server, args.config)
    print(f"[SIM] Config de simulation : {config_path}")
    shared = start_robot(args.server, config_path)
    print(f"[SIM] Robot simulé connecté à {args.server} (Ctrl+C pour arrêter)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SIM] Arrêt.")
        shared.match.stop()


if __name__ == "__main__":
    main()
