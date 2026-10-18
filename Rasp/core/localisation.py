"""Fusion odométrie ESP + caméra zénithale (pur Python, testé sans robot).

Principe
  L'ESP garde SON odométrie (repère « odo »), on n'y touche plus pendant le match : le
  firmware ignore un GoTo pendant un mouvement et « S » arrondit theta au degré.
  La Rasp tient une transformation rigide C (repère odo -> repère table) :
      pose_table = C(pose_odo)
  que chaque mesure caméra corrige un peu (filtre de Kalman sur la pose, sans
  termes croisés). Les GoTo sont convertis dans le repère odo avant envoi (to_odom).

Latence
  Une image caméra décrit le robot `latence_s` avant sa réception. On la compare à
  l'odométrie de CET instant (historique interpolé), puis la correction de C s'applique
  aussi à la pose courante : C est une transformation de tout le repère odo.

Incertitudes (écarts-types, config vision_odom)
  - odométrie : `odo_sigma_mm_par_m` (position) et `odo_sigma_deg_par_m` /
    `odo_sigma_deg_par_tour` (cap) ; la variance grandit avec la distance parcourue.
  - caméra : `cam_sigma_mm`, `cam_sigma_deg`, plus l'erreur due à la gigue de latence
    (`latence_sigma_s` x vitesse au moment de l'image).
  Une mesure trop loin de l'estimation (`porte_sigma` écarts-types, ou au-delà de
  `ecart_max_mm` / `ecart_max_deg`) est rejetée : mauvaise détection.
"""

import bisect
import math
import threading
from collections import deque

from core.frames import angle_diff_deg, apply_rigid, normalize_deg

DEFAULTS = {
    "fusion": True,
    "latence_s": 0.3,
    "latence_sigma_s": 0.05,
    "cam_sigma_mm": 15.0,
    "cam_sigma_deg": 2.0,
    "odo_sigma_mm_par_m": 20.0,
    "odo_sigma_deg_par_m": 1.0,
    "odo_sigma_deg_par_tour": 3.0,
    "porte_sigma": 4.0,
    "ecart_max_mm": 300.0,
    "ecart_max_deg": 30.0,
    "sigma_init_mm": 10.0,
    "sigma_init_deg": 1.0,
}

HISTORY_S = 2.0          # historique d'odométrie gardé pour la compensation de latence
P_MAX_MM2 = 500.0 ** 2   # plafonds de variance : au-delà, l'estimation ne veut plus rien dire
P_MAX_DEG2 = 45.0 ** 2


def _compose(c, x, y, theta):
    """Applique C = (dx, dy, dtheta) à une pose : rotation de dtheta autour de l'origine puis translation."""
    return apply_rigid(x, y, theta, c[0], c[1], c[2])


def _inverse(c, x, y, theta):
    """Applique C^-1 : pose table -> pose odo."""
    r = math.radians(-c[2])
    tx, ty = x - c[0], y - c[1]
    return (tx * math.cos(r) - ty * math.sin(r),
            tx * math.sin(r) + ty * math.cos(r),
            normalize_deg(theta - c[2]))


def _from_pair(odo, table):
    """C telle que C(odo) = table."""
    dtheta = angle_diff_deg(table[2], odo[2])
    r = math.radians(dtheta)
    rx = odo[0] * math.cos(r) - odo[1] * math.sin(r)
    ry = odo[0] * math.sin(r) + odo[1] * math.cos(r)
    return (table[0] - rx, table[1] - ry, dtheta)


class Localisation:
    """Pose du robot dans le repère table. Thread-safe (odométrie, caméra et stratégie
    l'appellent depuis des threads différents)."""

    def __init__(self, get_cfg=None):
        self._get_cfg = get_cfg or (lambda: {})
        self._lock = threading.Lock()
        self._c = (0.0, 0.0, 0.0)
        self._hist = deque()          # (t, x_odo, y_odo, theta_odo)
        self._odo = None              # dernière pose odo
        self._p_xy = 0.0
        self._p_th = 0.0
        self.stats = {"acceptees": 0, "rejetees": 0, "derniere": None}
        self._reset_variance()

    # --- Config ---
    def cfg(self):
        out = dict(DEFAULTS)
        try:
            out.update(self._get_cfg() or {})
        except Exception:
            pass
        return out

    def enabled(self):
        return bool(self.cfg()["fusion"])

    def _reset_variance(self):
        cfg = self.cfg()
        self._p_xy = cfg["sigma_init_mm"] ** 2
        self._p_th = cfg["sigma_init_deg"] ** 2

    # --- Odométrie ---
    def reset(self, table_pose, odo_pose=None, t=None):
        """Pose connue (set_pos, début de match). `odo_pose` = ce que l'ESP a réellement
        reçu (« S » arrondit à l'entier) : C rattrape l'arrondi."""
        odo_pose = tuple(odo_pose if odo_pose is not None else table_pose)
        with self._lock:
            self._c = _from_pair(odo_pose, tuple(table_pose))
            self._hist.clear()
            self._odo = odo_pose
            if t is not None:
                self._hist.append((t,) + odo_pose)
            self._reset_variance()

    def on_odom(self, t, x, y, theta):
        """Nouvelle trame odométrie « T ». Renvoie la pose table (x, y, theta)."""
        cfg = self.cfg()
        with self._lock:
            if self._odo is not None:
                dist_m = math.hypot(x - self._odo[0], y - self._odo[1]) / 1000.0
                tours = abs(angle_diff_deg(theta, self._odo[2])) / 360.0
                self._p_xy = min(P_MAX_MM2, self._p_xy + cfg["odo_sigma_mm_par_m"] ** 2 * dist_m)
                self._p_th = min(P_MAX_DEG2, self._p_th
                                 + cfg["odo_sigma_deg_par_m"] ** 2 * dist_m
                                 + cfg["odo_sigma_deg_par_tour"] ** 2 * tours)
            self._odo = (x, y, theta)
            self._hist.append((t, x, y, theta))
            while self._hist and self._hist[0][0] < t - HISTORY_S:
                self._hist.popleft()
            return _compose(self._c, x, y, theta)

    def _odo_at(self, t):
        """Pose odo interpolée à l'instant t, et vitesses (mm/s, deg/s). None si hors historique."""
        h = self._hist
        if not h:
            return None
        if t >= h[-1][0]:
            a = b = h[-1]
            if len(h) >= 2:
                a = h[-2]
        elif t < h[0][0]:
            return None
        else:
            i = bisect.bisect_right([e[0] for e in h], t)
            a, b = h[i - 1], h[i]
        dt = b[0] - a[0]
        f = 0.0 if dt <= 0 or t >= b[0] else (t - a[0]) / dt
        dth = angle_diff_deg(b[3], a[3])
        pose = (a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]), normalize_deg(a[3] + f * dth))
        if t >= h[-1][0]:
            pose = h[-1][1:]
        v = math.hypot(b[1] - a[1], b[2] - a[2]) / dt if dt > 0 else 0.0
        w = abs(dth) / dt if dt > 0 else 0.0
        return pose, v, w

    # --- Caméra ---
    def on_camera(self, t_recv, x, y, theta, gain=None):
        """Mesure caméra (repère table, déjà passée par vision_odom.repere).
        `gain` force le gain (recalage manuel, robot immobile) au lieu du gain de Kalman.
        Renvoie un dict : ok, raison, ecart_mm, ecart_deg."""
        cfg = self.cfg()
        with self._lock:
            # Gain forcé = robot immobile : la dernière odométrie vaut celle de l'image
            t_img = t_recv - cfg["latence_s"] if gain is None else math.inf
            got = self._odo_at(t_img)
            if got is None:
                return self._result(False, "pas d'odométrie à l'instant de l'image")
            odo, v, w = got
            est = _compose(self._c, *odo)
            ex, ey = x - est[0], y - est[1]
            eth = angle_diff_deg(theta, est[2])
            ecart = math.hypot(ex, ey)

            if ecart > cfg["ecart_max_mm"] or abs(eth) > cfg["ecart_max_deg"]:
                return self._result(False, "écart trop grand", ecart, eth)

            r_xy = cfg["cam_sigma_mm"] ** 2 + (v * cfg["latence_sigma_s"]) ** 2
            r_th = cfg["cam_sigma_deg"] ** 2 + (w * cfg["latence_sigma_s"]) ** 2
            if gain is None:
                porte = cfg["porte_sigma"]
                if ecart > porte * math.sqrt(self._p_xy + r_xy) or abs(eth) > porte * math.sqrt(self._p_th + r_th):
                    return self._result(False, "hors de la porte statistique", ecart, eth)
                k_xy = self._p_xy / (self._p_xy + r_xy)
                k_th = self._p_th / (self._p_th + r_th)
            else:
                k_xy = k_th = max(0.0, min(1.0, gain))
            # Innovation normalisée (x, y, theta) : ~3 en moyenne si les sigmas sont justes
            nis = (ecart ** 2 / (self._p_xy + r_xy)) + eth ** 2 / (self._p_th + r_th)

            new = (est[0] + k_xy * ex, est[1] + k_xy * ey, normalize_deg(est[2] + k_th * eth))
            self._c = _from_pair(odo, new)
            self._p_xy = (1.0 - k_xy) * self._p_xy if k_xy < 1 else r_xy
            self._p_th = (1.0 - k_th) * self._p_th if k_th < 1 else r_th
            return self._result(True, "ok", ecart, eth, nis)

    def _result(self, ok, raison, ecart=None, eth=None, nis=None):
        self.stats["acceptees" if ok else "rejetees"] += 1
        res = {"ok": ok, "raison": raison, "ecart_mm": ecart, "ecart_deg": eth, "nis": nis}
        self.stats["derniere"] = res
        return res

    # --- Conversions ---
    def to_odom(self, x, y, theta):
        """Consigne en repère table -> repère odo de l'ESP."""
        with self._lock:
            return _inverse(self._c, x, y, theta)

    def to_table(self, x, y, theta):
        with self._lock:
            return _compose(self._c, x, y, theta)

    def pose(self):
        """Pose table courante, ou None avant la première trame odométrie."""
        with self._lock:
            return _compose(self._c, *self._odo) if self._odo else None

    def sigma(self):
        """Écarts-types courants (mm, degrés)."""
        with self._lock:
            return math.sqrt(self._p_xy), math.sqrt(self._p_th)

    def correction(self):
        """C = (dx, dy, dtheta) : écart cumulé entre l'odométrie ESP et la table."""
        with self._lock:
            return self._c
