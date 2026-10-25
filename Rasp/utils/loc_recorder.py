"""Enregistrement brut pour régler la fusion odométrie + caméra (tools/regler_fusion.py).

Une ligne CSV par événement, heure de réception sur la Rasp :
  o,t,x,y,theta   trame odométrie « T » de l'ESP (repère odo)
  c,t,x,y,theta   pose caméra zénithale (repère table, après vision_odom.repere)
  s,t,x,y,theta   pose connue (set_pos) : l'odométrie repart de là
Un fichier par lancement du robot dans Rasp/logs/localisation/, les plus anciens sont supprimés.
"""

import glob
import os
import threading
import time
from datetime import datetime

KEEP_FILES = 10
# Rasp/logs/localisation, quel que soit le dossier courant au lancement
DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "localisation")
FLUSH_S = 1.0


class LocRecorder:
    def __init__(self, log_dir=DEFAULT_DIR, enabled=True):
        self.log_dir = log_dir
        self.enabled = enabled
        self._lock = threading.Lock()
        self._file = None
        self.chemin = None   # fichier en cours (calibration automatique : strat/calibration.py)
        self._last_flush = 0.0

    def _open(self):
        os.makedirs(self.log_dir, exist_ok=True)
        old = sorted(glob.glob(os.path.join(self.log_dir, "loc_*.csv")))
        for f in old[:max(0, len(old) - (KEEP_FILES - 1))]:
            try:
                os.remove(f)
            except OSError:
                pass
        name = os.path.join(self.log_dir, f"loc_{datetime.now():%Y-%m-%d_%H-%M-%S}.csv")
        self.chemin = name
        self._file = open(name, "w")
        self._file.write("type,t,x,y,theta\n")

    def write(self, kind, t, x, y, theta):
        if not self.enabled:
            return
        with self._lock:
            try:
                if self._file is None:
                    self._open()
                self._file.write(f"{kind},{t:.4f},{x:.2f},{y:.2f},{theta:.3f}\n")
                now = time.monotonic()
                if now - self._last_flush >= FLUSH_S:
                    self._file.flush()
                    self._last_flush = now
            except OSError:
                self.enabled = False  # disque plein / lecture seule : on n'insiste pas

    def flush(self):
        with self._lock:
            if self._file is not None:
                try:
                    self._file.flush()
                except OSError:
                    pass
