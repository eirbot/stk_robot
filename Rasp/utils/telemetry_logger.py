"""Boîte noire du match : un fichier JSON lignes par match, rejoué par la page Replay de la base
(qui le lit par ssh : Base/Web/media.go). Démarrée / arrêtée par main_robot.py avec le match.

logs/telemetry/match_<date>.jsonl, une ligne JSON par enregistrement :
  {"type": "entete", "debut": heure, "equipe", "strategie", "planif": {...}, "lidar_montage": {...}}
  {"type": "f", "t": temps de match (s), "x", "y", "th", "fsm", "v", "i", "obs": état d'évitement,
   "sig": incertitude de la pose (mm), "cam": [x, y, th] pose caméra zénithale récente ou absent,
   "adv": [[x, y], ...] adversaires, "lidar": [[x, y], ...] (une image sur deux)}       10 Hz
  {"type": "e", "t": temps de match, "k": goto | plan | retour | tag | ..., ...}  événements de
   stratégie (shared.evenement), dans l'ordre.
Les anciens journaux blackbox_*.csv restent lisibles par la page Replay.
"""

import glob
import json
import os
import threading
import time
from datetime import datetime

import ihm.shared as shared
from utils.system_info import get_battery_current, get_voltage_float

KEEP_FILES = 30


class TelemetryLogger:
    # ROBOT_TELEMETRY_DIR : autre dossier (tests, simulateur)
    DEFAULT_DIR = os.environ.get("ROBOT_TELEMETRY_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "telemetry")

    def __init__(self, log_dir=DEFAULT_DIR, interval=0.1):
        self.log_dir = log_dir
        self.interval = interval
        self.running = False
        self.thread = None
        self.file = None
        self.chemin = None

    def start(self):
        if self.running:
            return
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            anciens = sorted(glob.glob(os.path.join(self.log_dir, "match_*.jsonl")))
            for f in anciens[:max(0, len(anciens) - (KEEP_FILES - 1))]:
                os.remove(f)
            self.chemin = os.path.join(self.log_dir, f"match_{datetime.now():%Y-%m-%d_%H-%M-%S}.jsonl")
            self.file = open(self.chemin, "w", encoding="utf-8")
        except OSError as e:
            print(f"[LOGGER] Erreur création fichier log: {e}")
            return
        self.running = True
        self._ecrire({"type": "entete", "debut": time.time(), "equipe": shared.state.get("team"),
                      "strategie": shared.state.get("strat_id"), "planif": shared.cfg.get("planif", {}),
                      "lidar_montage": shared.cfg.get("lidar", {}).get("montage")})
        print(f"[LOGGER] Boîte noire : {self.chemin}")
        self.thread = threading.Thread(target=self._loop, daemon=True, name="boite_noire")
        self.thread.start()

    def stop(self):
        """Ferme le journal en cours (sans effet s'il n'y en a pas : fin à 100 s puis STOP)."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        if self.file:
            self.file.close()
            self.file = None
            print("[LOGGER] Enregistrement terminé.")

    def _ecrire(self, obj):
        if self.file:
            self.file.write(json.dumps(obj, separators=(",", ":"), ensure_ascii=False) + "\n")

    def _trame(self, now, t_match, n):
        p = shared.robot_pos
        f = {"type": "f", "t": round(t_match, 2), "x": round(p["x"], 1), "y": round(p["y"], 1),
             "th": round(p["theta"], 1), "fsm": shared.state.get("fsm_state"),
             "v": round(get_voltage_float() or 0.0, 2), "i": get_battery_current(),
             "obs": shared.state.get("obstacle_type", 0), "sig": round(shared.loc.sigma()[0], 1)}
        if shared.vision_poses and now - shared.vision_poses[-1][0] < 0.3:
            _, x, y, th = shared.vision_poses[-1]
            f["cam"] = [round(x), round(y), round(th, 1)]
        adv = shared.adversaires_recents(0.5, now)
        if adv:
            f["adv"] = [[round(a[0]), round(a[1])] for a in adv]
        if n % 2 == 0 and now - shared.lidar_points_t < 0.3:
            f["lidar"] = [list(pt) for pt in shared.lidar_points]
        return f

    def _loop(self):
        n, dernier_evt = 0, time.time() - 1.0
        while self.running:
            try:
                now = time.time()
                debut = shared.state.get("start_time")
                t_match = now - debut if debut else 0.0
                for t, kind, data in list(shared.evenements):
                    if t > dernier_evt:
                        self._ecrire({"type": "e", "t": round(t - debut, 2) if debut else 0.0, "k": kind, **data})
                        dernier_evt = t
                self._ecrire(self._trame(now, t_match, n))
                n += 1
                if n % 10 == 0:
                    self.file.flush()
                time.sleep(self.interval)
            except Exception as e:
                print(f"[LOGGER] Erreur boucle: {e}")
                time.sleep(1)


telemetry = TelemetryLogger()
