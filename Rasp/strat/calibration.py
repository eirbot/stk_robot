"""Calibration automatique de la fusion odométrie + caméra (bouton dans Debug > Robot).

Le robot, posé sur la table hors match, caméra zénithale allumée :
  1. recalage caméra (point de départ) ;
  2. deux carrés de `cote_mm` autour de sa position, arrêts de 2 s aux coins ;
  3. rotations sur place (4 x 90° dans un sens, puis dans l'autre), arrêts de 2 s ;
  4. allers-retours en ligne droite.
Pendant ce temps l'enregistreur (utils/loc_recorder.py) note odométrie et caméra ; à la fin,
core/reglage_fusion.py analyse la séquence (comme tools/regler_fusion.py) et le résultat est
envoyé à la base (événement « calibration ») : réglages vision_odom proposés, que Debug
applique d'un clic, et corrections de roues / entraxe à reporter dans le firmware.

Commande (zmq) : {"type": "calibration", "payload": {"cmd": "start" | "stop", "cote_mm": 500}}
Refusée pendant un match (ihm/zmq_client.py).
"""

import math
import threading
import time

from core import frames, reglage_fusion

PAUSE_S = 2.0
VITESSE = 0.3           # facteur de vitesse / accélération des GoTo : lent, les roues ne glissent pas
MARGE_BORD_MM = 350.0   # le robot fait ~310 mm de rayon autour de son point de référence


def sequence(pose, cote_mm=500.0):
    """Étapes [(libellé, ("goto", x, y, theta) | ("pause", s))] autour de pose (repère table).

    Le carré est décalé vers le centre de la table s'il déborde ; ValueError si la table est trop
    petite pour lui (cote_mm trop grand)."""
    x0, y0, th0 = pose
    demi = cote_mm / 2.0
    lim = MARGE_BORD_MM + demi
    if 2 * lim > frames.TABLE_X_MAX - frames.TABLE_X_MIN or 2 * lim > frames.TABLE_Y_MAX - frames.TABLE_Y_MIN:
        raise ValueError(f"carré de {cote_mm:.0f} mm trop grand pour la table")
    cx = min(max(x0, frames.TABLE_X_MIN + lim), frames.TABLE_X_MAX - lim)
    cy = min(max(y0, frames.TABLE_Y_MIN + lim), frames.TABLE_Y_MAX - lim)
    coins = [(cx - demi, cy - demi), (cx + demi, cy - demi), (cx + demi, cy + demi), (cx - demi, cy + demi)]

    etapes = [("Départ", ("pause", PAUSE_S)), ("Vers le carré", ("goto", coins[0][0], coins[0][1], 0.0))]
    for tour in (1, 2):
        for i in range(1, 5):
            a, b = coins[i - 1], coins[i % 4]
            cap = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            etapes.append((f"Carré {tour}/2", ("goto", b[0], b[1], cap)))
            etapes.append((f"Carré {tour}/2", ("pause", PAUSE_S)))
    x, y = coins[0]
    cap = 0.0
    for sens, nom in ((1, "Rotations +"), (-1, "Rotations -")):
        for _ in range(4):
            cap = frames.normalize_deg(cap + sens * 90.0)
            etapes.append((nom, ("goto", x, y, cap)))
            etapes.append((nom, ("pause", PAUSE_S)))
    for _ in range(2):
        etapes.append(("Lignes droites", ("goto", x + cote_mm, y, 0.0)))
        etapes.append(("Lignes droites", ("pause", PAUSE_S)))
        etapes.append(("Lignes droites", ("goto", x, y, 0.0)))
        etapes.append(("Lignes droites", ("pause", PAUSE_S)))
    return etapes


def resume(prop, rapport):
    """Résultat lisible par la page Debug (nombres seulement, pas d'objets Python)."""
    d = rapport.get("derive") or {}
    out = {"proposition": prop, "images": rapport.get("images"), "trames_odo": rapport.get("trames_odo"),
           "latence_s": rapport.get("latence_s"),
           "bruit_camera": list(rapport["bruit_camera"]) if rapport.get("bruit_camera") else None}
    if d:
        out["erreur_distance_pct"] = round((1 / d["echelle_distance"] - 1) * 100, 2)
        out["erreur_rotation_pct"] = round((1 / d["echelle_rotation"] - 1) * 100, 2)
        out["facteur_diametre"] = round(d["echelle_distance"], 4)
        out["facteur_entraxe"] = round(d["echelle_distance"] / d["echelle_rotation"], 4)
    for nom in ("rejeu_actuel", "rejeu_propose"):
        r = rapport.get(nom) or {}
        out[nom] = {k: r.get(k) for k in ("acceptees", "rejetees", "taux_rejet", "nis_moyen")}
    return out


class Calibration:
    """Une calibration à la fois, dans son thread ; progression envoyée à la base."""

    def __init__(self, robot, shared, hardware):
        self.robot, self.shared, self.hardware = robot, shared, hardware
        self.thread = None
        self._stop = threading.Event()

    @property
    def en_cours(self):
        return self.thread is not None and self.thread.is_alive()

    def _envoyer(self, **data):
        if self.shared.zmq_client_instance:
            self.shared.zmq_client_instance.send_event("calibration", data)
        if data.get("message"):
            print(f"[CALIB] {data['message']}")

    def commande(self, payload):
        p = payload if isinstance(payload, dict) else {"cmd": str(payload)}
        if p.get("cmd") == "stop":
            self._stop.set()
            return
        if self.en_cours:
            self._envoyer(etat="erreur", message="Calibration déjà en cours")
            return
        self._stop.clear()
        cote = float(p.get("cote_mm", 500.0))
        self.thread = threading.Thread(target=self._executer, args=(cote,), daemon=True, name="calibration")
        self.thread.start()

    def _executer(self, cote):
        sh, hw = self.shared, self.hardware
        try:
            if not hw.esp:
                raise RuntimeError("ESP moteurs absent")
            if not sh.loc_log.enabled:
                raise RuntimeError("enregistrement désactivé (vision_odom.enregistrer)")
            self._envoyer(etat="en_cours", etape="Recalage caméra", progression=0.0,
                          message=f"Calibration : carré de {cote:.0f} mm")
            if not self.robot.recalage_camera(attente_max=3.0, manual=True, force=True):
                raise RuntimeError("robot non vu par la caméra zénithale (recalage impossible)")
            etapes = sequence(sh.loc.pose(), cote)
            t0 = time.time()
            for n, (libelle, (kind, *args)) in enumerate(etapes):
                if self._stop.is_set():
                    raise RuntimeError("arrêtée")
                if sh.match.running:
                    raise RuntimeError("match lancé")
                self._envoyer(etat="en_cours", etape=libelle, progression=round(n / len(etapes), 3))
                if kind == "pause":
                    fin = time.time() + args[0]
                    while time.time() < fin and not self._stop.is_set():
                        time.sleep(0.05)
                else:
                    self.robot.goto(*args, manual=True, real=True, vitesse=VITESSE)
            t1 = time.time()
            sh.loc_log.flush()
            events = [e for e in reglage_fusion.load_log(sh.loc_log.chemin) if t0 - 1.0 <= e[1] <= t1]
            prop, rapport = reglage_fusion.analyser(events, sh.cfg.get("vision_odom", {}))
            self._envoyer(etat="fini", progression=1.0, resultat=resume(prop, rapport),
                          message=f"Calibration terminée ({t1 - t0:.0f} s, {rapport.get('images')} images)")
        except Exception as e:
            self.robot.stop()
            self._envoyer(etat="erreur", message=f"Calibration interrompue : {e}")
