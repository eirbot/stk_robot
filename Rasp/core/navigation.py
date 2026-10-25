"""Navigation : ce que sait le planificateur et ce qu'il propose (pur Python, testé).

Le même objet tourne à deux endroits :
  - sur la base (Base/Planif/planif_worker.py), alimenté par la caméra zénithale, la télémétrie et
    le LiDAR du robot ; il replanifie à 10 Hz pendant une navigation et envoie le plan au robot ;
  - sur le robot (strat/actions.py), en secours quand la base ne répond plus.
Observations : robots adverses (filtre de Kalman, core/suivi_adversaire.py + heat map), pierres
(caméra zénithale), points LiDAR, pose du robot. Plan : core/planif.planifier_temps, avec
hystérésis (core/planif.choisir_plan).
"""

import math

from core import planif
from core.suivi_adversaire import SuiviAdversaires

AGE_MAX_LIDAR_S = 0.5
AGE_MAX_PIERRES_S = 5.0        # les pierres bougent peu ; une image ratée ne les efface pas
AGE_MAX_POSE_S = 1.0
TOLERANCE_ADVERSAIRE_MM = 80.0   # point LiDAR à moins de rayon + ça d'un adversaire suivi : c'est lui
TOLERANCE_PIERRE_MM = 60.0       # point LiDAR à moins de ça d'une pierre connue : c'est elle


class Navigateur:
    def __init__(self, cfg=None):
        self.cfg = dict(cfg or {})
        self.suivi = SuiviAdversaires()
        self.chaleur = planif.Chaleur()
        self._t_chaleur = {}
        self.pierres, self.t_pierres = [], 0.0
        self.lidar, self.t_lidar = [], 0.0
        self.pose, self.t_pose = None, 0.0
        self.nav = None                 # {"id", "cible": (x, y, theta), "cfg": {...}}
        self.plan = None                # PlanTemps courant (hystérésis)
        self.carte = None               # dernière carte construite (affichage)

    # --- observations ---------------------------------------------------------------------
    def observer_vision(self, data, t):
        """Message de la caméra zénithale : {"adversaires": [{id, x, y}], "pierres": [{x, y, theta, nb}]}
        (nb : pierres empilées, déduit de la hauteur du tag)."""
        for a in data.get("adversaires") or []:
            try:
                i, x, y = int(a["id"]), float(a["x"]), float(a["y"])
            except (KeyError, TypeError, ValueError):
                continue
            self.suivi.observer(i, x, y, t)
            if t - self._t_chaleur.get(i, -1.0) >= 0.2:
                self.chaleur.observer(x, y, t)
                self._t_chaleur[i] = t
        if "pierres" in data:
            pierres = []
            for p in data.get("pierres") or []:
                try:
                    pierres.append((float(p["x"]), float(p["y"]), float(p.get("theta", 0.0)), int(p.get("nb", 1))))
                except (KeyError, TypeError, ValueError):
                    continue
            self.pierres, self.t_pierres = pierres, t

    def observer_pose(self, x, y, theta, t):
        self.pose, self.t_pose = (float(x), float(y), float(theta)), t

    def observer_lidar(self, points, t):
        self.lidar, self.t_lidar = [(float(p[0]), float(p[1])) for p in points], t

    def demander(self, id_, cible, cfg=None):
        """Nouvelle navigation vers cible (x, y, theta) ; cfg : section planif du robot."""
        if self.nav is None or self.nav["id"] != id_:
            self.plan = None
        self.nav = {"id": id_, "cible": tuple(float(v) for v in cible), "cfg": dict(cfg or {})}

    def terminer(self, id_=None):
        if self.nav is not None and (id_ is None or self.nav["id"] == id_):
            self.nav, self.plan = None, None

    # --- planification ----------------------------------------------------------------------
    def _cfg(self):
        return {**self.cfg, **(self.nav["cfg"] if self.nav else {})}

    def points_inexpliques(self, t, pierres):
        """Points LiDAR qui ne sont ni un adversaire suivi (couche dynamique, avec sa prédiction) ni une
        pierre connue (rectangle exact) : seuls ceux-là deviennent des obstacles fixes. Sinon chaque tour
        LiDAR redessine ces objets un peu ailleurs, gonflés de la taille du robot, et invalide le chemin."""
        if t - self.t_lidar > AGE_MAX_LIDAR_S:
            return []
        cfg = {**planif.DEFAUTS, **self._cfg()}
        r_adv = cfg["rayon_adversaire_mm"] + TOLERANCE_ADVERSAIRE_MM
        advs = [p.position(t)[:2] for p in self.suivi.actives(t)]
        lg, la = cfg["dimensions_pierre_mm"]
        out = []
        for x, y in self.lidar:
            if any(math.hypot(x - ax, y - ay) < r_adv for ax, ay in advs):
                continue
            if any(_dist_rect(x, y, p, lg, la) < TOLERANCE_PIERRE_MM for p in pierres):
                continue
            out.append((x, y))
        return out

    def construire_carte(self, t, cible=None):
        cfg = self._cfg()
        pierres = self.pierres if t - self.t_pierres <= AGE_MAX_PIERRES_S else []
        lidar = self.points_inexpliques(t, pierres)
        robot = self.pose[:2] if self.pose else None
        self.carte = planif.construire(cfg, (), lidar, self.chaleur, t, pierres, cible, robot)
        return self.carte

    def dynamique(self, t):
        return planif.Dynamique(self.suivi.actives(t), t, self._cfg())

    def planifier(self, t, pose=None):
        """(PlanTemps ou None, changé) pour la navigation en cours, depuis pose (ou la dernière connue)."""
        if self.nav is None:
            return None, False
        pose = pose or (self.pose if self.pose and t - self.t_pose <= AGE_MAX_POSE_S else None)
        if pose is None:
            return None, False
        cx, cy, ct = self.nav["cible"]
        carte = self.construire_carte(t, (cx, cy))
        dyn = self.dynamique(t)
        nouveau = planif.planifier_temps(carte, pose, (cx, cy), dyn, ct)
        self.plan, change = planif.choisir_plan(self.plan, nouveau, carte, dyn, pose, ct)
        return self.plan, change

    # --- messages (base -> robot / pages) ---------------------------------------------------
    def predictions(self, t, horizon_s=3.0, pas_s=0.25):
        return [{"id": p.id, "trajectoire": p.trajectoire(t, horizon_s, pas_s)} for p in self.suivi.actives(t)]

    def message_plan(self, t, plan, change, calcul_ms=None):
        """Plan pour le robot (et la carte 3D)."""
        if self.nav is None:
            return None
        msg = {"id": self.nav["id"], "cible": list(self.nav["cible"]), "t": t,
               "ok": plan is not None, "change": change, "calcul_ms": calcul_ms}
        if plan is not None:
            msg.update({"points": [[round(x, 1), round(y, 1)] for x, y in plan.points],
                        "temps": [round(v, 3) for v in plan.temps], "duree": round(plan.duree, 3),
                        "marge_adversaire_mm": None if math.isinf(plan.marge_adversaire_mm)
                        else round(plan.marge_adversaire_mm, 1),
                        "arrivee_deplacee": plan.arrivee_deplacee})
        return msg

    def message_carte(self, t, pas_mm=100.0):
        """Carte de coûts résumée, prédictions et pierres : affichage (carte 3D de la base)."""
        carte = self.carte if self.carte is not None else self.construire_carte(t)
        k = max(1, round(pas_mm / carte.res))
        return {"grille": carte.resume(pas_mm), "pas_mm": carte.res * k, "predictions": self.predictions(t),
                "pierres": [[round(x), round(y), round(th, 1), nb] for x, y, th, nb in
                            (self.pierres if t - self.t_pierres <= AGE_MAX_PIERRES_S else [])]}


def _dist_rect(x, y, pierre, longueur, largeur):
    """Distance d'un point au rectangle d'une pierre (x, y, theta[, nb]), 0 dedans."""
    c, s = math.cos(math.radians(pierre[2])), math.sin(math.radians(pierre[2]))
    u = (x - pierre[0]) * c + (y - pierre[1]) * s
    v = -(x - pierre[0]) * s + (y - pierre[1]) * c
    return math.hypot(max(abs(u) - longueur / 2, 0.0), max(abs(v) - largeur / 2, 0.0))
